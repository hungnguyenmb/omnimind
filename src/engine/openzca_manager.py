import logging
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from engine.config_manager import ConfigManager
from engine.environment_manager import EnvironmentManager

logger = logging.getLogger(__name__)


class OpenZcaManager:
    DEFAULT_PROFILE_NAME = "omnimind"
    INSTALL_TIMEOUT_SEC = 20 * 60
    AUTH_TIMEOUT_SEC = 5 * 60

    def __init__(self, env_manager: Optional[EnvironmentManager] = None):
        self.env_manager = env_manager or EnvironmentManager()
        self.os_name = platform.system()
        self.app_data_dir = self._get_app_data_root()

    def _get_app_data_root(self) -> Path:
        raw_root = getattr(self.env_manager, "app_data_dir", None)
        root = Path(raw_root).expanduser() if raw_root else None
        if root is None:
            if self.os_name == "Windows":
                base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
                root = Path(base) / "OmniMind"
            elif self.os_name == "Darwin":
                root = Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind"
            else:
                root = Path(os.path.expanduser("~/.omnimind"))
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _windows_hidden_subprocess_kwargs(self) -> dict:
        helper = getattr(self.env_manager, "_windows_hidden_subprocess_kwargs", None)
        if callable(helper):
            return helper()
        return {}

    def _run_probe(self, cmd: list[str], timeout: int = 8, env: Optional[dict] = None) -> tuple[bool, str]:
        helper = getattr(self.env_manager, "_run_probe", None)
        if callable(helper) and env is None:
            return helper(cmd, timeout=timeout)
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=env,
                **self._windows_hidden_subprocess_kwargs(),
            )
            out = (completed.stdout or completed.stderr or "").strip()
            return completed.returncode == 0, out
        except Exception as e:
            return False, str(e)

    def _resolve_node_command(self) -> str:
        return shutil.which("node") or "node"

    def _resolve_npm_command(self) -> str:
        if self.os_name == "Windows":
            return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
        return shutil.which("npm") or "npm"

    def _build_openzca_invocation(self, *args: str) -> list[str]:
        cmd = self.get_openzca_command()
        path = Path(cmd)
        argv = [str(arg) for arg in args if str(arg or "").strip()]
        if path.suffix.lower() == ".js":
            return [self._resolve_node_command(), cmd, *argv]
        return [cmd, *argv]

    def _run_openzca_command(
        self,
        args: list[str],
        timeout: int = 15,
        env: Optional[dict] = None,
    ) -> dict:
        runtime = self.inspect_runtime()
        if not runtime.get("node_ok"):
            return {"success": False, "returncode": 127, "stdout": "", "stderr": "Thiếu Node.js 18+."}
        if not runtime.get("npm_ok"):
            return {"success": False, "returncode": 127, "stdout": "", "stderr": "Thiếu npm."}
        cmd = self._build_openzca_invocation(*args)
        try:
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                env=env or self.build_openzca_env(),
                **self._windows_hidden_subprocess_kwargs(),
            )
            return {
                "success": completed.returncode == 0,
                "returncode": int(completed.returncode),
                "stdout": str(completed.stdout or ""),
                "stderr": str(completed.stderr or ""),
                "command": cmd,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "success": False,
                "returncode": -9,
                "stdout": str(getattr(e, "stdout", "") or ""),
                "stderr": str(getattr(e, "stderr", "") or ""),
                "message": "Lệnh OpenZCA quá thời gian chờ.",
                "command": cmd,
            }
        except Exception as e:
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
                "message": f"Lỗi chạy OpenZCA: {str(e)[:220]}",
                "command": cmd,
            }

    def get_app_data_root(self) -> str:
        return str(self.app_data_dir)

    def get_openzca_runtime_root(self) -> str:
        path = self.app_data_dir / "openzca-runtime"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_openzca_home(self) -> str:
        path = self.app_data_dir / "openzca-home"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_openzca_logs_dir(self) -> str:
        path = self.app_data_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_profile_name(self) -> str:
        profile = str(ConfigManager.get("zalo_profile_name", self.DEFAULT_PROFILE_NAME) or "").strip()
        if not profile:
            profile = self.DEFAULT_PROFILE_NAME
        if profile != ConfigManager.get("zalo_profile_name", ""):
            ConfigManager.set("zalo_profile_name", profile)
        return profile

    def build_openzca_env(self, include_profile: bool = True) -> dict:
        env = os.environ.copy()
        env["OPENZCA_HOME"] = self.get_openzca_home()
        if include_profile:
            env["OPENZCA_PROFILE"] = self.get_profile_name()
        else:
            env.pop("OPENZCA_PROFILE", None)
        return env

    def is_node_available(self) -> bool:
        ok, _ = self._run_probe([self._resolve_node_command(), "--version"], timeout=5)
        return ok

    def is_npm_available(self) -> bool:
        ok, _ = self._run_probe([self._resolve_npm_command(), "--version"], timeout=5)
        return ok

    def get_node_version(self) -> str:
        ok, out = self._run_probe([self._resolve_node_command(), "--version"], timeout=5)
        return out.splitlines()[0].strip() if ok and out else ""

    def get_npm_version(self) -> str:
        ok, out = self._run_probe([self._resolve_npm_command(), "--version"], timeout=5)
        return out.splitlines()[0].strip() if ok and out else ""

    def get_openzca_command(self) -> str:
        runtime_root = Path(self.get_openzca_runtime_root())
        bin_dir = runtime_root / "node_modules" / ".bin"
        candidates: list[Path] = []
        if self.os_name == "Windows":
            candidates.extend(
                [
                    bin_dir / "openzca.cmd",
                    bin_dir / "openzca",
                    runtime_root / "node_modules" / "openzca" / "bin" / "openzca.js",
                ]
            )
        else:
            candidates.extend(
                [
                    bin_dir / "openzca",
                    runtime_root / "node_modules" / "openzca" / "bin" / "openzca.js",
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(candidates[0])

    def check_openzca_installed(self) -> bool:
        cmd = self.get_openzca_command()
        path = Path(cmd)
        if not path.exists():
            return False
        ok, _ = self._run_probe(self._build_openzca_invocation("--version"), timeout=8, env=self.build_openzca_env())
        if ok:
            return True
        ok_help, _ = self._run_probe(self._build_openzca_invocation("--help"), timeout=8, env=self.build_openzca_env())
        return ok_help

    def get_openzca_version(self) -> str:
        cmd = self.get_openzca_command()
        if not Path(cmd).exists():
            return ""
        ok, out = self._run_probe(self._build_openzca_invocation("--version"), timeout=8, env=self.build_openzca_env())
        if ok and out:
            return out.splitlines()[0].strip()
        return ""

    @staticmethod
    def _summarize_output(raw: str) -> str:
        lines = [line.strip() for line in str(raw or "").splitlines() if line.strip()]
        if not lines:
            return ""
        return lines[0][:220]

    def _persist_runtime_status(self, install_status: str, version: str = "", last_error: str = ""):
        ConfigManager.set_zalo_runtime_status(
            install_status=install_status,
            version=version,
            last_error=last_error,
            checked_at=self._utc_now_iso(),
        )

    def inspect_runtime(self) -> dict:
        node_ok = self.is_node_available()
        npm_ok = self.is_npm_available()
        node_version = self.get_node_version() if node_ok else ""
        npm_version = self.get_npm_version() if npm_ok else ""
        openzca_ready = self.check_openzca_installed() if node_ok and npm_ok else False
        openzca_version = self.get_openzca_version() if openzca_ready else ""
        command_path = self.get_openzca_command()
        last_error = ConfigManager.get("zalo_runtime_last_error", "").strip()

        install_status = "ready" if openzca_ready else "not_installed"
        message = "OpenZCA đã sẵn sàng." if openzca_ready else "OpenZCA chưa được cài đặt."
        if not node_ok:
            install_status = "missing_node"
            message = "Thiếu Node.js 18+."
        elif not npm_ok:
            install_status = "missing_npm"
            message = "Thiếu npm."
        elif Path(command_path).exists() and not openzca_ready:
            install_status = "broken"
            message = "Runtime OpenZCA tồn tại nhưng không chạy được."

        self._persist_runtime_status(
            install_status=install_status,
            version=openzca_version,
            last_error="" if openzca_ready else last_error,
        )
        return {
            "success": True,
            "install_status": install_status,
            "message": message,
            "node_ok": node_ok,
            "npm_ok": npm_ok,
            "node_version": node_version,
            "npm_version": npm_version,
            "openzca_ready": openzca_ready,
            "openzca_version": openzca_version,
            "runtime_root": self.get_openzca_runtime_root(),
            "openzca_home": self.get_openzca_home(),
            "logs_dir": self.get_openzca_logs_dir(),
            "command_path": command_path,
            "profile_name": self.get_profile_name(),
            "last_error": last_error,
        }

    def install_openzca(self, target_version: str = "") -> dict:
        inspect = self.inspect_runtime()
        if not inspect.get("node_ok"):
            msg = "Thiếu Node.js 18+ nên chưa thể cài OpenZCA."
            self._persist_runtime_status("missing_node", last_error=msg)
            return {**inspect, "success": False, "message": msg}
        if not inspect.get("npm_ok"):
            msg = "Thiếu npm nên chưa thể cài OpenZCA."
            self._persist_runtime_status("missing_npm", last_error=msg)
            return {**inspect, "success": False, "message": msg}

        runtime_root = Path(self.get_openzca_runtime_root())
        runtime_root.mkdir(parents=True, exist_ok=True)

        version_token = str(target_version or "").strip()
        package_name = f"openzca@{version_token}" if version_token else "openzca@latest"
        install_cmd = [
            self._resolve_npm_command(),
            "install",
            "--prefix",
            str(runtime_root),
            "--no-fund",
            "--no-audit",
            package_name,
        ]

        self._persist_runtime_status("installing", last_error="")
        try:
            completed = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.INSTALL_TIMEOUT_SEC,
                stdin=subprocess.DEVNULL,
                env=self.build_openzca_env(),
                **self._windows_hidden_subprocess_kwargs(),
            )
            if completed.returncode != 0:
                detail = self._summarize_output(completed.stderr or completed.stdout)
                msg = f"Cài OpenZCA thất bại: {detail or 'npm install lỗi.'}"
                self._persist_runtime_status("error", last_error=msg)
                return {**self.inspect_runtime(), "success": False, "message": msg}
        except subprocess.TimeoutExpired:
            msg = "Cài OpenZCA quá thời gian chờ."
            self._persist_runtime_status("error", last_error=msg)
            return {**self.inspect_runtime(), "success": False, "message": msg}
        except Exception as e:
            msg = f"Cài OpenZCA lỗi: {str(e)[:220]}"
            self._persist_runtime_status("error", last_error=msg)
            return {**self.inspect_runtime(), "success": False, "message": msg}

        verify = self.inspect_runtime()
        if not verify.get("openzca_ready"):
            msg = "Cài OpenZCA xong nhưng không verify được binary local."
            self._persist_runtime_status("error", last_error=msg)
            return {**verify, "success": False, "message": msg}

        version = str(verify.get("openzca_version") or "").strip()
        self._persist_runtime_status("ready", version=version, last_error="")
        return {**verify, "success": True, "message": f"Đã cài OpenZCA thành công{f' · {version}' if version else ''}."}

    def repair_openzca(self, target_version: str = "") -> dict:
        runtime_root = Path(self.get_openzca_runtime_root())
        try:
            if runtime_root.exists():
                shutil.rmtree(runtime_root, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Cannot cleanup OpenZCA runtime before repair: {e}")
        return self.install_openzca(target_version=target_version)

    def ensure_openzca_installed(self, target_version: str = "") -> dict:
        inspect = self.inspect_runtime()
        if inspect.get("openzca_ready"):
            return {**inspect, "success": True, "message": "OpenZCA đã sẵn sàng."}
        return self.install_openzca(target_version=target_version)

    def ensure_profile_exists(self) -> dict:
        runtime = self.inspect_runtime()
        if not runtime.get("openzca_ready"):
            return {"success": False, "message": runtime.get("message", "OpenZCA chưa sẵn sàng.")}

        profile_name = self.get_profile_name()
        list_res = self._run_openzca_command(
            ["account", "list"],
            timeout=15,
            env=self.build_openzca_env(include_profile=False),
        )
        list_text = self._extract_text(list_res)
        if list_res.get("success") and profile_name in list_text:
            return {"success": True, "message": f"Profile {profile_name} đã tồn tại."}

        add_res = self._run_openzca_command(
            ["account", "add", profile_name],
            timeout=15,
            env=self.build_openzca_env(include_profile=False),
        )
        add_text = self._extract_text(add_res)
        low = add_text.lower()
        if add_res.get("success") or "profile created" in low or "already exists" in low:
            return {"success": True, "message": add_text or f"Đã tạo profile {profile_name}."}
        return {
            "success": False,
            "message": self._summarize_output(add_text) or f"Không thể tạo profile {profile_name}.",
        }

    @staticmethod
    def _extract_text(payload: dict) -> str:
        parts = [str(payload.get("stdout") or "").strip(), str(payload.get("stderr") or "").strip()]
        return "\n".join([part for part in parts if part]).strip()

    @staticmethod
    def _looks_logged_in(raw_text: str) -> bool:
        text = str(raw_text or "").strip().lower()
        if not text:
            return False
        negative = (
            "not logged in",
            "not authenticated",
            "unauthenticated",
            "chưa đăng nhập",
            "no session",
            "login required",
            "qr required",
        )
        if any(token in text for token in negative):
            return False
        positive = (
            "logged in",
            "authenticated",
            "authorized",
            "connected",
            "session active",
            "active session",
            "đã đăng nhập",
        )
        return any(token in text for token in positive)

    @staticmethod
    def _extract_identity(raw_text: str) -> str:
        text = str(raw_text or "").strip()
        if not text:
            return ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if any(line.lower().startswith("error:") for line in lines):
            return ""
        if len(lines) == 1 and len(lines[0]) <= 64:
            return lines[0]
        for line in lines:
            low = line.lower()
            if low.startswith("id:") or low.startswith("uid:") or low.startswith("user_id:"):
                return line.split(":", 1)[1].strip()
        return ""

    def run_auth_status(self) -> dict:
        runtime = self.inspect_runtime()
        if not runtime.get("openzca_ready"):
            return {
                "success": False,
                "logged_in": False,
                "message": runtime.get("message", "OpenZCA chưa sẵn sàng."),
                "self_user_id": "",
            }
        profile_res = self.ensure_profile_exists()
        if not profile_res.get("success"):
            return {
                "success": False,
                "logged_in": False,
                "message": profile_res.get("message", "Không thể khởi tạo profile Zalo."),
                "self_user_id": "",
            }

        status_res = self._run_openzca_command(["auth", "status"], timeout=20)
        combined = self._extract_text(status_res)
        logged_in = bool(status_res.get("success") and self._looks_logged_in(combined))
        self_user_id = ""

        if not logged_in:
            id_res = self._run_openzca_command(["me", "id"], timeout=15)
            id_text = self._extract_text(id_res)
            self_user_id = self._extract_identity(id_text)
            if id_res.get("success") and self_user_id:
                logged_in = True
                combined = combined or id_text
        else:
            id_res = self._run_openzca_command(["me", "id"], timeout=15)
            self_user_id = self._extract_identity(self._extract_text(id_res))

        if logged_in:
            msg = combined or "Zalo session đang hoạt động."
            return {
                "success": True,
                "logged_in": True,
                "message": self._summarize_output(msg) or "Zalo session đang hoạt động.",
                "raw_text": combined,
                "self_user_id": self_user_id,
            }

        msg = combined or status_res.get("message") or "Chưa đăng nhập Zalo."
        return {
            "success": False,
            "logged_in": False,
            "message": self._summarize_output(msg) or "Chưa đăng nhập Zalo.",
            "raw_text": combined,
            "self_user_id": self_user_id,
        }

    def run_auth_login(self) -> dict:
        runtime = self.inspect_runtime()
        if not runtime.get("openzca_ready"):
            return {
                "success": False,
                "message": runtime.get("message", "OpenZCA chưa sẵn sàng."),
                "qr_path": "",
            }
        profile_res = self.ensure_profile_exists()
        if not profile_res.get("success"):
            return {
                "success": False,
                "message": profile_res.get("message", "Không thể khởi tạo profile Zalo."),
                "qr_path": "",
            }

        qr_dir = Path(self.get_openzca_runtime_root()) / "qr"
        qr_dir.mkdir(parents=True, exist_ok=True)
        qr_path = qr_dir / "zalo-login-qr.png"
        cmd_args = ["auth", "login", "--qr-path", str(qr_path)]
        if self.os_name != "Windows":
            cmd_args.append("--open-qr")
        result = self._run_openzca_command(cmd_args, timeout=self.AUTH_TIMEOUT_SEC)
        combined = self._extract_text(result)
        if result.get("success"):
            status = self.run_auth_status()
            success = bool(status.get("logged_in"))
            message = status.get("message") if success else (self._summarize_output(combined) or "Đăng nhập Zalo chưa hoàn tất.")
            return {
                "success": success,
                "message": message,
                "qr_path": str(qr_path),
                "self_user_id": status.get("self_user_id", ""),
                "raw_text": combined,
            }
        return {
            "success": False,
            "message": self._summarize_output(combined) or result.get("message") or "Đăng nhập Zalo thất bại.",
            "qr_path": str(qr_path),
            "raw_text": combined,
        }

    def run_auth_logout(self) -> dict:
        runtime = self.inspect_runtime()
        if not runtime.get("openzca_ready"):
            return {"success": False, "message": runtime.get("message", "OpenZCA chưa sẵn sàng.")}
        profile_res = self.ensure_profile_exists()
        if not profile_res.get("success"):
            return {"success": False, "message": profile_res.get("message", "Không thể khởi tạo profile Zalo.")}
        result = self._run_openzca_command(["auth", "logout"], timeout=30)
        combined = self._extract_text(result)
        if result.get("success"):
            return {
                "success": True,
                "message": self._summarize_output(combined) or "Đã đăng xuất Zalo.",
            }
        return {
            "success": False,
            "message": self._summarize_output(combined) or result.get("message") or "Đăng xuất Zalo thất bại.",
        }
