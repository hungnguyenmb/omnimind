import json
import logging
import os
import platform
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests

from database.db_manager import db
from engine.action_executor import ActionExecutor
from engine.skill_action_runners import SkillActionRunnerRegistry
from engine.assistant_memory_manager import AssistantMemoryManager
from engine.config_manager import ConfigManager
from engine.skill_runtime_manager import SkillRuntimeManager

logger = logging.getLogger(__name__)


class SkillManager:
    """
    Quản lý Skill Marketplace:
    - Đồng bộ danh sách skills từ API về cache SQLite.
    - Tải và cài đặt skill vào thư mục Codex skills local.
    - Quản lý danh sách skill đã cài.
    """

    def __init__(self):
        self.api_base_url = self._get_api_base_url()
        self.os_name = platform.system()
        self.codex_home = Path(ConfigManager.get_codex_home())
        # Đồng bộ env trong runtime để Codex CLI và skill installer dùng cùng 1 home.
        os.environ["CODEX_HOME"] = str(self.codex_home)
        self.skills_dir = self.codex_home / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.action_executor = ActionExecutor()
        self.runner_registry = SkillActionRunnerRegistry()
        self.memory_manager = AssistantMemoryManager()
        self.runtime_manager = SkillRuntimeManager(
            skill_manager=self,
            action_executor=self.action_executor,
        )

    @staticmethod
    def _extract_frontmatter(text: str) -> str:
        src = text or ""
        if not src.startswith("---"):
            return ""
        lines = src.splitlines()
        if not lines or lines[0].strip() != "---":
            return ""
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                return "\n".join(lines[1:idx])
        return ""

    @staticmethod
    def _parse_inline_list(raw: str) -> list[str]:
        val = (raw or "").strip()
        if not val:
            return []

        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                return []
            parts = [p.strip().strip("'\"") for p in inner.split(",")]
            return [p for p in parts if p]

        parts = [p.strip().strip("'\"") for p in val.split(",")]
        return [p for p in parts if p]

    def _parse_skill_frontmatter(self, skill_md_path: Path) -> dict:
        try:
            text = skill_md_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Cannot read SKILL.md for frontmatter parse: {e}")
            return {}

        frontmatter = self._extract_frontmatter(text)
        if not frontmatter:
            return {}

        data = {}
        lines = frontmatter.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].rstrip()
            stripped = line.strip()
            i += 1
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in line or stripped.startswith("-"):
                continue

            key, raw_val = line.split(":", 1)
            key = key.strip()
            val = raw_val.strip()

            if key != "required_capabilities":
                data[key] = val.strip("'\"")
                continue

            if val:
                data[key] = self._parse_inline_list(val)
                continue

            items = []
            while i < len(lines):
                sub = lines[i].strip()
                if not sub:
                    i += 1
                    continue
                if sub.startswith("-"):
                    items.append(sub[1:].strip().strip("'\""))
                    i += 1
                    continue
                break
            data[key] = [x for x in items if x]

        return data

    @staticmethod
    def _normalize_capabilities(capabilities) -> list[str]:
        if not capabilities:
            return []
        if isinstance(capabilities, str):
            capabilities = [capabilities]
        out = []
        for cap in capabilities:
            cap_val = str(cap or "").strip().lower().replace(" ", "_")
            if not cap_val:
                continue
            if cap_val not in out:
                out.append(cap_val)
        return out

    def _save_skill_capabilities(self, skill_id: str, capabilities: list[str]):
        try:
            db.execute_query(
                """
                INSERT INTO skill_capabilities (skill_id, capabilities_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(skill_id) DO UPDATE SET
                    capabilities_json = excluded.capabilities_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (skill_id, json.dumps(capabilities, ensure_ascii=False)),
                commit=True,
            )
        except Exception as e:
            logger.warning(f"Cannot persist skill capabilities ({skill_id}): {e}")

    def get_skill_runtime_requirements(self, skill_id: str) -> dict:
        row = db.fetch_one(
            "SELECT capabilities_json FROM skill_capabilities WHERE skill_id = ?",
            (skill_id,),
        )
        capabilities = []
        if row and row.get("capabilities_json"):
            try:
                parsed = json.loads(row.get("capabilities_json") or "[]")
                if isinstance(parsed, list):
                    capabilities = self._normalize_capabilities(parsed)
            except Exception:
                capabilities = []

        preflight = self.action_executor.preflight_capabilities(
            capabilities,
            action_id=f"skill:{skill_id}:preflight",
        )
        return {
            "success": True,
            "skill_id": skill_id,
            "required_capabilities": capabilities,
            "preflight": preflight,
        }

    def execute_skill_action(
        self,
        skill_id: str,
        action_id: str,
        payload: dict | None = None,
        required_capabilities=None,
        runner=None,
        auto_request_permissions: bool = False,
    ) -> dict:
        """
        API runtime chuẩn cho luồng Telegram/Codex sau này:
        - Preflight capability + permission
        - Optional auto-request permission
        - Execute action runner khi đủ điều kiện
        """
        return self.runtime_manager.execute(
            skill_id=skill_id,
            action_id=action_id,
            payload=payload or {},
            required_capabilities=required_capabilities,
            runner=runner,
            auto_request_permissions=auto_request_permissions,
        )

    def retry_skill_action_with_permission_request(
        self,
        skill_id: str,
        action_id: str,
        payload: dict | None = None,
        required_capabilities=None,
        runner=None,
    ) -> dict:
        return self.execute_skill_action(
            skill_id=skill_id,
            action_id=action_id,
            payload=payload or {},
            required_capabilities=required_capabilities,
            runner=runner,
            auto_request_permissions=True,
        )

    def execute_builtin_skill_action(
        self,
        skill_id: str,
        action_id: str,
        payload: dict | None = None,
        auto_request_permissions: bool = False,
    ) -> dict:
        """
        Execute built-in action runner qua runtime pipeline chuẩn.
        Dùng cho bot runtime nội bộ trước khi có Telegram engine đầy đủ.
        """
        meta = self.runner_registry.get_action_meta(action_id)
        if not meta:
            return {
                "success": False,
                "code": "ACTION_NOT_SUPPORTED",
                "message": f"Action built-in không hỗ trợ: {action_id}",
                "skill_id": skill_id,
                "action_id": action_id,
            }

        capabilities = meta.get("capabilities", []) or []
        return self.execute_skill_action(
            skill_id=skill_id,
            action_id=action_id,
            payload=payload or {},
            required_capabilities=capabilities,
            runner=lambda run_payload: self.runner_registry.execute(action_id, run_payload),
            auto_request_permissions=auto_request_permissions,
        )

    def record_runtime_interaction(
        self,
        user_text: str,
        assistant_text: str,
        source: str = "telegram",
        metadata: dict | None = None,
        user_external_id: str | None = None,
        assistant_external_id: str | None = None,
    ) -> dict:
        """
        API nền cho Sprint 2:
        - Log message theo turn
        - Auto summary batch
        - Auto fact extraction có confidence
        - Retention sau ingest để tránh phình DB
        """
        result = self.memory_manager.ingest_turn(
            user_text=user_text,
            assistant_text=assistant_text,
            source=source,
            metadata=metadata or {},
            user_external_id=user_external_id,
            assistant_external_id=assistant_external_id,
            auto_summary=True,
            auto_fact=True,
        )
        # Giữ DB gọn nhẹ, tránh tăng trưởng vô hạn.
        self.memory_manager.prune_history()
        return result

    def get_runtime_conversation_context(
        self,
        message_limit: int = 20,
        facts_limit: int = 20,
        char_budget: int = 12000,
    ) -> dict:
        return self.memory_manager.build_runtime_context(
            message_limit=message_limit,
            facts_limit=facts_limit,
            char_budget=char_budget,
        )

    def update_assistant_profile(
        self,
        display_name: str | None = None,
        persona_prompt: str | None = None,
        preferences: dict | None = None,
    ) -> bool:
        return self.memory_manager.update_profile(
            display_name=display_name,
            persona_prompt=persona_prompt,
            preferences=preferences or {},
        )

    def _get_api_base_url(self) -> str:
        env_url = os.environ.get("OMNIMIND_API_URL", "").strip()
        if env_url:
            return env_url
        cfg_url = (
            ConfigManager.get("omnimind_api_url", "").strip()
            or ConfigManager.get("OMNIMIND_API_URL", "").strip()
        )
        if cfg_url:
            return cfg_url
        return "http://localhost:8050"

    def _platform_key(self) -> str:
        if self.os_name == "Darwin":
            return "darwin"
        if self.os_name == "Windows":
            return "win32"
        if self.os_name == "Linux":
            return "linux"
        return "unknown"

    def _license_key(self) -> str:
        return ConfigManager.get("license_key", "").strip()

    @staticmethod
    def _safe_json(resp: requests.Response) -> dict:
        if not resp.content:
            return {}
        try:
            data = resp.json()
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    @staticmethod
    def _response_preview(resp: requests.Response, limit: int = 180) -> str:
        try:
            text = (resp.text or "").strip().replace("\n", " ")
        except Exception:
            return ""
        return text[:limit]

    def _response_error_message(self, resp: requests.Response, data: dict, default: str) -> str:
        if isinstance(data, dict):
            message = data.get("message") or data.get("error") or data.get("detail")
            if message:
                return str(message)
        preview = self._response_preview(resp)
        if preview:
            return f"{default} (HTTP {resp.status_code}) - {preview}"
        return f"{default} (HTTP {resp.status_code})"

    @staticmethod
    def _artifact_hint(pkg_path: Path) -> str:
        try:
            head = pkg_path.read_bytes()[:256].strip()
        except Exception:
            return ""
        if not head:
            return "Artifact rỗng, không có dữ liệu tải về."

        if head.startswith(b"<"):
            return "Artifact trả về HTML, hãy kiểm tra lại URL download/public CDN."

        if head.startswith(b"{") or head.startswith(b"["):
            try:
                payload = json.loads(head.decode("utf-8", errors="ignore"))
                if isinstance(payload, dict):
                    message = payload.get("message") or payload.get("error")
                    if message:
                        return f"Artifact trả về JSON lỗi: {message}"
            except Exception:
                pass
            return "Artifact trả về JSON thay vì file zip/tar."

        return ""

    def fetch_marketplace_skills(self, page: int = 1, per_page: int = 200) -> dict:
        """
        Lấy skills từ server và cache vào SQLite.
        """
        url = f"{self.api_base_url}/api/v1/omnimind/skills"
        params = {
            "page": page,
            "per_page": per_page,
            "os_name": self.os_name,
            "license_key": self._license_key(),
        }
        headers = {"Accept": "application/json"}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            data = self._safe_json(resp)
            if resp.status_code != 200:
                return {"success": False, "message": self._response_error_message(resp, data, "Không lấy được danh sách skills.")}

            skills = data.get("skills", [])
            if not isinstance(skills, list):
                return {"success": False, "message": "Response skills không đúng định dạng."}
            self._cache_marketplace_skills(skills)
            return {"success": True, "skills": skills, "raw": data}
        except Exception as e:
            logger.error(f"fetch_marketplace_skills error: {e}")
            return {"success": False, "message": str(e)}

    def _cache_marketplace_skills(self, skills: list):
        for s in skills:
            try:
                db.execute_query(
                    """
                    INSERT INTO marketplace_skills (id, name, description, skill_type, price, author, version, manifest_json, is_vip)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        description = excluded.description,
                        skill_type = excluded.skill_type,
                        price = excluded.price,
                        author = excluded.author,
                        version = excluded.version,
                        manifest_json = excluded.manifest_json,
                        is_vip = excluded.is_vip
                    """,
                    (
                        s.get("id", ""),
                        s.get("name", ""),
                        s.get("description", ""),
                        s.get("skill_type", "KNOWLEDGE"),
                        float(s.get("price", 0) or 0),
                        s.get("author", ""),
                        s.get("version", ""),
                        json.dumps(s, ensure_ascii=False),
                        1 if s.get("is_vip") else 0,
                    ),
                    commit=True,
                )
            except Exception as e:
                logger.error(f"cache skill error ({s.get('id')}): {e}")

    def get_cached_marketplace_skills(self) -> list:
        rows = db.fetch_all("SELECT * FROM marketplace_skills ORDER BY id ASC")
        out = []
        for r in rows:
            try:
                data = json.loads(r.get("manifest_json") or "{}")
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}

            out.append({
                "id": r.get("id"),
                "name": data.get("name", r.get("name") or ""),
                "description": data.get("description", r.get("description") or ""),
                "short": data.get("short", data.get("short_description", r.get("description") or "")),
                "detail": data.get("detail", data.get("detail_description", r.get("description") or "")),
                "skill_type": r.get("skill_type"),
                "price": r.get("price", 0),
                "author": data.get("author", r.get("author") or ""),
                "version": data.get("version", r.get("version") or ""),
                "is_vip": bool(r.get("is_vip")),
                "icon": data.get("icon", "🧩"),
                "badge": data.get("badge", "SKILL"),
                "color": data.get("color", "#3B82F6"),
                "download_url": data.get("download_url", ""),
                "is_owned": bool(data.get("is_owned", False)),
                "requires_purchase": bool(data.get("requires_purchase", False)),
            })
        return out

    def get_installed_skills(self) -> list:
        return db.fetch_all("SELECT * FROM installed_skills ORDER BY installed_at DESC")

    def purchase_skill(self, skill_id: str) -> dict:
        license_key = self._license_key()
        if not license_key:
            return {"success": False, "message": "Thiếu license key để cấp quyền skill."}

        url = f"{self.api_base_url}/api/v1/omnimind/skills/{skill_id}/purchase"
        headers = {"Accept": "application/json"}
        try:
            resp = requests.post(url, json={"license_key": license_key}, headers=headers, timeout=20)
            data = self._safe_json(resp)
            if resp.status_code != 200:
                return {"success": False, "message": self._response_error_message(resp, data, "Không thể cấp quyền skill.")}
            return {"success": True, "message": data.get("message", "Đã cấp quyền skill.")}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def install_skill(self, skill_id: str) -> dict:
        """
        Tải artifact của skill từ server và cài vào ~/.codex/skills/<skill_id>.
        """
        license_key = self._license_key()
        download_url = f"{self.api_base_url}/api/v1/omnimind/skills/{skill_id}/download"
        params = {"os_name": self.os_name, "platform": self._platform_key()}
        headers = {"Accept": "application/json"}
        if license_key:
            params["license_key"] = license_key

        try:
            # 1) Resolve download URL
            resolve_resp = requests.get(download_url, params=params, headers=headers, timeout=20)
            resolve_data = self._safe_json(resolve_resp)
            if resolve_resp.status_code != 200:
                msg = self._response_error_message(resolve_resp, resolve_data, "Không lấy được link tải skill.")
                return {"success": False, "message": msg}

            if not resolve_data:
                preview = self._response_preview(resolve_resp)
                return {
                    "success": False,
                    "message": (
                        "API resolve download không trả JSON hợp lệ."
                        + (f" Nội dung: {preview}" if preview else "")
                    ),
                }

            artifact_url = (resolve_data.get("url") or "").strip()
            if not artifact_url:
                return {"success": False, "message": "Skill không có URL tải hợp lệ."}

            # 2) Download artifact
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir) / "skill_artifact.pkg"
                with requests.get(artifact_url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                f.write(chunk)

                extract_dir = Path(tmpdir) / "extract"
                extract_dir.mkdir(parents=True, exist_ok=True)

                extracted = False
                if zipfile.is_zipfile(tmp_path):
                    with zipfile.ZipFile(tmp_path, "r") as zf:
                        zf.extractall(extract_dir)
                    extracted = True
                elif tarfile.is_tarfile(tmp_path):
                    with tarfile.open(tmp_path, "r:*") as tf:
                        tf.extractall(extract_dir)
                    extracted = True

                if not extracted:
                    hint = self._artifact_hint(tmp_path)
                    base = "Gói skill không đúng định dạng zip/tar."
                    return {"success": False, "message": f"{base} {hint}".strip()}

                # 3) Chuẩn hóa thư mục đích
                target_dir = self.skills_dir / skill_id
                if target_dir.exists():
                    shutil.rmtree(target_dir)

                candidate = extract_dir
                children = [p for p in extract_dir.iterdir()]
                if len(children) == 1 and children[0].is_dir():
                    candidate = children[0]

                if not (candidate / "SKILL.md").exists():
                    return {"success": False, "message": "Skill package thiếu file SKILL.md."}

                skill_frontmatter = self._parse_skill_frontmatter(candidate / "SKILL.md")
                required_capabilities = self._normalize_capabilities(
                    skill_frontmatter.get("required_capabilities", [])
                )

                # 3.1) Cài theo cơ chế staging + backup để tránh mất skill cũ nếu update lỗi.
                staging_dir = self.skills_dir / f".{skill_id}.tmp"
                backup_dir = self.skills_dir / f".{skill_id}.bak"
                if staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)
                if backup_dir.exists():
                    shutil.rmtree(backup_dir, ignore_errors=True)

                restore_backup = False
                try:
                    shutil.copytree(candidate, staging_dir)

                    if target_dir.exists():
                        target_dir.rename(backup_dir)
                        restore_backup = True

                    staging_dir.rename(target_dir)
                    restore_backup = False

                    if backup_dir.exists():
                        shutil.rmtree(backup_dir, ignore_errors=True)
                except Exception:
                    if target_dir.exists():
                        shutil.rmtree(target_dir, ignore_errors=True)
                    if restore_backup and backup_dir.exists():
                        backup_dir.rename(target_dir)
                    if staging_dir.exists():
                        shutil.rmtree(staging_dir, ignore_errors=True)
                    raise

                # 4) Cập nhật DB local
                db.execute_query(
                    """
                    INSERT INTO installed_skills (skill_id, name, version, local_path, installed_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(skill_id) DO UPDATE SET
                        name = excluded.name,
                        version = excluded.version,
                        local_path = excluded.local_path,
                        installed_at = CURRENT_TIMESTAMP
                    """,
                    (
                        skill_id,
                        resolve_data.get("name", skill_id),
                        resolve_data.get("version", ""),
                        str(target_dir),
                    ),
                    commit=True,
                )

            self._save_skill_capabilities(skill_id, required_capabilities)
            preflight = self.action_executor.preflight_capabilities(
                required_capabilities,
                action_id=f"skill:{skill_id}:install",
            )

            result = {
                "success": True,
                "skill_id": skill_id,
                "message": f"Cài skill '{skill_id}' thành công.",
                "required_capabilities": required_capabilities,
                "permission_preflight": preflight,
            }
            if not preflight.get("success"):
                missing = preflight.get("missing_permissions", [])
                if missing:
                    names = ", ".join(
                        sorted({m.get("permission", "") for m in missing if m.get("permission")})
                    )
                    result["message"] += (
                        f" Skill cần cấp thêm quyền hệ thống trước khi chạy action: {names}."
                    )
                unknown = preflight.get("unknown_capabilities", [])
                if unknown:
                    result["message"] += (
                        " Skill khai báo capability chưa được app hỗ trợ: "
                        + ", ".join(unknown)
                        + "."
                    )
            return result
        except Exception as e:
            logger.error(f"install_skill error ({skill_id}): {e}")
            return {"success": False, "message": str(e)}

    def uninstall_skill(self, skill_id: str) -> dict:
        try:
            target_dir = self.skills_dir / skill_id
            if target_dir.exists():
                shutil.rmtree(target_dir)
            db.execute_query("DELETE FROM installed_skills WHERE skill_id = ?", (skill_id,), commit=True)
            db.execute_query("DELETE FROM skill_capabilities WHERE skill_id = ?", (skill_id,), commit=True)
            return {"success": True, "message": f"Đã gỡ skill '{skill_id}'."}
        except Exception as e:
            logger.error(f"uninstall_skill error ({skill_id}): {e}")
            return {"success": False, "message": str(e)}
