import os
import shutil
import platform
import subprocess
import logging
import urllib.request
import zipfile
import tarfile
from pathlib import Path
from engine.config_manager import ConfigManager

logger = logging.getLogger(__name__)

DEFAULT_API_BASE_URL = os.environ.get("OMNIMIND_API_URL", "http://localhost:8050")
DEFAULT_RELEASE_MANIFEST = {
    "version": "1.5.0",
    "prerequisites": {"python": ">=3.9", "node": ">=18.0"},
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
    (Python, Node, npm, Codex CLI) tương thích Cross-Platform (macOS / Windows).
    """
    
    def __init__(self):
        self.os_name = platform.system()
        self.app_data_dir = self._get_app_data_dir()
        self.codex_bin_dir = self.app_data_dir / "bin"
        self.codex_bin_dir.mkdir(parents=True, exist_ok=True)
        
        # Đưa thư mục bin cục bộ vào PATH tạm thời cho phiên chạy
        os.environ["PATH"] = f"{str(self.codex_bin_dir)}{os.pathsep}{os.environ.get('PATH', '')}"

    def _resolve_codex_cmd(self) -> str:
        """Ưu tiên codex đã cài local trong app, fallback system PATH."""
        return shutil.which("codex", path=str(self.codex_bin_dir)) or shutil.which("codex") or "codex"

    def get_platform_key(self) -> str:
        """Chuẩn hóa platform key cho manifest release."""
        if self.os_name == "Darwin":
            return "darwin"
        if self.os_name == "Windows":
            return "win32"
        if self.os_name == "Linux":
            return "linux"
        return "unknown"

    def get_api_base_url(self) -> str:
        """
        Lấy API base URL theo thứ tự ưu tiên:
        1) ENV OMNIMIND_API_URL
        2) DB app_configs (omnimind_api_url / OMNIMIND_API_URL)
        3) Default local
        """
        env_val = os.environ.get("OMNIMIND_API_URL", "").strip()
        if env_val:
            return env_val

        cfg_val = (
            ConfigManager.get("omnimind_api_url", "").strip()
            or ConfigManager.get("OMNIMIND_API_URL", "").strip()
        )
        if cfg_val:
            return cfg_val

        return DEFAULT_API_BASE_URL

    def fetch_codex_release_manifest(self) -> dict:
        """
        Lấy release manifest từ server; nếu lỗi sẽ fallback local defaults.
        Cơ chế hybrid này giúp hotfix link tải mà không bắt user update app.
        """
        import requests

        api_url = f"{self.get_api_base_url()}/api/v1/omnimind/codex/releases"
        try:
            resp = requests.get(api_url, timeout=10)
            if resp.status_code == 200:
                remote = resp.json() or {}
                merged = dict(DEFAULT_RELEASE_MANIFEST)
                merged.update(remote)

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
        codex_cmd = self._resolve_codex_cmd()
        codex_ok = shutil.which(codex_cmd) is not None or codex_cmd == "codex"
        if codex_ok and codex_cmd == "codex":
            # Nếu rơi vào fallback literal "codex", kiểm tra lại bằng which để tránh false-positive.
            codex_ok = shutil.which("codex") is not None

        status = {
            "python": "OK" if shutil.which("python3") or shutil.which("python") else "MISSING",
            "node": "OK" if shutil.which("node") else "MISSING",
            "npm": "OK" if shutil.which("npm") else "MISSING",
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

    def install_missing_env(self, missing_list: list, install_policy: dict | None = None) -> bool:
        """
        Cài đặt tự động các môi trường bị thiếu (Yêu cầu Quyền Admin/Sudo).
        """
        logger.info(f"Attempting to install missing environment: {missing_list}")
        policy = install_policy or {}
        
        if self.os_name == "Windows":
            return self._install_env_windows(missing_list, policy.get("windows", {}))
        elif self.os_name == "Darwin":
            return self._install_env_macos(missing_list, policy.get("darwin", {}))
        else:
            logger.error("Auto-install not supported on this OS.")
            return False

    def _install_env_windows(self, missing: list, policy: dict | None = None) -> bool:
        """Sử dụng WinGet / PowerShell để cài âm thầm trên Windows."""
        policy = policy or {}
        try:
            # Script cài đặt qua winget (Cần cửa sổ UAC của Windows)
            script = []
            python_pkg = policy.get("python_package_id", "Python.Python.3.11")
            node_pkg = policy.get("node_package_id", "OpenJS.NodeJS")
            if "python" in missing:
                script.append(f"winget install -e --id {python_pkg} --silent")
            if "node" in missing or "npm" in missing:
                script.append(f"winget install -e --id {node_pkg} --silent")
                
            if not script: return True
            
            ps_command = " ; ".join(script)
            logger.info(f"Running Windows installer: {ps_command}")
            # Dùng powershell Start-Process để trigger UAC Admin
            subprocess.run([
                "powershell", "-Command", 
                f"Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command \"{ps_command}\"' -Verb RunAs -Wait"
            ], check=True)
            return True
        except Exception as e:
            logger.error(f"Windows env install failed: {e}")
            return False

    def _install_env_macos(self, missing: list, policy: dict | None = None) -> bool:
        """Sử dụng Homebrew trên macOS. Yêu cầu nhập pass Sudo qua GUI (tương lai)."""
        policy = policy or {}
        try:
            # Kiểm tra Brew trước
            if not shutil.which("brew"):
                logger.error("Homebrew is missing. Cannot auto-install on macOS.")
                # TODO: Mở popup hướng dẫn cài Brew
                return False
                
            script = []
            python_formula = policy.get("python_formula", "python")
            node_formula = policy.get("node_formula", "node")
            if "python" in missing:
                script.append(f"brew install {python_formula}")
            if "node" in missing or "npm" in missing:
                script.append(f"brew install {node_formula}")
                
            if not script: return True
            
            sh_command = " && ".join(script)
            logger.info(f"Running macOS installer: {sh_command}")
            # Note: Brew không chạy dưới root, nên chạy lệnh thường. 
            subprocess.run(sh_command, shell=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"macOS env install failed: {e}")
            return False

    def download_and_install_codex(self, download_url: str) -> bool:
        """
        Tải binary Codex CLI từ Server, giải nén vào self.codex_bin_dir
        """
        logger.info(f"Downloading Codex CLI from {download_url}...")
        archive_path = self.app_data_dir / "codex_temp.pkg"
        
        try:
            # Tải file
            req = urllib.request.Request(download_url, headers={'User-Agent': 'OmniMind-App'})
            with urllib.request.urlopen(req) as response, open(archive_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            
            logger.info("Extracting Codex CLI...")
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
                raise RuntimeError("Định dạng gói Codex không hợp lệ (không phải zip/tar).")
                    
            # Cấp quyền thực thi (chmod +x) trên Mac/Linux
            if self.os_name != "Windows":
                for root, _, files in os.walk(self.codex_bin_dir):
                    for file in files:
                        os.chmod(os.path.join(root, file), 0o755)

            # Verify binary tồn tại sau khi giải nén.
            if not shutil.which("codex", path=str(self.codex_bin_dir)) and not shutil.which("codex"):
                raise RuntimeError("Không tìm thấy binary codex sau khi cài đặt.")

            # Dọn dẹp
            os.remove(archive_path)
            logger.info("Codex CLI installed successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Download/Install Codex failed: {e}")
            if archive_path.exists():
                os.remove(archive_path)
            return False

    def verify_codex_auth(self) -> dict:
        """
        Kiểm tra trạng thái đăng nhập thực tế của Codex.
        Ưu tiên đọc file config `~/.codex/auth.json` để tránh bị treo CLI.
        """
        import json
        
        try:
            # 1. Kiểm tra file config trước (cách tốt nhất để tránh hang)
            codex_dir = Path.home() / ".codex"
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
            
            subprocess.run([codex_cmd, "--version"], capture_output=True, text=True, timeout=3, stdin=subprocess.DEVNULL)
            
            # Sử dụng timeout ngắn để tránh treo hoàn toàn
            result = subprocess.run(
                [codex_cmd, "login", "status"], 
                capture_output=True, 
                text=True, 
                timeout=5, 
                stdin=subprocess.DEVNULL
            )
            
            output = result.stdout.strip()
            output_lower = output.lower()
            if result.returncode == 0 and ("logged in" in output_lower or "authenticated" in output_lower):
                return {"success": True, "version": output, "message": "Xác thực thành công."}
            else:
                return {"success": False, "message": "Chưa đăng nhập tài khoản Codex."}
                
        except json.JSONDecodeError:
            logger.error("Failed to parse auth.json")
            return {"success": False, "message": "Lỗi file cấu hình Codex."}
        except FileNotFoundError:
            logger.error("Codex CLI not found.")
            return {"success": False, "message": "Không tìm thấy Codex CLI."}
        except subprocess.TimeoutExpired:
            logger.error("Codex CLI status check timed out.")
            return {"success": False, "message": "Hết thời gian chờ kết nối CLI."}
        except Exception as e:
            logger.exception("Unexpected error during Codex auth verification")
            return {"success": False, "message": f"Lỗi xác thực: {str(e)[:50]}"}

    def login_codex(self) -> dict:
        """
        Thực hiện lệnh đăng nhập Codex CLI.
        """
        try:
            codex_cmd = self._resolve_codex_cmd()
            result = subprocess.run(
                [codex_cmd, "login"],
                capture_output=True,
                text=True,
                timeout=180,
                stdin=subprocess.DEVNULL,
            )

            output = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            output_lower = output.lower()
            err_lower = err.lower()

            if result.returncode == 0:
                return {"success": True, "message": output or "Đăng nhập Codex thành công."}

            if "already logged in" in output_lower or "already logged in" in err_lower:
                return {"success": True, "message": output or err or "Codex đã đăng nhập."}

            return {
                "success": False,
                "message": err or output or "Không thể đăng nhập Codex CLI.",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Đăng nhập Codex quá thời gian chờ. Vui lòng thử lại.",
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi hệ thống: {str(e)[:50]}"}

    def logout_codex(self) -> dict:
        """
        Thực hiện đăng xuất tài khoản trong CLI.
        """
        try:
            codex_cmd = self._resolve_codex_cmd()
            result = subprocess.run([codex_cmd, "logout"], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return {"success": True, "message": "Đã đăng xuất thành công."}
            else:
                return {"success": False, "message": f"Lỗi khi đăng xuất: {result.stderr.strip()}"}
        except Exception as e:
            return {"success": False, "message": f"Lỗi hệ thống: {str(e)[:50]}"}
