import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import requests

from database.db_manager import db
from engine.action_executor import ActionExecutor
from engine.skill_action_runners import SkillActionRunnerRegistry
from engine.assistant_memory_manager import AssistantMemoryManager
from engine.conversation_orchestrator import ConversationOrchestrator
from engine.config_manager import ConfigManager
from engine.http_client import request_with_retry
from engine.skill_runtime_manager import SkillRuntimeManager

logger = logging.getLogger(__name__)


class SkillManager:
    """
    Quản lý Skill Marketplace:
    - Đồng bộ danh sách skills từ API về cache SQLite.
    - Tải và cài đặt skill vào thư mục Codex skills local.
    - Quản lý danh sách skill đã cài.
    """

    DEFAULT_SCRIPT_TIMEOUT_SEC = 60.0

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
        self.conversation_orchestrator = ConversationOrchestrator(self.memory_manager)
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

    @staticmethod
    def _safe_tool_function_name(skill_id: str, function_name: str) -> str:
        skill_part = str(skill_id or "").strip().lower().replace("-", "_")
        fn_part = str(function_name or "").strip().lower().replace("-", "_")
        return f"skill__{skill_part}__{fn_part}"

    @staticmethod
    def _normalize_supported_channels(raw_value) -> list[str]:
        if not raw_value:
            return []
        if isinstance(raw_value, str):
            raw_value = [raw_value]
        out = []
        for item in raw_value:
            token = str(item or "").strip().lower()
            if token and token not in out:
                out.append(token)
        return out

    def _read_tool_manifest(self, skill_dir: Path) -> dict:
        manifest_path = skill_dir / "tool_manifest.json"
        if not manifest_path.is_file():
            return {}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception as e:
            logger.warning(f"Cannot parse tool_manifest.json in {skill_dir}: {e}")
            return {}

    def _normalize_skill_tool_function(self, skill_id: str, skill_dir: Path, item: dict) -> tuple[dict | None, str]:
        if not isinstance(item, dict):
            return None, "Function entry không phải object."

        function_name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        input_schema = item.get("input_schema")
        execution = item.get("execution") if isinstance(item.get("execution"), dict) else {}
        execution_type = str((execution or {}).get("type") or "").strip().lower()
        entrypoint = str((execution or {}).get("entrypoint") or "").strip()
        if not function_name:
            return None, "Thiếu function.name."
        if not description:
            return None, f"Function '{function_name}' thiếu description."
        if not isinstance(input_schema, dict):
            return None, f"Function '{function_name}' thiếu input_schema hợp lệ."
        if execution_type != "python_script":
            return None, f"Function '{function_name}' có execution.type chưa hỗ trợ: {execution_type or 'empty'}."
        if not entrypoint:
            return None, f"Function '{function_name}' thiếu execution.entrypoint."

        resolved_skill_dir = skill_dir.resolve()
        resolved_entrypoint = (resolved_skill_dir / entrypoint).resolve()
        if not self._path_is_within(resolved_skill_dir, resolved_entrypoint) or not resolved_entrypoint.is_file():
            return None, f"Function '{function_name}' có entrypoint không hợp lệ: {entrypoint}"

        approval_policy = str(item.get("approval_policy") or "on-request").strip().lower()
        if approval_policy not in {"auto", "on-request"}:
            approval_policy = "on-request"

        required_capabilities = self._normalize_capabilities(item.get("required_capabilities", []))
        supported_channels = self._normalize_supported_channels(item.get("supported_channels", []))
        timeout_seconds = item.get("timeout_seconds")
        try:
            timeout_value = float(timeout_seconds) if timeout_seconds not in (None, "") else 0.0
        except Exception:
            timeout_value = 0.0

        normalized = {
            "name": self._safe_tool_function_name(skill_id, function_name),
            "original_name": function_name,
            "skill_id": skill_id,
            "description": f"[Skill {skill_id}] {description}",
            "input_schema": input_schema,
            "required_capabilities": required_capabilities,
            "approval_policy": approval_policy,
            "supported_channels": supported_channels,
            "returns_artifacts": bool(item.get("returns_artifacts")),
            "execution_target": {
                "kind": "skill_function",
                "skill_id": skill_id,
                "function_name": function_name,
                "entrypoint": str(resolved_entrypoint.relative_to(resolved_skill_dir)),
                "execution_type": execution_type,
                "timeout_seconds": timeout_value,
            },
        }
        return normalized, ""

    def get_installed_skill_tool_functions(
        self,
        *,
        supported_channel: str = "",
        include_invalid: bool = False,
    ) -> list[dict]:
        rows = self.get_installed_skills()
        channel = str(supported_channel or "").strip().lower()
        out: list[dict] = []
        for row in rows:
            skill_id = str((row or {}).get("skill_id") or "").strip()
            local_path = Path(str((row or {}).get("local_path") or "")).expanduser()
            if not skill_id or not local_path.is_dir():
                continue

            manifest = self._read_tool_manifest(local_path)
            functions = manifest.get("functions") if isinstance(manifest.get("functions"), list) else []
            for item in functions:
                normalized, error = self._normalize_skill_tool_function(skill_id, local_path, item)
                if error:
                    logger.warning(f"Skip invalid tool function for skill {skill_id}: {error}")
                    if include_invalid:
                        out.append({"skill_id": skill_id, "error": error, "raw": item})
                    continue

                supported_channels = normalized.get("supported_channels") or []
                if channel and supported_channels and channel not in supported_channels:
                    continue
                out.append(normalized)
        return out

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

    def _get_required_capabilities_for_skill(self, skill_id: str, local_path: Path | None = None) -> list[str]:
        row = db.fetch_one(
            "SELECT capabilities_json FROM skill_capabilities WHERE skill_id = ?",
            (skill_id,),
        )
        if row and row.get("capabilities_json"):
            try:
                parsed = json.loads(row.get("capabilities_json") or "[]")
                if isinstance(parsed, list):
                    return self._normalize_capabilities(parsed)
            except Exception:
                logger.warning(f"Cannot decode skill capabilities for {skill_id}", exc_info=True)

        if local_path:
            frontmatter = self._parse_skill_frontmatter(local_path / "SKILL.md")
            capabilities = self._normalize_capabilities(frontmatter.get("required_capabilities", []))
            if capabilities:
                self._save_skill_capabilities(skill_id, capabilities)
            return capabilities
        return []

    @staticmethod
    def _windows_hidden_subprocess_kwargs() -> dict:
        if platform.system() != "Windows":
            return {}
        kwargs: dict = {}
        create_no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
        if create_no_window:
            kwargs["creationflags"] = create_no_window
        startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
        if startupinfo_cls:
            startupinfo = startupinfo_cls()
            startupinfo.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0) or 0)
            startupinfo.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0) or 0)
            kwargs["startupinfo"] = startupinfo
        return kwargs

    @staticmethod
    def _safe_preview(text: str, limit: int = 500) -> str:
        body = str(text or "").strip()
        if len(body) <= limit:
            return body
        return body[: max(1, limit - 1)].rstrip() + "…"

    @staticmethod
    def _path_is_within(base_dir: Path, candidate: Path) -> bool:
        try:
            candidate.resolve().relative_to(base_dir.resolve())
            return True
        except Exception:
            return False

    def _resolve_python_executable(self) -> str | None:
        env_candidates = [
            os.environ.get("OMNIMIND_SKILL_PYTHON", ""),
            os.environ.get("OMNIMIND_PYTHON", ""),
        ]
        for candidate in env_candidates:
            raw = str(candidate or "").strip()
            if raw and Path(raw).exists():
                return raw

        exe = Path(sys.executable or "")
        if exe.is_file() and exe.name.lower().startswith("python"):
            return str(exe)

        for cmd_name in ("python3", "python"):
            resolved = shutil.which(cmd_name)
            if resolved:
                return resolved
        return None

    def _get_installed_skill_row(self, skill_id: str) -> dict | None:
        return db.fetch_one(
            "SELECT skill_id, name, version, local_path, installed_at FROM installed_skills WHERE skill_id = ?",
            (skill_id,),
        )

    def _get_marketplace_skill_entrypoint(self, skill_id: str) -> str:
        row = db.fetch_one(
            "SELECT manifest_json FROM marketplace_skills WHERE id = ?",
            (skill_id,),
        )
        if not row or not row.get("manifest_json"):
            return ""
        try:
            manifest = json.loads(row.get("manifest_json") or "{}")
        except Exception:
            return ""
        if not isinstance(manifest, dict):
            return ""
        return str(manifest.get("entrypoint") or "").strip()

    def _resolve_installed_skill_entrypoint(
        self,
        skill_id: str,
        skill_dir: Path,
        explicit_entrypoint: str = "",
    ) -> Path:
        candidates: list[str] = []
        if explicit_entrypoint:
            candidates.append(explicit_entrypoint)

        manifest_entrypoint = self._get_marketplace_skill_entrypoint(skill_id)
        if manifest_entrypoint:
            candidates.append(manifest_entrypoint)

        skill_md_path = skill_dir / "SKILL.md"
        if skill_md_path.exists():
            frontmatter = self._parse_skill_frontmatter(skill_md_path)
            frontmatter_entrypoint = str(frontmatter.get("entrypoint") or "").strip()
            if frontmatter_entrypoint:
                candidates.append(frontmatter_entrypoint)

        scripts_dir = skill_dir / "scripts"
        if scripts_dir.is_dir():
            script_files = sorted(
                path for path in scripts_dir.glob("*.py")
                if path.is_file() and not path.name.startswith(".")
            )
            if len(script_files) == 1:
                candidates.append(str(script_files[0].relative_to(skill_dir)))

        seen: set[str] = set()
        for raw in candidates:
            value = str(raw or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            candidate = (skill_dir / value).resolve()
            if not self._path_is_within(skill_dir, candidate):
                continue
            if candidate.is_file():
                return candidate

        raise FileNotFoundError(
            f"Không resolve được entrypoint cho skill '{skill_id}'."
        )

    @staticmethod
    def _build_cli_args_from_payload(payload: dict | None) -> list[str]:
        payload = payload or {}
        raw_args = payload.get("argv")
        if raw_args is None:
            raw_args = payload.get("args")
        if isinstance(raw_args, list):
            return [str(item) for item in raw_args if str(item or "").strip()]

        arg_map = payload.get("args")
        if not isinstance(arg_map, dict):
            arg_map = payload if isinstance(payload, dict) else {}

        reserved = {"timeout_seconds", "entrypoint", "stdin_json", "env", "argv", "args"}
        cli_args: list[str] = []
        for key, value in arg_map.items():
            if key in reserved:
                continue
            if value is None or value is False:
                continue

            flag = "--" + str(key).strip().replace("_", "-")
            if value is True:
                cli_args.append(flag)
                continue
            if isinstance(value, list):
                for item in value:
                    cli_args.extend([flag, str(item)])
                continue
            cli_args.extend([flag, str(value)])
        return cli_args

    @staticmethod
    def _redact_cli_args(args: list[str]) -> list[str]:
        secret_flags = {"--api-secret", "--secret", "--token", "--password"}
        redacted: list[str] = []
        hide_next = False
        for item in args:
            if hide_next:
                redacted.append("***")
                hide_next = False
                continue
            token = str(item or "")
            lowered = token.lower()
            if lowered in secret_flags:
                redacted.append(token)
                hide_next = True
                continue
            redacted.append(token)
        return redacted

    def _run_installed_skill_process(
        self,
        skill_id: str,
        skill_dir: Path,
        payload: dict | None = None,
        entrypoint: str = "",
        timeout_seconds: float | None = None,
    ) -> dict:
        payload = payload or {}
        timeout = float(timeout_seconds or payload.get("timeout_seconds") or self.DEFAULT_SCRIPT_TIMEOUT_SEC)
        resolved_skill_dir = skill_dir.resolve()
        script_path = self._resolve_installed_skill_entrypoint(skill_id, resolved_skill_dir, explicit_entrypoint=entrypoint)
        python_executable = self._resolve_python_executable()
        if not python_executable:
            return {
                "success": False,
                "code": "PYTHON_NOT_FOUND",
                "message": "Không tìm thấy Python runtime để chạy skill script.",
                "skill_id": skill_id,
                "entrypoint": str(script_path.relative_to(resolved_skill_dir)),
            }

        cmd = [python_executable, str(script_path)] + self._build_cli_args_from_payload(payload)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        custom_env = payload.get("env")
        if isinstance(custom_env, dict):
            for key, value in custom_env.items():
                if not str(key or "").strip():
                    continue
                env[str(key)] = str(value)

        stdin_data = None
        if isinstance(payload.get("stdin_json"), dict):
            stdin_data = json.dumps(payload.get("stdin_json"), ensure_ascii=False)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=stdin_data,
                cwd=str(skill_dir),
                env=env,
                timeout=max(1.0, timeout),
                check=False,
                **self._windows_hidden_subprocess_kwargs(),
            )
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "code": "SKILL_TIMEOUT",
                "message": f"Skill '{skill_id}' chạy quá thời gian cho phép ({timeout:.0f}s).",
                "skill_id": skill_id,
                "entrypoint": str(script_path.relative_to(resolved_skill_dir)),
                "timeout_seconds": timeout,
            }
        except Exception as e:
            logger.exception(f"execute installed skill process failed ({skill_id})")
            return {
                "success": False,
                "code": "SKILL_RUN_FAILED",
                "message": f"Không chạy được skill '{skill_id}': {str(e)[:220]}",
                "skill_id": skill_id,
                "entrypoint": str(script_path.relative_to(resolved_skill_dir)),
            }

        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        parsed_json = None
        if stdout:
            try:
                parsed_json = json.loads(stdout)
            except Exception:
                parsed_json = None

        success = proc.returncode == 0
        code = "OK" if success else "SKILL_EXIT_NONZERO"
        message = self._safe_preview(stdout or stderr or "Skill chạy xong nhưng không trả nội dung.")

        if isinstance(parsed_json, dict):
            if "success" in parsed_json:
                success = bool(parsed_json.get("success"))
            code = str(
                parsed_json.get("code")
                or parsed_json.get("error_code")
                or ("OK" if success else code)
            ).strip() or ("OK" if success else code)
            message = str(
                parsed_json.get("message")
                or ("Skill chạy thành công." if success else "Skill chạy thất bại.")
            ).strip() or message

        if proc.returncode != 0 and success:
            success = False
            code = "SKILL_EXIT_NONZERO"

        result = {
            "success": success,
            "code": code,
            "message": message,
            "skill_id": skill_id,
            "entrypoint": str(script_path.relative_to(resolved_skill_dir)),
            "command": self._redact_cli_args(cmd),
            "exit_code": proc.returncode,
            "stdout_preview": self._safe_preview(stdout),
            "stderr_preview": self._safe_preview(stderr),
        }
        if isinstance(parsed_json, dict):
            result["data"] = parsed_json
            if "artifact_path" in parsed_json:
                result["artifact_path"] = parsed_json.get("artifact_path")
        elif stdout:
            result["output"] = stdout
        return result

    def execute_installed_skill(
        self,
        skill_id: str,
        payload: dict | None = None,
        entrypoint: str = "",
        timeout_seconds: float | None = None,
        auto_request_permissions: bool = False,
    ) -> dict:
        skill_id = str(skill_id or "").strip()
        if not skill_id:
            return {"success": False, "code": "SKILL_ID_MISSING", "message": "Thiếu skill_id."}

        installed = self._get_installed_skill_row(skill_id)
        if not installed:
            return {
                "success": False,
                "code": "SKILL_NOT_INSTALLED",
                "message": f"Skill '{skill_id}' chưa được cài trên máy này.",
                "skill_id": skill_id,
            }

        local_path = Path(str(installed.get("local_path") or "")).expanduser()
        if not local_path.is_dir():
            return {
                "success": False,
                "code": "SKILL_PATH_INVALID",
                "message": f"Thư mục skill '{skill_id}' không còn tồn tại: {local_path}",
                "skill_id": skill_id,
            }

        required_capabilities = self._get_required_capabilities_for_skill(skill_id, local_path=local_path)
        return self.execute_skill_action(
            skill_id=skill_id,
            action_id=f"run_installed_skill:{skill_id}",
            payload=payload or {},
            required_capabilities=required_capabilities,
            runner=lambda run_payload: self._run_installed_skill_process(
                skill_id=skill_id,
                skill_dir=local_path,
                payload=run_payload,
                entrypoint=entrypoint,
                timeout_seconds=timeout_seconds,
            ),
            auto_request_permissions=auto_request_permissions,
        )

    def execute_installed_skill_function(
        self,
        skill_id: str,
        function_name: str,
        arguments: dict | None = None,
        *,
        auto_request_permissions: bool = False,
    ) -> dict:
        skill_id = str(skill_id or "").strip()
        function_name = str(function_name or "").strip()
        if not skill_id:
            return {"success": False, "code": "SKILL_ID_MISSING", "message": "Thiếu skill_id."}
        if not function_name:
            return {"success": False, "code": "FUNCTION_NAME_MISSING", "message": "Thiếu function_name."}

        installed = self._get_installed_skill_row(skill_id)
        if not installed:
            return {
                "success": False,
                "code": "SKILL_NOT_INSTALLED",
                "message": f"Skill '{skill_id}' chưa được cài trên máy này.",
                "skill_id": skill_id,
            }

        local_path = Path(str(installed.get("local_path") or "")).expanduser()
        if not local_path.is_dir():
            return {
                "success": False,
                "code": "SKILL_PATH_INVALID",
                "message": f"Thư mục skill '{skill_id}' không còn tồn tại: {local_path}",
                "skill_id": skill_id,
            }

        function_defs = self.get_installed_skill_tool_functions(include_invalid=False)
        normalized_name = self._safe_tool_function_name(skill_id, function_name)
        target = None
        for item in function_defs:
            if str(item.get("name") or "").strip() == normalized_name:
                target = item
                break
        if not target:
            return {
                "success": False,
                "code": "FUNCTION_NOT_FOUND",
                "message": f"Skill '{skill_id}' không expose function '{function_name}'.",
                "skill_id": skill_id,
                "function_name": function_name,
            }

        execution_target = target.get("execution_target") if isinstance(target.get("execution_target"), dict) else {}
        entrypoint = str(execution_target.get("entrypoint") or "").strip()
        timeout_seconds = float(execution_target.get("timeout_seconds") or 0.0) or None
        required_capabilities = self._normalize_capabilities(target.get("required_capabilities", []))

        return self.execute_skill_action(
            skill_id=skill_id,
            action_id=f"run_skill_function:{function_name}",
            payload=arguments or {},
            required_capabilities=required_capabilities,
            runner=lambda run_payload: self._run_installed_skill_process(
                skill_id=skill_id,
                skill_dir=local_path,
                payload=run_payload,
                entrypoint=entrypoint,
                timeout_seconds=timeout_seconds,
            ),
            auto_request_permissions=auto_request_permissions,
        )

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
        return self.conversation_orchestrator.build_context(
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
        return ConfigManager.get_api_base_url()

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

    def fetch_marketplace_skills(self, page: int = 1, per_page: int = 50) -> dict:
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
            resp = request_with_retry("GET", url, params=params, headers=headers, timeout=20, max_attempts=4)
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
                "effective_price": data.get("effective_price", r.get("price", 0)),
                "author": data.get("author", r.get("author") or ""),
                "version": data.get("version", r.get("version") or ""),
                "is_vip": bool(r.get("is_vip")),
                "icon": data.get("icon", "🧩"),
                "badge": data.get("badge", "SKILL"),
                "color": data.get("color", "#3B82F6"),
                "download_url": data.get("download_url", ""),
                "is_owned": bool(data.get("is_owned", False)),
                "requires_purchase": bool(data.get("requires_purchase", False)),
                "pricing": data.get("pricing", {}),
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
            resp = request_with_retry(
                "POST",
                url,
                json={"license_key": license_key},
                headers=headers,
                timeout=20,
                max_attempts=4,
            )
            data = self._safe_json(resp)
            if resp.status_code == 200:
                return {
                    "success": True,
                    "message": data.get("message", "Đã cấp quyền skill."),
                    "pricing": data.get("pricing"),
                }

            code = str(data.get("code", "")).strip().upper()
            if code in {"PAYMENT_REQUIRED", "PAYMENT_PENDING"}:
                payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
                default_msg = "Skill trả phí. Vui lòng thanh toán để tiếp tục."
                return {
                    "success": False,
                    "code": code,
                    "message": data.get("message") or default_msg,
                    "payment": payment,
                    "pricing": data.get("pricing"),
                }

            return {"success": False, "message": self._response_error_message(resp, data, "Không thể cấp quyền skill.")}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_payment_order_status(self, order_id: str) -> dict:
        order_id = str(order_id or "").strip()
        if not order_id:
            return {"success": False, "message": "Thiếu order id."}

        license_key = self._license_key()
        if not license_key:
            return {"success": False, "message": "Thiếu license key để kiểm tra thanh toán."}

        url = f"{self.api_base_url}/api/v1/omnimind/payments/orders/{order_id}"
        headers = {"Accept": "application/json"}
        params = {"license_key": license_key}
        try:
            resp = request_with_retry("GET", url, params=params, headers=headers, timeout=20, max_attempts=4)
            data = self._safe_json(resp)
            if resp.status_code != 200:
                return {
                    "success": False,
                    "message": self._response_error_message(
                        resp, data, "Không kiểm tra được trạng thái thanh toán."
                    ),
                }

            order = data.get("order")
            if not isinstance(order, dict):
                return {"success": False, "message": "Response payment order không hợp lệ."}
            return {"success": True, "order": order}
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
            resolve_resp = request_with_retry("GET", download_url, params=params, headers=headers, timeout=20, max_attempts=4)
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
                with request_with_retry(
                    "GET",
                    artifact_url,
                    stream=True,
                    timeout=60,
                    max_attempts=4,
                ) as r:
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
                tool_manifest = self._read_tool_manifest(candidate)
                tool_functions = tool_manifest.get("functions") if isinstance(tool_manifest.get("functions"), list) else []
                tool_function_count = 0
                tool_manifest_warnings: list[str] = []
                for item in tool_functions:
                    normalized, error = self._normalize_skill_tool_function(skill_id, candidate, item)
                    if error:
                        tool_manifest_warnings.append(error)
                        continue
                    if normalized:
                        tool_function_count += 1

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
                "tool_function_count": tool_function_count,
                "tool_manifest_warnings": tool_manifest_warnings,
                "permission_preflight": preflight,
            }
            if tool_function_count:
                result["message"] += f" Skill này expose {tool_function_count} function cho AI trung tâm."
            if tool_manifest_warnings:
                result["message"] += " Một số function trong tool_manifest.json bị bỏ qua do không hợp lệ."
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
