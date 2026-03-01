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
from engine.config_manager import ConfigManager

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
        self.codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        self.skills_dir = self.codex_home / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)

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

                shutil.copytree(candidate, target_dir)

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

            return {"success": True, "message": f"Cài skill '{skill_id}' thành công."}
        except Exception as e:
            logger.error(f"install_skill error ({skill_id}): {e}")
            return {"success": False, "message": str(e)}

    def uninstall_skill(self, skill_id: str) -> dict:
        try:
            target_dir = self.skills_dir / skill_id
            if target_dir.exists():
                shutil.rmtree(target_dir)
            db.execute_query("DELETE FROM installed_skills WHERE skill_id = ?", (skill_id,), commit=True)
            return {"success": True, "message": f"Đã gỡ skill '{skill_id}'."}
        except Exception as e:
            logger.error(f"uninstall_skill error ({skill_id}): {e}")
            return {"success": False, "message": str(e)}
