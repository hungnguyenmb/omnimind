import os
import shutil
import platform
import subprocess
import logging
import re
import json
import hashlib
import urllib.request
import zipfile
import tarfile
import time
from pathlib import Path
from typing import Callable, Optional
from engine.config_manager import ConfigManager
from engine.http_client import request_with_retry

logger = logging.getLogger(__name__)
_RUNTIME_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._@+-]+$")

DEFAULT_API_BASE_URL = "https://license.vinhyenit.com"
DEFAULT_RELEASE_MANIFEST = {
    "version": "1.5.0",
    "prerequisites": {"python": ">=3.9", "node": ">=18.0"},
    "matrix": {
        "darwin": {
            "arm64": {
                "url": "https://github.com/Antigravity-AI/codex-cli/releases/download/v1.5.0/codex-macos-arm64.zip",
                "method": "zip_extract",
            }
        },
        "win32": {
            "x64": {
                "url": "https://github.com/Antigravity-AI/codex-cli/releases/download/v1.5.0/codex-windows-x64.zip",
                "method": "zip_extract",
            }
        },
    },
    "platforms": {
        "darwin": {
            "url": "https://github.com/Antigravity-AI/codex-cli/releases/download/v1.5.0/codex-macos-arm64.zip",
            "method": "zip_extract",
        },
        "win32": {
            "url": "https://github.com/Antigravity-AI/codex-cli/releases/download/v1.5.0/codex-windows-x64.zip",
            "method": "zip_extract",
        },
    },
    # Remote config có thể override các key này từ server.
    "install_policy": {
        "auto_install_runtime": True,
        "windows": {
            "python_package_id": "Python.Python.3.11",
            "node_package_id": "OpenJS.NodeJS",
        },
        "darwin": {
            "python_formula": "python",
            "node_formula": "node",
        },
    },
}

class EnvironmentManager:
    """
    Quản lý việc kiểm tra, cài đặt và cấu hình môi trường chạy AI 
    (Python, Node, npm, OmniMind) tương thích Cross-Platform (macOS / Windows).
    """
    
    def __init__(self):
        self.os_name = platform.system()
        self.app_data_dir = self._get_app_data_dir()
        self.codex_home = Path(ConfigManager.get_codex_home())
        self.codex_home.mkdir(parents=True, exist_ok=True)
        self.last_install_error = ""
        # Chuẩn hóa CODEX_HOME xuyên suốt runtime.
        os.environ["CODEX_HOME"] = str(self.codex_home)
        # Persist để lần chạy sau không lệch path giữa các module.
        ConfigManager.set_codex_home(str(self.codex_home))
        self.codex_bin_dir = self.app_data_dir / "bin"
        self.codex_bin_dir.mkdir(parents=True, exist_ok=True)
        
        # Đưa thư mục bin cục bộ vào PATH tạm thời cho phiên chạy
        os.environ["PATH"] = f"{str(self.codex_bin_dir)}{os.pathsep}{os.environ.get('PATH', '')}"
        # Finder launch trên macOS thường không nạp shell PATH, cần thêm path tool chuẩn.
        self._ensure_macos_tool_paths()
        self._ensure_windows_tool_paths()

    def _prepend_path_once(self, path_value: str) -> None:
        path_value = str(path_value or "").strip()
        if not path_value:
            return
        current_parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
        if path_value in current_parts:
            return
        os.environ["PATH"] = os.pathsep.join([path_value] + current_parts)

    def _ensure_macos_tool_paths(self) -> None:
        if self.os_name != "Darwin":
            return
        # Ưu tiên path theo kiến trúc máy, vẫn giữ fallback path còn lại.
        machine = (platform.machine() or "").lower()
        if "arm" in machine or "aarch" in machine:
            preferred = ["/opt/homebrew/bin", "/usr/local/bin"]
        else:
            preferred = ["/usr/local/bin", "/opt/homebrew/bin"]
        for candidate in reversed(preferred):
            if Path(candidate).exists():
                self._prepend_path_once(candidate)

    def _ensure_windows_tool_paths(self) -> None:
        if self.os_name != "Windows":
            return
        for p in self._windows_runtime_search_paths():
            if Path(p).exists():
                self._prepend_path_once(str(p))

    @staticmethod
    def _is_windowsapps_alias(path_value: str) -> bool:
        p = str(path_value or "").replace("/", "\\").lower()
        return "\\microsoft\\windowsapps\\" in p

    @staticmethod
    def _parse_python_major(version_text: str) -> int:
        txt = str(version_text or "")
        m = re.search(r"python\s+(\d+)\.", txt, flags=re.IGNORECASE)
        if not m:
            return -1
        try:
            return int(m.group(1))
        except Exception:
            return -1

    def _run_probe(self, cmd: list[str], timeout: int = 4) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
            output = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
            return result.returncode == 0, output
        except Exception as e:
            return False, str(e)

    def _windows_runtime_search_paths(self) -> list[Path]:
        paths: list[Path] = []
        for env_key in ("ProgramFiles", "ProgramFiles(x86)"):
            base = Path(os.environ.get(env_key, ""))
            if base:
                paths.append(base / "nodejs")
        local_app = Path(os.environ.get("LOCALAPPDATA", ""))
        if local_app:
            paths.append(local_app / "Programs" / "nodejs")
            py_root = local_app / "Programs" / "Python"
            paths.extend(sorted(py_root.glob("Python*"), reverse=True))
        return [p for p in paths if str(p).strip()]

    def _iter_windows_python_candidates(self) -> list[list[str]]:
        commands: list[list[str]] = []
        seen: set[str] = set()

        def add(cmd: list[str]):
            key = " ".join(cmd).lower()
            if key in seen:
                return
            seen.add(key)
            commands.append(cmd)

        for cmd_name in ("python3", "python"):
            resolved = shutil.which(cmd_name)
            if resolved and not self._is_windowsapps_alias(resolved):
                add([resolved, "--version"])

        local_app = Path(os.environ.get("LOCALAPPDATA", ""))
        if local_app:
            py_root = local_app / "Programs" / "Python"
            for exe in sorted(py_root.glob("Python*/python.exe"), reverse=True):
                if exe.is_file():
                    add([str(exe), "--version"])

        for env_key in ("ProgramFiles", "ProgramFiles(x86)"):
            base = Path(os.environ.get(env_key, ""))
            if not str(base):
                continue
            for exe in sorted(base.glob("Python*/python.exe"), reverse=True):
                if exe.is_file():
                    add([str(exe), "--version"])

        py_launcher = shutil.which("py") or str(Path(os.environ.get("WINDIR", "C:\\Windows")) / "py.exe")
        if py_launcher and Path(py_launcher).exists():
            add([py_launcher, "-3", "-V"])
            add([py_launcher, "-V"])

        # Fallback cuối cùng: thử command name chuẩn.
        add(["python", "--version"])
        add(["python3", "--version"])
        return commands

    def _is_python_available(self) -> bool:
        if self.os_name == "Windows":
            for cmd in self._iter_windows_python_candidates():
                ok, output = self._run_probe(cmd, timeout=5)
                if not ok:
                    continue
                major = self._parse_python_major(output)
                if major >= 3:
                    return True
            return False

        for cmd in (["python3", "--version"], ["python", "--version"]):
            ok, output = self._run_probe(cmd, timeout=4)
            if not ok:
                continue
            major = self._parse_python_major(output)
            if major >= 3:
                return True
        return False

    def _iter_windows_binary_candidates(self, base_name: str, exts: list[str]) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(path_value: str):
            key = str(path_value or "").strip().lower()
            if not key or key in seen:
                return
            seen.add(key)
            candidates.append(path_value)

        resolved = shutil.which(base_name)
        if resolved:
            add(resolved)

        for base in self._windows_runtime_search_paths():
            for ext in exts:
                exe = base / f"{base_name}{ext}"
                if exe.is_file():
                    add(str(exe))

        # fallback command name
        add(base_name)
        return candidates

    def _is_node_available(self) -> bool:
        if self.os_name == "Windows":
            for node_bin in self._iter_windows_binary_candidates("node", [".exe"]):
                ok, output = self._run_probe([node_bin, "--version"], timeout=4)
                if ok and re.search(r"v?\d+\.\d+\.\d+", output):
                    return True
            return False

        ok, output = self._run_probe(["node", "--version"], timeout=4)
        return bool(ok and re.search(r"v?\d+\.\d+\.\d+", output))

    def _is_npm_available(self) -> bool:
        if self.os_name == "Windows":
            for npm_bin in self._iter_windows_binary_candidates("npm", [".cmd", ".exe", ".bat"]):
                ok, output = self._run_probe([npm_bin, "--version"], timeout=4)
                if ok and re.search(r"\d+\.\d+\.\d+", output):
                    return True
            return False

        ok, output = self._run_probe(["npm", "--version"], timeout=4)
        return bool(ok and re.search(r"\d+\.\d+\.\d+", output))

    def _normalize_codex_binary_name(self) -> Path | None:
        target_name = "codex.exe" if self.os_name == "Windows" else "codex"
        target_path = self.codex_bin_dir / target_name
        if target_path.exists():
            return target_path

        candidates: list[Path] = []
        for root, _, files in os.walk(self.codex_bin_dir):
            for file_name in files:
                lower = file_name.lower()
                p = Path(root) / file_name
                if self.os_name == "Windows":
                    if lower.startswith("codex") and lower.endswith(".exe"):
                        # Bỏ các helper exe không phải CLI chính
                        if "command-runner" in lower or "sandbox-setup" in lower:
                            continue
                        candidates.append(p)
                else:
                    if lower == "codex" or lower.startswith("codex-") or lower.startswith("codex_"):
                        candidates.append(p)

        if not candidates:
            return None

        # Ưu tiên file nằm gần root bin dir và tên "gần chuẩn" nhất.
        def score(path_obj: Path) -> tuple[int, int]:
            name = path_obj.name.lower()
            dist = len(path_obj.parts)
            if name == target_name:
                return (0, dist)
            if name.startswith("codex-"):
                return (1, dist)
            return (2, dist)

        selected = sorted(candidates, key=score)[0]
        try:
            shutil.copy2(selected, target_path)
            if self.os_name != "Windows":
                os.chmod(target_path, 0o755)
            logger.info(f"Normalized OmniMind binary: {selected} -> {target_path}")
            return target_path
        except Exception as e:
            logger.warning(f"Cannot normalize OmniMind binary name from {selected}: {e}")
            return selected

    def _find_working_codex_command(self) -> str:
        local_names = ["codex.exe", "codex"] if self.os_name == "Windows" else ["codex"]

        # Ưu tiên binary local trong app data dir.
        for name in local_names:
            path = shutil.which(name, path=str(self.codex_bin_dir))
            if path:
                ok, _ = self._run_probe([path, "--version"], timeout=5)
                if ok:
                    return path

        # Fallback system PATH.
        for name in local_names:
            path = shutil.which(name)
            if path:
                ok, _ = self._run_probe([path, "--version"], timeout=5)
                if ok:
                    return path

        # Last resort: literal command for later error display.
        return "codex.exe" if self.os_name == "Windows" else "codex"

    def _resolve_brew_path(self) -> str:
        if self.os_name != "Darwin":
            return ""
        brew_path = shutil.which("brew")
        if brew_path:
            return brew_path
        machine = (platform.machine() or "").lower()
        candidates = (
            ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
            if ("arm" in machine or "aarch" in machine)
            else ["/usr/local/bin/brew", "/opt/homebrew/bin/brew"]
        )
        for candidate in candidates:
            if Path(candidate).is_file() and os.access(candidate, os.X_OK):
                return candidate
        return ""

    def _codex_env(self) -> dict:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        sandbox_mode = ConfigManager.get_sandbox_mode()
        approval_policy = ConfigManager.get_codex_approval_policy()
        model = ConfigManager.get_codex_model()
        # Dùng biến env để các lệnh Codex/bot engine downstream có thể đọc cùng 1 cấu hình sandbox.
        env["OMNIMIND_SANDBOX_MODE"] = sandbox_mode
        env["CODEX_SANDBOX_MODE"] = sandbox_mode
        env["OMNIMIND_APPROVAL_POLICY"] = approval_policy
        env["CODEX_APPROVAL_POLICY"] = approval_policy
        env["OMNIMIND_CODEX_MODEL"] = model
        return env

    def get_codex_config_path(self) -> Path:
        return self.codex_home / "config.toml"

    @staticmethod
    def _unquote_toml_string(raw: str) -> str:
        value = (raw or "").strip()
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            try:
                return json.loads(value)
            except Exception:
                return value[1:-1]
        return value

    @classmethod
    def _parse_root_toml_values(cls, text: str, keys: set[str]) -> dict:
        out = {}
        in_table = False
        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("[") and stripped.endswith("]"):
                in_table = True
                continue
            if in_table:
                continue
            if "=" not in stripped:
                continue
            key_part, value_part = stripped.split("=", 1)
            key = key_part.strip()
            if key not in keys:
                continue
            value_raw = value_part.split("#", 1)[0].strip()
            out[key] = cls._unquote_toml_string(value_raw)
        return out

    @staticmethod
    def _escape_toml_string(value: str) -> str:
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    @classmethod
    def _upsert_root_toml_values(cls, text: str, updates: dict) -> str:
        lines = (text or "").splitlines()
        first_table_idx = next(
            (i for i, line in enumerate(lines) if line.strip().startswith("[") and line.strip().endswith("]")),
            len(lines),
        )
        root_lines = lines[:first_table_idx]
        table_lines = lines[first_table_idx:]

        normalized_keys = set(updates.keys())
        filtered_root = []
        for line in root_lines:
            stripped = line.strip()
            if not stripped:
                filtered_root.append(line)
                continue
            if "=" in stripped:
                maybe_key = stripped.split("=", 1)[0].strip()
                if maybe_key in normalized_keys:
                    continue
            filtered_root.append(line)

        insert_lines = [f'{k} = "{cls._escape_toml_string(v)}"' for k, v in updates.items()]
        anchor = 0
        while anchor < len(filtered_root):
            s = filtered_root[anchor].strip()
            if not s or s.startswith("#"):
                anchor += 1
                continue
            break

        new_root = filtered_root[:anchor] + insert_lines + [""] + filtered_root[anchor:]
        final_lines = new_root + table_lines
        # Loại bớt dòng trống thừa cuối file.
        while final_lines and not final_lines[-1].strip():
            final_lines.pop()
        return "\n".join(final_lines) + "\n"

    def read_codex_cli_preferences(self) -> dict:
        cfg = {
            "model": ConfigManager.get_codex_model(),
            "sandbox_mode": ConfigManager.get_sandbox_mode(),
            "approval_policy": ConfigManager.get_codex_approval_policy(),
            "config_path": str(self.get_codex_config_path()),
            "source": "sqlite",
        }
        config_path = self.get_codex_config_path()
        try:
            if not config_path.exists():
                return cfg

            text = config_path.read_text(encoding="utf-8", errors="ignore")
            parsed = self._parse_root_toml_values(text, {"model", "sandbox_mode", "approval_policy"})

            model = str(parsed.get("model", "")).strip() or cfg["model"]
            sandbox_mode = str(parsed.get("sandbox_mode", "")).strip()
            approval_policy = str(parsed.get("approval_policy", "")).strip()

            if sandbox_mode not in {"read-only", "workspace-write", "danger-full-access"}:
                sandbox_mode = cfg["sandbox_mode"]
            if approval_policy not in {"untrusted", "on-request", "never", "on-failure"}:
                approval_policy = cfg["approval_policy"]

            cfg.update(
                {
                    "model": model,
                    "sandbox_mode": sandbox_mode,
                    "approval_policy": approval_policy,
                    "source": "config.toml",
                }
            )
            return cfg
        except Exception as e:
            logger.warning(f"Cannot read Codex config.toml: {e}")
            return cfg

    def write_codex_cli_preferences(self, model: str, sandbox_mode: str, approval_policy: str) -> dict:
        model = str(model or "").strip() or "gpt-5.3-codex"
        sandbox_mode = str(sandbox_mode or "").strip()
        approval_policy = str(approval_policy or "").strip()

        if sandbox_mode not in {"read-only", "workspace-write", "danger-full-access"}:
            return {"success": False, "message": f"Sandbox mode không hợp lệ: {sandbox_mode}"}
        if approval_policy not in {"untrusted", "on-request", "never", "on-failure"}:
            return {"success": False, "message": f"Approval policy không hợp lệ: {approval_policy}"}

        config_path = self.get_codex_config_path()
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            old_text = ""
            if config_path.exists():
                old_text = config_path.read_text(encoding="utf-8", errors="ignore")

            new_text = self._upsert_root_toml_values(
                old_text,
                {
                    "model": model,
                    "sandbox_mode": sandbox_mode,
                    "approval_policy": approval_policy,
                },
            )
            config_path.write_text(new_text, encoding="utf-8")

            ConfigManager.set_codex_model(model)
            ConfigManager.set_sandbox_mode(sandbox_mode)
            ConfigManager.set_codex_approval_policy(approval_policy)

            return {
                "success": True,
                "message": "Đã lưu cấu hình OmniMind.",
                "config_path": str(config_path),
                "model": model,
                "sandbox_mode": sandbox_mode,
                "approval_policy": approval_policy,
            }
        except Exception as e:
            logger.exception("Cannot write Codex config.toml")
            return {"success": False, "message": f"Không thể lưu config.toml: {str(e)[:120]}"}

    @staticmethod
    def _emit_progress(progress_callback: Optional[Callable[[int, str], None]], percent: int, message: str):
        if not progress_callback:
            return
        try:
            bounded = max(0, min(100, int(percent)))
            progress_callback(bounded, message)
        except Exception:
            pass

    @staticmethod
    def _summarize_subprocess_error(err: subprocess.CalledProcessError) -> str:
        stderr = str(getattr(err, "stderr", "") or "").strip()
        stdout = str(getattr(err, "output", "") or "").strip()
        raw = stderr or stdout or str(err)
        first_line = next((ln.strip() for ln in raw.splitlines() if ln.strip()), raw)
        return first_line[:220]

    def _run_command_with_progress(
        self,
        cmd: list[str],
        *,
        progress_callback: Optional[Callable[[int, str], None]],
        start_percent: int,
        end_percent: int,
        start_message: str,
        waiting_message: str,
        env: Optional[dict] = None,
        timeout_seconds: int = 1800,
    ) -> subprocess.CompletedProcess:
        """
        Chạy subprocess kiểu non-interactive và đẩy tiến trình heartbeat để UI không đứng yên.
        """
        self._emit_progress(progress_callback, start_percent, start_message)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        start_ts = time.time()
        next_beat = start_ts + 3
        current_percent = int(start_percent)
        bounded_end = max(current_percent, int(end_percent))
        dot = 0

        while process.poll() is None:
            now = time.time()
            if now - start_ts > timeout_seconds:
                process.kill()
                process.wait(timeout=5)
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_seconds)
            if now >= next_beat:
                if current_percent < bounded_end:
                    current_percent += 1
                dot = (dot + 1) % 4
                self._emit_progress(
                    progress_callback,
                    current_percent,
                    f"{waiting_message}{'.' * dot}",
                )
                next_beat = now + 3
            time.sleep(0.2)

        stdout, stderr = process.communicate()
        completed = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode,
                cmd,
                output=stdout,
                stderr=stderr,
            )
        return completed

    def _resolve_codex_cmd(self) -> str:
        """Ưu tiên codex đã cài local trong app, fallback system PATH."""
        return self._find_working_codex_command()

    def resolve_codex_command(self) -> str:
        """Public wrapper để các runtime services dùng cùng chiến lược resolve codex binary."""
        return self._resolve_codex_cmd()

    def get_codex_env(self) -> dict:
        """Public wrapper để đồng bộ env runtime Codex (CODEX_HOME/model/sandbox/approval)."""
        return self._codex_env()

    @staticmethod
    def _sanitize_runtime_token(token: str, field_name: str) -> str:
        val = str(token or "").strip()
        if not val or not _RUNTIME_TOKEN_PATTERN.fullmatch(val):
            raise ValueError(f"{field_name} không hợp lệ.")
        return val

    def get_platform_key(self) -> str:
        """Chuẩn hóa platform key cho manifest release."""
        if self.os_name == "Darwin":
            return "darwin"
        if self.os_name == "Windows":
            return "win32"
        if self.os_name == "Linux":
            return "linux"
        return "unknown"

    @staticmethod
    def normalize_arch_key(raw_arch: str) -> str:
        arch = str(raw_arch or "").strip().lower()
        mapping = {
            "x86_64": "x64",
            "amd64": "x64",
            "x64": "x64",
            "i386": "x86",
            "i686": "x86",
            "aarch64": "arm64",
            "arm64": "arm64",
            "armv7l": "armv7",
            "armv6l": "armv6",
        }
        return mapping.get(arch, arch or "unknown")

    def get_arch_key(self) -> str:
        return self.normalize_arch_key(platform.machine())

    @staticmethod
    def _normalize_release_entry(entry) -> dict:
        if isinstance(entry, str):
            url = entry.strip()
            return {"url": url} if url else {}
        if isinstance(entry, dict):
            url = str(entry.get("url", "")).strip()
            if not url:
                return {}
            out = {
                "url": url,
                "method": str(entry.get("method", "zip_extract")).strip() or "zip_extract",
                "checksum": str(entry.get("checksum") or entry.get("sha256") or "").strip(),
                "file_name": str(entry.get("file_name") or entry.get("filename") or "").strip(),
            }
            size_val = entry.get("size")
            try:
                out["size"] = int(size_val) if size_val is not None else None
            except Exception:
                out["size"] = None
            return out
        return {}

    def resolve_codex_download_info(self, manifest: dict | None = None) -> dict:
        data = manifest or {}
        platform_key = self.get_platform_key()
        arch_key = self.get_arch_key()

        selected = self._normalize_release_entry(data.get("selected", {}))
        if selected.get("url"):
            selected["platform"] = str(data.get("platform", platform_key) or platform_key)
            selected["arch"] = self.normalize_arch_key(str(data.get("arch", arch_key)))
            return selected

        matrix = data.get("matrix", {}) if isinstance(data.get("matrix"), dict) else {}
        platform_map = matrix.get(platform_key, {}) if isinstance(matrix.get(platform_key), dict) else {}
        exact = self._normalize_release_entry(platform_map.get(arch_key))
        if exact.get("url"):
            exact["platform"] = platform_key
            exact["arch"] = arch_key
            return exact

        # Fallback theo thứ tự ưu tiên kiến trúc phổ biến.
        fallback_arches = ["x64", "arm64", "x86"]
        for fallback_arch in fallback_arches:
            candidate = self._normalize_release_entry(platform_map.get(fallback_arch))
            if candidate.get("url"):
                candidate["platform"] = platform_key
                candidate["arch"] = fallback_arch
                return candidate

        platforms = data.get("platforms", {}) if isinstance(data.get("platforms"), dict) else {}
        legacy = self._normalize_release_entry(platforms.get(platform_key))
        if legacy.get("url"):
            legacy["platform"] = platform_key
            legacy["arch"] = arch_key
            return legacy

        return {"url": "", "platform": platform_key, "arch": arch_key}

    def get_api_base_url(self) -> str:
        """
        Lấy API base URL theo thứ tự ưu tiên:
        1) ENV OMNIMIND_API_URL
        2) DB app_configs (omnimind_api_url / OMNIMIND_API_URL)
        3) Default production VPS
        """
        return ConfigManager.get_api_base_url() or DEFAULT_API_BASE_URL

    def get_runtime_installer_status(self) -> dict:
        """
        Kiểm tra công cụ cài đặt runtime tự động theo HĐH.
        - macOS: Homebrew
        - Windows: winget
        """
        if self.os_name == "Darwin":
            brew_path = self._resolve_brew_path()
            ready = bool(brew_path)
            return {
                "tool": "brew",
                "display_name": "Homebrew",
                "ready": ready,
                "message": (
                    f"Homebrew đã sẵn sàng ({brew_path})."
                    if ready
                    else "Thiếu Homebrew. Cài Homebrew trước khi cài Python/Node tự động."
                ),
                "manual_hint": '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
            }

        if self.os_name == "Windows":
            ready = shutil.which("winget") is not None
            return {
                "tool": "winget",
                "display_name": "WinGet",
                "ready": ready,
                "message": (
                    "WinGet đã sẵn sàng."
                    if ready
                    else "Thiếu WinGet (App Installer). Cài App Installer từ Microsoft Store trước."
                ),
                "manual_hint": "Cài App Installer từ Microsoft Store, sau đó mở lại ứng dụng.",
            }

        return {
            "tool": "unsupported",
            "display_name": "Unsupported",
            "ready": False,
            "message": f"HĐH {self.os_name} chưa hỗ trợ auto-install runtime.",
            "manual_hint": "Vui lòng cài Python/Node/npm thủ công.",
        }

    def fetch_codex_release_manifest(self) -> dict:
        """
        Lấy release manifest từ server; nếu lỗi sẽ fallback local defaults.
        Cơ chế hybrid này giúp hotfix link tải mà không bắt user update app.
        """
        api_url = f"{self.get_api_base_url()}/api/v1/omnimind/codex/releases"
        try:
            resp = request_with_retry(
                "GET",
                api_url,
                params={"os_name": self.get_platform_key(), "arch": self.get_arch_key()},
                timeout=10,
                max_attempts=4,
            )
            if resp.status_code == 200:
                remote = resp.json() or {}
                merged = dict(DEFAULT_RELEASE_MANIFEST)
                merged.update(remote)

                # Merge matrix theo os + arch (nếu có).
                base_matrix = json.loads(json.dumps(DEFAULT_RELEASE_MANIFEST.get("matrix", {})))
                remote_matrix = remote.get("matrix", {})
                if isinstance(remote_matrix, dict):
                    for os_key, arch_map in remote_matrix.items():
                        if not isinstance(arch_map, dict):
                            continue
                        merged_arch_map = dict(base_matrix.get(os_key, {}))
                        merged_arch_map.update(arch_map)
                        base_matrix[os_key] = merged_arch_map
                merged["matrix"] = base_matrix

                # Merge sâu cho 2 nhánh hay thay đổi.
                merged_platforms = dict(DEFAULT_RELEASE_MANIFEST.get("platforms", {}))
                merged_platforms.update(remote.get("platforms", {}))
                merged["platforms"] = merged_platforms

                remote_policy = remote.get("install_policy", {}) or remote.get("env_installers", {})
                merged_policy = dict(DEFAULT_RELEASE_MANIFEST.get("install_policy", {}))
                merged_policy.update(remote_policy)
                # Merge sâu cho nhánh per-OS để hỗ trợ remote partial override.
                for os_key in ("windows", "darwin", "linux"):
                    base_os_policy = dict(DEFAULT_RELEASE_MANIFEST.get("install_policy", {}).get(os_key, {}))
                    remote_os_policy = dict((remote_policy or {}).get(os_key, {}))
                    if base_os_policy or remote_os_policy:
                        base_os_policy.update(remote_os_policy)
                        merged_policy[os_key] = base_os_policy
                merged["install_policy"] = merged_policy
                return merged
        except Exception as e:
            logger.warning(f"Fetch codex manifest failed, fallback local: {e}")
        return dict(DEFAULT_RELEASE_MANIFEST)

    def _get_app_data_dir(self) -> Path:
        """Lấy thư mục AppData chuẩn từng HĐH."""
        if self.os_name == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            return Path(base) / "OmniMind"
        elif self.os_name == "Darwin":
            base = os.path.expanduser("~/Library/Application Support")
            return Path(base) / "OmniMind"
        else:
            return Path(os.path.expanduser("~/.omnimind"))

    def check_prerequisites(self) -> dict:
        """
        Kiểm tra xem máy đã có đủ đồ chơi chưa (Python, Node, npm, Codex).
        Trạng thái: OK, MISSING, ERROR
        """
        # Đồng bộ PATH mỗi lần check để bắt thay đổi sau cài thủ công (đặc biệt trên Windows).
        self._ensure_macos_tool_paths()
        self._ensure_windows_tool_paths()

        python_ok = self._is_python_available()
        node_ok = self._is_node_available()
        npm_ok = self._is_npm_available()

        codex_cmd = self._resolve_codex_cmd()
        codex_ok, _ = self._run_probe([codex_cmd, "--version"], timeout=5)

        status = {
            "python": "OK" if python_ok else "MISSING",
            "node": "OK" if node_ok else "MISSING",
            "npm": "OK" if npm_ok else "MISSING",
            "codex": "OK" if codex_ok else "MISSING"
        }

        runtime_ready = all(status[k] == "OK" for k in ("python", "node", "npm"))
        codex_ready = status["codex"] == "OK"

        # "is_ready" dùng cho flow Codex Auth: chỉ cần Codex.
        status["runtime_ready"] = runtime_ready
        status["codex_ready"] = codex_ready
        status["is_full_ready"] = runtime_ready and codex_ready
        status["is_ready"] = codex_ready
        return status

    def install_missing_env(
        self,
        missing_list: list,
        install_policy: dict | None = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """
        Cài đặt tự động các môi trường bị thiếu (Yêu cầu Quyền Admin/Sudo).
        """
        logger.info(f"Attempting to install missing environment: {missing_list}")
        self._emit_progress(progress_callback, 5, "Đang chuẩn bị cài đặt môi trường...")
        policy = install_policy or {}
        
        if self.os_name == "Windows":
            return self._install_env_windows(missing_list, policy.get("windows", {}), progress_callback)
        elif self.os_name == "Darwin":
            return self._install_env_macos(missing_list, policy.get("darwin", {}), progress_callback)
        else:
            logger.error("Auto-install not supported on this OS.")
            self._emit_progress(progress_callback, 100, "Hệ điều hành chưa hỗ trợ cài đặt tự động.")
            return False

    def _install_env_windows(
        self,
        missing: list,
        policy: dict | None = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """Sử dụng WinGet / PowerShell để cài âm thầm trên Windows."""
        policy = policy or {}
        try:
            # Cài đặt qua winget (có thể trigger UAC khi cần).
            actions = []
            python_pkg = self._sanitize_runtime_token(
                policy.get("python_package_id", "Python.Python.3.11"),
                "python_package_id",
            )
            node_pkg = self._sanitize_runtime_token(
                policy.get("node_package_id", "OpenJS.NodeJS"),
                "node_package_id",
            )
            if "python" in missing:
                actions.append(("Python", python_pkg))
            if "node" in missing or "npm" in missing:
                actions.append(("Node.js", node_pkg))
                
            if not actions:
                self._emit_progress(progress_callback, 100, "Môi trường đã đầy đủ.")
                return True

            step = 70 // max(1, len(actions))
            progress = 20
            for display, package_id in actions:
                self._emit_progress(
                    progress_callback,
                    progress,
                    f"Đang yêu cầu quyền quản trị Windows (UAC) để cài {display}...",
                )
                arg_list = f"install -e --id {package_id} --silent"
                logger.info(f"Running WinGet installer for {display}: {package_id}")
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        f"Start-Process -FilePath winget -ArgumentList '{arg_list}' -Verb RunAs -Wait",
                    ],
                    check=True,
                )
                progress = min(90, progress + step)

            self._emit_progress(progress_callback, 90, "Đang xác minh môi trường sau cài đặt...")
            return True
        except Exception as e:
            logger.error(f"Windows env install failed: {e}")
            self._emit_progress(progress_callback, 100, f"Cài đặt thất bại: {str(e)[:80]}")
            return False

    def _install_env_macos(
        self,
        missing: list,
        policy: dict | None = None,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """Sử dụng Homebrew trên macOS. Yêu cầu nhập pass Sudo qua GUI (tương lai)."""
        policy = policy or {}
        try:
            # Kiểm tra Brew trước
            brew_path = self._resolve_brew_path()
            if not brew_path:
                logger.error("Homebrew is missing. Cannot auto-install on macOS.")
                # TODO: Mở popup hướng dẫn cài Brew
                self._emit_progress(progress_callback, 100, "Thiếu Homebrew. Vui lòng cài Homebrew trước.")
                return False
                
            formulas = []
            python_formula = self._sanitize_runtime_token(
                policy.get("python_formula", "python"),
                "python_formula",
            )
            node_formula = self._sanitize_runtime_token(
                policy.get("node_formula", "node"),
                "node_formula",
            )
            if "python" in missing:
                formulas.append(("Python", python_formula))
            if "node" in missing or "npm" in missing:
                formulas.append(("Node.js", node_formula))
                
            if not formulas:
                self._emit_progress(progress_callback, 100, "Môi trường đã đầy đủ.")
                return True

            brew_env = os.environ.copy()
            brew_env["NONINTERACTIVE"] = "1"
            brew_env["CI"] = "1"
            brew_env.setdefault("HOMEBREW_NO_AUTO_UPDATE", "1")
            brew_env.setdefault("HOMEBREW_NO_INSTALL_CLEANUP", "1")

            step = 70 // max(1, len(formulas))
            progress = 20
            for display, formula in formulas:
                logger.info(f"Running Homebrew installer for {display}: {formula}")
                wait_text = f"Đang cài {display} bằng Homebrew (có thể mất vài phút)"
                self._run_command_with_progress(
                    [brew_path, "install", formula],
                    progress_callback=progress_callback,
                    start_percent=progress,
                    end_percent=min(88, progress + max(4, step - 1)),
                    start_message=f"Đang cài {display} bằng Homebrew...",
                    waiting_message=wait_text,
                    env=brew_env,
                    timeout_seconds=1800,
                )
                progress = min(90, progress + step)

            self._emit_progress(progress_callback, 90, "Đang xác minh môi trường sau cài đặt...")
            return True
        except subprocess.TimeoutExpired:
            logger.error("macOS env install timeout")
            self._emit_progress(
                progress_callback,
                100,
                "Cài đặt quá thời gian chờ. Homebrew có thể đang chờ quyền hoặc mạng chậm.",
            )
            return False
        except subprocess.CalledProcessError as e:
            detail = self._summarize_subprocess_error(e)
            logger.error(f"macOS env install failed: {detail}")
            self._emit_progress(progress_callback, 100, f"Cài đặt thất bại: {detail}")
            return False
        except ValueError as e:
            logger.error(f"Invalid installer policy on macOS: {e}")
            self._emit_progress(progress_callback, 100, str(e))
            return False

    def download_and_install_codex(
        self,
        download_url: str,
        expected_checksum: str = "",
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """
        Tải binary OmniMind từ Server, giải nén vào self.codex_bin_dir
        """
        logger.info(f"Downloading OmniMind from {download_url}...")
        self.last_install_error = ""
        archive_path = self.app_data_dir / "codex_temp.pkg"
        
        try:
            # Tải file
            req = urllib.request.Request(download_url, headers={'User-Agent': 'OmniMind-App'})
            self._emit_progress(progress_callback, 5, "Bắt đầu tải OmniMind...")
            with urllib.request.urlopen(req) as response, open(archive_path, 'wb') as out_file:
                total_size = int(response.headers.get("Content-Length", "0") or "0")
                downloaded = 0
                chunk_size = 1024 * 256
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = 5 + int((downloaded / total_size) * 65)
                    else:
                        pct = min(70, 5 + int(downloaded / (1024 * 1024)))
                    self._emit_progress(progress_callback, pct, "Đang tải OmniMind...")

            checksum = str(expected_checksum or "").strip().lower()
            if checksum:
                self._emit_progress(progress_callback, 72, "Đang kiểm tra checksum gói cài...")
                digest = hashlib.sha256()
                with open(archive_path, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(chunk)
                actual = digest.hexdigest().lower()
                if actual != checksum:
                    raise RuntimeError("Checksum gói OmniMind không khớp. Vui lòng thử lại.")
            
            logger.info("Extracting OmniMind...")
            self._emit_progress(progress_callback, 75, "Đang giải nén OmniMind...")
            # Giải nén
            extracted = False
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(self.codex_bin_dir)
                extracted = True
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path, 'r') as tar_ref:
                    tar_ref.extractall(self.codex_bin_dir)
                extracted = True

            if not extracted:
                raise RuntimeError("Định dạng gói OmniMind không hợp lệ (không phải zip/tar).")

            # Chuẩn hóa tên binary để kiểm tra/chạy nhất quán giữa các gói release.
            normalized_bin = self._normalize_codex_binary_name()
            if not normalized_bin:
                raise RuntimeError("Giải nén xong nhưng không tìm thấy binary OmniMind hợp lệ.")
                    
            # Cấp quyền thực thi (chmod +x) trên Mac/Linux
            if self.os_name != "Windows":
                self._emit_progress(progress_callback, 88, "Đang cấp quyền thực thi OmniMind...")
                for root, _, files in os.walk(self.codex_bin_dir):
                    for file in files:
                        os.chmod(os.path.join(root, file), 0o755)

            # Verify binary tồn tại sau khi giải nén.
            self._emit_progress(progress_callback, 95, "Đang kiểm tra binary OmniMind...")
            verify_cmd = self._resolve_codex_cmd()
            ok_verify, verify_output = self._run_probe([verify_cmd, "--version"], timeout=8)
            if not ok_verify:
                detail = (verify_output or "").splitlines()
                hint = detail[0][:140] if detail else "binary không chạy được"
                raise RuntimeError(f"Không thể chạy OmniMind CLI sau cài đặt: {hint}")
            logger.info(f"OmniMind binary verified: {verify_cmd} -> {verify_output[:80]}")

            # Dọn dẹp
            os.remove(archive_path)
            logger.info("OmniMind installed successfully.")
            self._emit_progress(progress_callback, 100, "Cài đặt OmniMind hoàn tất.")
            self.last_install_error = ""
            return True
            
        except Exception as e:
            logger.error(f"Download/Install OmniMind failed: {e}")
            self.last_install_error = f"Lỗi cài đặt OmniMind: {str(e)[:200]}"
            if archive_path.exists():
                os.remove(archive_path)
            self._emit_progress(progress_callback, 100, f"Lỗi cài đặt OmniMind: {str(e)[:80]}")
            return False

    def verify_codex_auth(self) -> dict:
        """
        Kiểm tra trạng thái đăng nhập thực tế của Codex.
        Ưu tiên đọc file config `~/.codex/auth.json` để tránh bị treo CLI.
        """
        import json
        
        try:
            # 1. Kiểm tra file config trước (cách tốt nhất để tránh hang)
            codex_dir = self.codex_home
            auth_file = codex_dir / "auth.json"
            
            if auth_file.exists():
                logger.info(f"codex auth_file found at {auth_file}")
                with open(auth_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                auth_mode = data.get("auth_mode", "unknown")
                tokens = data.get("tokens", {})
                api_key = data.get("OPENAI_API_KEY")
                has_tokens = isinstance(tokens, dict) and any(bool(v) for v in tokens.values())
                has_api_key = bool(api_key)
                
                # Nếu có token hoặc có API Key -> Đã đăng nhập
                if has_tokens or has_api_key:
                    logger.info("Codex auth verified via auth.json")
                    return {"success": True, "version": f"Logged in ({auth_mode})", "message": "Xác thực thành công qua config."}
            else:
                logger.debug(f"codex auth_file not found at {auth_file}")
            
            # 2. Xử lý xóa log cũ nếu cần fallback
            codex_cmd = self._resolve_codex_cmd()
            logger.info(f"Fallback: Checking Codex auth status using: {codex_cmd}")
            
            subprocess.run(
                [codex_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                stdin=subprocess.DEVNULL,
                env=self._codex_env(),
            )
            
            # Sử dụng timeout ngắn để tránh treo hoàn toàn
            result = subprocess.run(
                [codex_cmd, "login", "status"], 
                capture_output=True, 
                text=True, 
                timeout=5, 
                stdin=subprocess.DEVNULL,
                env=self._codex_env(),
            )
            
            output = result.stdout.strip()
            output_lower = output.lower()
            if result.returncode == 0 and ("logged in" in output_lower or "authenticated" in output_lower):
                return {"success": True, "version": output, "message": "Xác thực thành công."}
            else:
                return {"success": False, "message": "Chưa đăng nhập tài khoản OmniMind."}
                
        except json.JSONDecodeError:
            logger.error("Failed to parse auth.json")
            return {"success": False, "message": "Lỗi file cấu hình OmniMind."}
        except FileNotFoundError:
            logger.error("OmniMind not found.")
            return {"success": False, "message": "Không tìm thấy OmniMind."}
        except subprocess.TimeoutExpired:
            logger.error("OmniMind status check timed out.")
            return {"success": False, "message": "Hết thời gian chờ kết nối CLI."}
        except Exception as e:
            logger.exception("Unexpected error during Codex auth verification")
            return {"success": False, "message": f"Lỗi xác thực: {str(e)[:50]}"}

    def login_codex(self) -> dict:
        """
        Thực hiện lệnh đăng nhập OmniMind.
        """
        try:
            codex_cmd = self._resolve_codex_cmd()
            result = subprocess.run(
                [codex_cmd, "login"],
                capture_output=True,
                text=True,
                timeout=180,
                stdin=subprocess.DEVNULL,
                env=self._codex_env(),
            )

            output = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            output_lower = output.lower()
            err_lower = err.lower()

            if result.returncode == 0:
                return {"success": True, "message": output or "Đăng nhập OmniMind thành công."}

            if "already logged in" in output_lower or "already logged in" in err_lower:
                return {"success": True, "message": output or err or "OmniMind đã đăng nhập."}

            return {
                "success": False,
                "message": err or output or "Không thể đăng nhập OmniMind.",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Đăng nhập OmniMind quá thời gian chờ. Vui lòng thử lại.",
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi hệ thống: {str(e)[:50]}"}

    def logout_codex(self) -> dict:
        """
        Thực hiện đăng xuất tài khoản trong CLI.
        """
        try:
            codex_cmd = self._resolve_codex_cmd()
            result = subprocess.run(
                [codex_cmd, "logout"],
                capture_output=True,
                text=True,
                timeout=10,
                env=self._codex_env(),
            )
            
            if result.returncode == 0:
                return {"success": True, "message": "Đã đăng xuất thành công."}
            else:
                return {"success": False, "message": f"Lỗi khi đăng xuất: {result.stderr.strip()}"}
        except Exception as e:
            return {"success": False, "message": f"Lỗi hệ thống: {str(e)[:50]}"}
