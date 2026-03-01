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
        Chạy thử `codex --version` để check đã nhận lệnh chưa.
        Giả lập việc kiểm tra account nếu sau này Codex CLI hỗ trợ lệnh `codex status`.
        """
        try:
            # Ưu tiên lấy từ thư mục bin cục bộ
            codex_cmd = shutil.which("codex", path=str(self.codex_bin_dir)) or "codex"
            
            result = subprocess.run([codex_cmd, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return {"success": True, "version": result.stdout.strip(), "message": "Xác thực thành công."}
            else:
                return {"success": False, "message": f"Lỗi CLI: {result.stderr.strip()}"}
        except FileNotFoundError:
            return {"success": False, "message": "Không tìm thấy Codex CLI."}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Hết thời gian chờ (Timeout)."}
        except Exception as e:
            return {"success": False, "message": f"Lỗi không xác định: {str(e)[:50]}"}
