import logging
import platform
from engine.config_manager import ConfigManager
from engine.update_manager import UpdateManager

logger = logging.getLogger(__name__)

class DashboardManager:
    """
    Quản lý dữ liệu cho trang Dashboard.
    - Lấy thông tin bản quyền từ local config.
    - Kiểm tra cập nhật từ Server API.
    """

    def __init__(self):
        self.api_base_url = ConfigManager.get("OMNIMIND_API_URL", "http://localhost:8050")
        self.update_mgr = UpdateManager()

    def get_license_display_info(self) -> dict:
        """Lấy thông tin bản quyền để hiển thị trên Dashboard."""
        is_activated = bool(ConfigManager.get("license_key"))
        status_dot = '<span style="color: #10B981;">●</span>' if is_activated else '<span style="color: #EF4444;">●</span>'
        status_text = "Đã kích hoạt" if is_activated else "Chưa kích hoạt"
        
        return {
            "key": ConfigManager.get("license_key", "Chưa kích hoạt"),
            "plan": ConfigManager.get("license_plan", "N/A"),
            "expires_at": ConfigManager.get("license_expires", "N/A"),
            "status": f"{status_dot} {status_text}"
        }

    def get_current_version(self) -> str:
        return self.update_mgr.get_current_version()

    def check_for_updates(self, current_version=None) -> dict:
        """
        Gọi API kiểm tra version mới nhất.
        Returns: { "has_update": bool, "latest_version": str, "changelog": list, ... }
        """
        return self.update_mgr.check_for_updates(self.api_base_url, current_version)

    def install_update(self, download_url: str, target_version: str, progress_callback=None) -> dict:
        return self.update_mgr.download_and_install_update(
            download_url=download_url,
            target_version=target_version,
            progress_callback=progress_callback,
        )

    def get_system_info(self) -> dict:
        """Lấy thông tin hệ thống cho Dashboard."""
        return {
            "os": platform.system(),
            "version": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.version(),
            "arch": platform.machine()
        }
