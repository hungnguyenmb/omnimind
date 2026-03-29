from __future__ import annotations

import json
import os
import platform
import fnmatch
import shlex
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from engine.action_executor import ActionExecutor
from engine.config_manager import ConfigManager
from engine.function_registry import FunctionRegistry
from engine.skill_manager import SkillManager


class FunctionExecutor:
    """
    Executor cho built-in functions của OmniMind.
    Sprint 4 ưu tiên hàm local an toàn và bọc lại built-in runtime actions sẵn có.
    """

    DANGEROUS_SHELL_TOKENS = ("&&", "||", ";", "|", ">", "<", "$(", "`")
    SAFE_SHELL_PREFIXES = (
        "pwd",
        "ls",
        "dir",
        "find",
        "find ",
        "cat",
        "type",
        "head",
        "tail",
        "wc",
        "stat",
        "echo",
        "whoami",
        "uname",
        "python --version",
        "python3 --version",
        "node --version",
        "git status",
        "git rev-parse",
        "git branch",
        "rg --files",
        "rg --files ",
        "rg ",
        "rg",
    )

    def __init__(
        self,
        registry: FunctionRegistry | None = None,
        action_executor: ActionExecutor | None = None,
        skill_manager: SkillManager | None = None,
    ):
        self.action_executor = action_executor or ActionExecutor()
        self.skill_manager = skill_manager or getattr(registry, "skill_manager", None) or SkillManager()
        self.registry = registry or FunctionRegistry(skill_manager=self.skill_manager)
        if getattr(self.registry, "skill_manager", None) is None:
            self.registry.skill_manager = self.skill_manager

    @staticmethod
    def _safe_json(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return "{}"

    @staticmethod
    def _normalize_path(raw_path: str) -> Path:
        return Path(os.path.expanduser(str(raw_path or "").strip()))

    @staticmethod
    def _preview(text: str, limit: int = 1600) -> str:
        body = str(text or "")
        if len(body) <= limit:
            return body
        return body[: max(1, limit - 1)].rstrip() + "…"

    @staticmethod
    def _normalize_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        raw = str(value or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "y", "on"}

    def _find_git_root(self, start_path: Path) -> Path | None:
        current = start_path.resolve()
        if current.is_file():
            current = current.parent
        for candidate in [current] + list(current.parents):
            if (candidate / ".git").exists():
                return candidate
        return None

    def _default_workspace_path(self, *, prefer_repo_root: bool = False) -> Path:
        candidates = []
        cfg_workspace = str(ConfigManager.get_workspace_path() or "").strip()
        if cfg_workspace:
            candidates.append(self._normalize_path(cfg_workspace))
        candidates.append(Path(os.getcwd()))

        for item in candidates:
            try:
                candidate = item.resolve()
            except Exception:
                candidate = item
            if not candidate.exists():
                continue
            if candidate.is_file():
                candidate = candidate.parent
            if prefer_repo_root:
                repo_root = self._find_git_root(candidate)
                if repo_root:
                    return repo_root
            return candidate
        return Path(os.getcwd()).resolve()

    def _resolve_discovery_path(self, raw_path: str = "", *, prefer_repo_root: bool = False) -> Path:
        body = str(raw_path or "").strip()
        if body:
            candidate = self._normalize_path(body)
            if not candidate.exists():
                return candidate
            candidate = candidate.resolve()
            if candidate.is_file():
                candidate = candidate.parent
            if prefer_repo_root:
                repo_root = self._find_git_root(candidate)
                if repo_root:
                    return repo_root
            return candidate
        return self._default_workspace_path(prefer_repo_root=prefer_repo_root)

    @staticmethod
    def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            normalized = int(value)
        except Exception:
            normalized = int(default)
        return max(minimum, min(maximum, normalized))

    @staticmethod
    def _matches_discovery_pattern(name: str, rel_path: str, pattern: str) -> bool:
        raw = str(pattern or "").strip()
        if not raw:
            return True
        lowered = raw.lower()
        name_lower = name.lower()
        rel_lower = rel_path.lower()
        if any(ch in raw for ch in "*?[]"):
            return fnmatch.fnmatch(name_lower, lowered) or fnmatch.fnmatch(rel_lower, lowered)
        if lowered.startswith("."):
            return name_lower.endswith(lowered) or rel_lower.endswith(lowered)
        return lowered in name_lower or lowered in rel_lower

    def _approval_required_result(self, definition: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": False,
            "code": "APPROVAL_REQUIRED",
            "message": "Function này yêu cầu approval trước khi thực thi.",
            "data": {
                "approval_policy": str(definition.get("approval_policy") or "on-request"),
                "required_capabilities": list(definition.get("required_capabilities") or []),
                "arguments": args,
            },
            "artifacts": [],
            "approval_required": True,
            "function_name": str(definition.get("name") or "").strip(),
        }

    def _format_result(
        self,
        *,
        function_name: str,
        result: dict[str, Any] | None,
        approval_required: bool = False,
    ) -> dict[str, Any]:
        payload = dict(result or {})
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            artifacts = []
        artifact_path = str(payload.get("artifact_path") or "").strip()
        if artifact_path and artifact_path not in artifacts:
            artifacts.append(artifact_path)
        payload["artifacts"] = artifacts
        payload["approval_required"] = bool(approval_required)
        payload["function_name"] = function_name
        payload.setdefault("data", {})
        return payload

    def _run_with_audit(self, action_id: str, capabilities: list[str], runner) -> dict[str, Any]:
        return self.action_executor.execute_action(
            action_id=action_id,
            capabilities=capabilities,
            runner=runner,
        )

    def _handle_get_system_info(self, args: dict[str, Any]) -> dict[str, Any]:
        data = {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "python_version": sys.version.split()[0],
            "hostname": socket.gethostname(),
            "cwd": os.getcwd(),
            "codex_home": ConfigManager.get_codex_home(),
        }
        return {
            "success": True,
            "code": "SYSTEM_INFO_READY",
            "message": "Đã lấy thông tin hệ thống.",
            "data": data,
        }

    def _handle_get_current_workspace(self, args: dict[str, Any]) -> dict[str, Any]:
        cwd = Path(os.getcwd()).resolve()
        config_workspace_raw = str(ConfigManager.get_workspace_path() or "").strip()
        config_workspace = ""
        if config_workspace_raw:
            try:
                config_workspace = str(self._normalize_path(config_workspace_raw).resolve())
            except Exception:
                config_workspace = str(self._normalize_path(config_workspace_raw))
        repo_root = self._find_git_root(cwd)
        resolved_workspace = self._default_workspace_path(prefer_repo_root=False)
        return {
            "success": True,
            "code": "WORKSPACE_READY",
            "message": "Đã xác định workspace hiện tại.",
            "data": {
                "cwd": str(cwd),
                "workspace_path": str(resolved_workspace),
                "configured_workspace_path": config_workspace,
                "git_repo_root": str(repo_root) if repo_root else "",
                "codex_home": ConfigManager.get_codex_home(),
            },
        }

    def _handle_list_local_files(self, args: dict[str, Any]) -> dict[str, Any]:
        root_path = self._resolve_discovery_path(str(args.get("path") or "").strip(), prefer_repo_root=False)
        if not root_path.exists() or not root_path.is_dir():
            return {
                "success": False,
                "code": "INVALID_PATH",
                "message": f"Không tìm thấy thư mục để liệt kê file: {str(root_path)}",
            }

        pattern = str(args.get("pattern") or "").strip()
        max_entries = self._clamp_int(args.get("max_entries"), default=40, minimum=1, maximum=200)
        max_depth = self._clamp_int(args.get("max_depth"), default=2, minimum=0, maximum=8)
        include_dirs = self._normalize_bool(args.get("include_dirs"), default=False)

        root_depth = len(root_path.parts)
        entries: list[dict[str, Any]] = []
        total_matches = 0
        truncated = False

        for current_root, dirnames, filenames in os.walk(root_path):
            current_path = Path(current_root)
            current_depth = len(current_path.parts) - root_depth
            if current_depth >= max_depth:
                dirnames[:] = []
            dirnames.sort()
            filenames.sort()

            if include_dirs:
                for dirname in dirnames:
                    rel_path = str((current_path / dirname).relative_to(root_path))
                    if not self._matches_discovery_pattern(dirname, rel_path, pattern):
                        continue
                    total_matches += 1
                    if len(entries) < max_entries:
                        entries.append(
                            {
                                "type": "dir",
                                "name": dirname,
                                "relative_path": rel_path,
                                "path": str((current_path / dirname).resolve()),
                            }
                        )
                    else:
                        truncated = True
                        break
                if truncated:
                    break

            for filename in filenames:
                rel_path = str((current_path / filename).relative_to(root_path))
                if not self._matches_discovery_pattern(filename, rel_path, pattern):
                    continue
                total_matches += 1
                if len(entries) < max_entries:
                    entries.append(
                        {
                            "type": "file",
                            "name": filename,
                            "relative_path": rel_path,
                            "path": str((current_path / filename).resolve()),
                        }
                    )
                else:
                    truncated = True
                    break
            if truncated:
                break

        return {
            "success": True,
            "code": "FILE_LIST_READY",
            "message": "Đã liệt kê file trong thư mục.",
            "data": {
                "root_path": str(root_path.resolve()),
                "pattern": pattern,
                "max_entries": max_entries,
                "max_depth": max_depth,
                "include_dirs": include_dirs,
                "entries": entries,
                "match_count": total_matches,
                "truncated": truncated,
            },
        }

    def _collect_candidate_files(self, root_path: Path) -> list[str]:
        if shutil.which("rg"):
            try:
                proc = subprocess.run(
                    ["rg", "--files", str(root_path)],
                    capture_output=True,
                    text=True,
                    timeout=12,
                    check=False,
                )
                if proc.returncode == 0:
                    normalized: list[str] = []
                    for line in (proc.stdout or "").splitlines():
                        raw = line.strip()
                        if not raw:
                            continue
                        raw_path = Path(raw)
                        try:
                            if raw_path.is_absolute():
                                normalized.append(str(raw_path.resolve().relative_to(root_path.resolve())))
                            else:
                                full_path = (Path.cwd() / raw_path).resolve()
                                if str(full_path).startswith(str(root_path.resolve())):
                                    normalized.append(str(full_path.relative_to(root_path.resolve())))
                                else:
                                    normalized.append(raw)
                        except Exception:
                            normalized.append(raw)
                    return normalized
            except Exception:
                pass

        out: list[str] = []
        for current_root, _, filenames in os.walk(root_path):
            current_path = Path(current_root)
            filenames.sort()
            for filename in filenames:
                try:
                    out.append(str((current_path / filename).relative_to(root_path)))
                except Exception:
                    out.append(str(current_path / filename))
        return out

    def _handle_search_files_by_name(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        if not query:
            return {"success": False, "code": "INVALID_ARGS", "message": "Thiếu query để tìm file."}

        root_path = self._resolve_discovery_path(str(args.get("root_path") or "").strip(), prefer_repo_root=True)
        if not root_path.exists() or not root_path.is_dir():
            return {
                "success": False,
                "code": "INVALID_PATH",
                "message": f"Không tìm thấy thư mục gốc để tìm file: {str(root_path)}",
            }

        max_entries = self._clamp_int(args.get("max_entries"), default=40, minimum=1, maximum=200)
        candidates = self._collect_candidate_files(root_path)
        matches: list[dict[str, Any]] = []
        total_matches = 0
        truncated = False

        for rel_path in candidates:
            name = Path(rel_path).name
            if not self._matches_discovery_pattern(name, rel_path, query):
                continue
            total_matches += 1
            abs_path = root_path / rel_path
            if len(matches) < max_entries:
                matches.append(
                    {
                        "name": name,
                        "relative_path": rel_path,
                        "path": str(abs_path.resolve()),
                    }
                )
            else:
                truncated = True
                break

        return {
            "success": True,
            "code": "FILE_SEARCH_READY",
            "message": "Đã tìm file theo tên.",
            "data": {
                "root_path": str(root_path.resolve()),
                "query": query,
                "matches": matches,
                "match_count": total_matches,
                "truncated": truncated,
            },
        }

    def _handle_get_git_repo_info(self, args: dict[str, Any]) -> dict[str, Any]:
        target_path = self._resolve_discovery_path(str(args.get("path") or "").strip(), prefer_repo_root=True)
        repo_root = self._find_git_root(target_path)
        if not repo_root:
            return {
                "success": False,
                "code": "NOT_A_GIT_REPO",
                "message": f"Không xác định được git repo từ path: {str(target_path)}",
                "data": {"requested_path": str(target_path)},
            }

        include_status = self._normalize_bool(args.get("include_status"), default=True)

        def _run_git(*git_args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", "-C", str(repo_root), *git_args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        branch_proc = _run_git("rev-parse", "--abbrev-ref", "HEAD")
        branch = str(branch_proc.stdout or "").strip() if branch_proc.returncode == 0 else ""
        status_lines: list[str] = []
        if include_status:
            status_proc = _run_git("status", "--short")
            if status_proc.returncode == 0:
                status_lines = [line.rstrip() for line in (status_proc.stdout or "").splitlines() if line.strip()]

        return {
            "success": True,
            "code": "GIT_REPO_READY",
            "message": "Đã lấy thông tin git repo hiện tại.",
            "data": {
                "requested_path": str(target_path),
                "repo_root": str(repo_root),
                "branch": branch,
                "has_changes": bool(status_lines),
                "status_count": len(status_lines),
                "status_preview": status_lines[:20],
            },
        }

    def _handle_read_local_file(self, args: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(args.get("path") or "").strip()
        if not raw_path:
            return {"success": False, "code": "INVALID_ARGS", "message": "Thiếu path."}
        path_obj = self._normalize_path(raw_path)
        if not path_obj.exists() or not path_obj.is_file():
            return {"success": False, "code": "FILE_NOT_FOUND", "message": f"Không tìm thấy file: {raw_path}"}

        max_chars = int(args.get("max_chars") or ConfigManager.get_central_ai_function_read_max_chars())
        max_chars = max(200, min(50000, max_chars))
        try:
            raw_bytes = path_obj.read_bytes()
            text = raw_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            return {"success": False, "code": "FILE_READ_FAILED", "message": f"Không đọc được file: {str(e)[:200]}"}

        preview = text[:max_chars]
        truncated = len(text) > len(preview)
        return {
            "success": True,
            "code": "FILE_READ_OK",
            "message": "Đã đọc file thành công.",
            "data": {
                "path": str(path_obj.resolve()),
                "content": preview,
                "truncated": truncated,
                "char_count": len(text),
            },
        }

    def _handle_write_local_file(self, args: dict[str, Any]) -> dict[str, Any]:
        raw_path = str(args.get("path") or "").strip()
        content = str(args.get("content") or "")
        overwrite = self._normalize_bool(args.get("overwrite"), default=False)
        if not raw_path:
            return {"success": False, "code": "INVALID_ARGS", "message": "Thiếu path."}
        path_obj = self._normalize_path(raw_path)
        if path_obj.exists() and not overwrite:
            return {
                "success": False,
                "code": "FILE_EXISTS",
                "message": "File đã tồn tại. Cần overwrite=true để ghi đè.",
            }
        try:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            path_obj.write_text(content, encoding="utf-8")
            resolved = str(path_obj.resolve())
        except Exception as e:
            return {"success": False, "code": "FILE_WRITE_FAILED", "message": f"Không ghi được file: {str(e)[:200]}"}
        return {
            "success": True,
            "code": "FILE_WRITE_OK",
            "message": "Đã ghi file thành công.",
            "artifact_path": resolved,
            "data": {
                "path": resolved,
                "char_count": len(content),
            },
        }

    def _is_shell_command_safe(self, command: str) -> tuple[bool, str]:
        body = str(command or "").strip()
        if not body:
            return False, "Thiếu command."
        if any(token in body for token in self.DANGEROUS_SHELL_TOKENS):
            return False, "Lệnh chứa token shell nguy hiểm."
        lowered = body.lower()
        for prefix in self.SAFE_SHELL_PREFIXES:
            if lowered == prefix or lowered.startswith(prefix + " "):
                return True, ""
        return False, "Lệnh chưa nằm trong allowlist an toàn của Sprint 4."

    def _handle_run_shell_command(self, args: dict[str, Any]) -> dict[str, Any]:
        command = str(args.get("command") or "").strip()
        ok, reason = self._is_shell_command_safe(command)
        if not ok:
            return {"success": False, "code": "SHELL_BLOCKED", "message": reason}

        cwd = str(args.get("cwd") or "").strip() or os.getcwd()
        cwd_path = self._normalize_path(cwd)
        if not cwd_path.exists() or not cwd_path.is_dir():
            return {"success": False, "code": "INVALID_CWD", "message": f"Không tìm thấy thư mục làm việc: {cwd}"}

        timeout = int(args.get("timeout_seconds") or ConfigManager.get_central_ai_function_shell_timeout_sec())
        timeout = max(3, min(60, timeout))
        max_output = ConfigManager.get_central_ai_function_shell_max_output_chars()

        try:
            proc = subprocess.run(
                shlex.split(command),
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except Exception as e:
            return {"success": False, "code": "SHELL_FAILED", "message": f"Không chạy được command: {str(e)[:200]}"}

        stdout = self._preview(proc.stdout or "", limit=max_output)
        stderr = self._preview(proc.stderr or "", limit=max_output)
        success = proc.returncode == 0
        return {
            "success": success,
            "code": "SHELL_OK" if success else "SHELL_NONZERO",
            "message": "Command đã chạy xong." if success else f"Command trả mã {proc.returncode}.",
            "data": {
                "command": command,
                "cwd": str(cwd_path.resolve()),
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            },
        }

    def _handle_builtin_action(self, action_id: str, args: dict[str, Any]) -> dict[str, Any]:
        return self.skill_manager.execute_builtin_skill_action(
            skill_id="omnimind-runtime",
            action_id=action_id,
            payload=args,
            auto_request_permissions=False,
        )

    def _resolve_definition(self, function_name: str) -> dict[str, Any] | None:
        direct = self.registry.get_definition(function_name)
        if direct:
            return direct

        key = str(function_name or "").strip()
        for item in self.registry.list_definitions():
            if str(item.get("name") or "").strip() == key:
                return item
            if str(item.get("original_name") or "").strip() == key:
                return item

        for item in self.skill_manager.get_installed_skill_tool_functions(include_invalid=False):
            if str(item.get("name") or "").strip() == key:
                return item
            if str(item.get("original_name") or "").strip() == key:
                return item
        return None

    def execute_function(
        self,
        function_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        definition = self._resolve_definition(function_name)
        if not definition:
            return self._format_result(
                function_name=str(function_name or "").strip(),
                result={
                    "success": False,
                    "code": "FUNCTION_NOT_FOUND",
                    "message": f"Không tìm thấy function: {function_name}",
                    "data": {},
                },
            )

        args = arguments if isinstance(arguments, dict) else {}
        approval_policy = str(definition.get("approval_policy") or "auto").strip().lower()
        if approval_policy != "auto" and not auto_approve:
            return self._format_result(
                function_name=str(definition.get("name") or "").strip(),
                result=self._approval_required_result(definition, args),
                approval_required=True,
            )

        execution_target = definition.get("execution_target") or {}
        capabilities = list(definition.get("required_capabilities") or [])
        handler_kind = str(execution_target.get("kind") or "builtin").strip().lower()
        handler_name = str(execution_target.get("handler") or "").strip()
        action_id = str(execution_target.get("action_id") or "").strip()
        skill_id = str(execution_target.get("skill_id") or "").strip()
        original_function_name = str(execution_target.get("function_name") or "").strip()
        audit_action_id = f"function:{definition.get('name')}"

        def runner():
            if handler_kind == "builtin":
                if handler_name == "get_system_info":
                    return self._handle_get_system_info(args)
                if handler_name == "get_current_workspace":
                    return self._handle_get_current_workspace(args)
                if handler_name == "list_local_files":
                    return self._handle_list_local_files(args)
                if handler_name == "search_files_by_name":
                    return self._handle_search_files_by_name(args)
                if handler_name == "get_git_repo_info":
                    return self._handle_get_git_repo_info(args)
                if handler_name == "read_local_file":
                    return self._handle_read_local_file(args)
                if handler_name == "write_local_file":
                    return self._handle_write_local_file(args)
                if handler_name == "run_shell_command":
                    return self._handle_run_shell_command(args)
                return {
                    "success": False,
                    "code": "HANDLER_NOT_FOUND",
                    "message": f"Thiếu handler cho function: {handler_name}",
                }
            if handler_kind == "builtin_action":
                return self._handle_builtin_action(action_id, args)
            if handler_kind == "skill_function":
                return self.skill_manager.execute_installed_skill_function(
                    skill_id=skill_id,
                    function_name=original_function_name,
                    arguments=args,
                    auto_request_permissions=False,
                )
            return {
                "success": False,
                "code": "UNSUPPORTED_EXECUTION_TARGET",
                "message": f"Execution target không hỗ trợ: {handler_kind}",
            }

        result = self._run_with_audit(audit_action_id, capabilities, runner)
        return self._format_result(
            function_name=str(definition.get("name") or "").strip(),
            result=result,
            approval_required=False,
        )

    def build_tool_message_content(self, result: dict[str, Any]) -> str:
        return self._safe_json(result or {})
