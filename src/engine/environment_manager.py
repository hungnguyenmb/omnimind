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
        status = {
            "python": "OK" if shutil.which("python3") or shutil.which("python") else "MISSING",
            "node": "OK" if shutil.which("node") else "MISSING",
            "npm": "OK" if shutil.which("npm") else "MISSING",
            "codex": "OK" if shutil.which("codex") else "MISSING"
        }
        
        # Phân loại độ nghiêm trọng
        status["is_ready"] = all(v == "OK" for v in status.values())
        return status

    def install_missing_env(self, missing_list: list) -> bool:
        """
        Cài đặt tự động các môi trường bị thiếu (Yêu cầu Quyền Admin/Sudo).
        """
        logger.info(f"Attempting to install missing environment: {missing_list}")
        
        if self.os_name == "Windows":
            return self._install_env_windows(missing_list)
        elif self.os_name == "Darwin":
            return self._install_env_macos(missing_list)
        else:
            logger.error("Auto-install not supported on this OS.")
            return False

    def _install_env_windows(self, missing: list) -> bool:
        """Sử dụng WinGet / PowerShell để cài âm thầm trên Windows."""
        try:
            # Script cài đặt qua winget (Cần cửa sổ UAC của Windows)
            script = []
            if "python" in missing:
                script.append("winget install -e --id Python.Python.3.11 --silent")
            if "node" in missing or "npm" in missing:
                script.append("winget install -e --id OpenJS.NodeJS --silent")
                
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

    def _install_env_macos(self, missing: list) -> bool:
        """Sử dụng Homebrew trên macOS. Yêu cầu nhập pass Sudo qua GUI (tương lai)."""
        try:
            # Kiểm tra Brew trước
            if not shutil.which("brew"):
                logger.error("Homebrew is missing. Cannot auto-install on macOS.")
                # TODO: Mở popup hướng dẫn cài Brew
                return False
                
            script = []
            if "python" in missing:
                script.append("brew install python")
            if "node" in missing or "npm" in missing:
                script.append("brew install node")
                
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
        zip_path = self.app_data_dir / "codex_temp.zip"
        
        try:
            # Tải file
            req = urllib.request.Request(download_url, headers={'User-Agent': 'OmniMind-App'})
            with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            
            logger.info("Extracting Codex CLI...")
            # Giải nén
            if zipfile.is_zipfile(zip_path):
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(self.codex_bin_dir)
            elif tarfile.is_tarfile(zip_path):
                with tarfile.open(zip_path, 'r') as tar_ref:
                    tar_ref.extractall(self.codex_bin_dir)
                    
            # Cấp quyền thực thi (chmod +x) trên Mac/Linux
            if self.os_name != "Windows":
                for root, _, files in os.walk(self.codex_bin_dir):
                    for file in files:
                        os.chmod(os.path.join(root, file), 0o755)
                        
            # Dọn dẹp
            os.remove(zip_path)
            logger.info("Codex CLI installed successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Download/Install Codex failed: {e}")
            if zip_path.exists():
                os.remove(zip_path)
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
            codex_cmd = shutil.which("codex", path=str(self.codex_bin_dir)) or "codex"
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
            codex_cmd = shutil.which("codex", path=str(self.codex_bin_dir)) or "codex"
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
            codex_cmd = shutil.which("codex", path=str(self.codex_bin_dir)) or "codex"
            result = subprocess.run([codex_cmd, "logout"], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                return {"success": True, "message": "Đã đăng xuất thành công."}
            else:
                return {"success": False, "message": f"Lỗi khi đăng xuất: {result.stderr.strip()}"}
        except Exception as e:
            return {"success": False, "message": f"Lỗi hệ thống: {str(e)[:50]}"}
