import logging
import platform
from engine.config_manager import ConfigManager
from engine.update_manager import UpdateManager
from engine.telegram_bot_service import get_global_telegram_bot_service

logger = logging.getLogger(__name__)

class DashboardManager:
    """
    Quản lý dữ liệu cho trang Dashboard.
    - Lấy thông tin bản quyền từ local config.
    - Kiểm tra cập nhật từ Server API.
    """

    def __init__(self):
        self.api_base_url = ConfigManager.get_api_base_url()
        self.update_mgr = UpdateManager()

    def get_license_display_info(self) -> dict:
        """Lấy thông tin bản quyền để hiển thị trên Dashboard."""
        key = ConfigManager.get("license_key", "")
        status = str(ConfigManager.get("license_status", "")).strip().lower()
        is_activated = bool(key and status in {"active", "ok", "valid"})
        if not status and key:
            is_activated = True

        if is_activated:
            status_dot = '<span style="color: #10B981;">●</span>'
            status_text = "Đang hoạt động"
        elif key:
            status_dot = '<span style="color: #F59E0B;">●</span>'
            status_text = f"Không hoạt động ({status or 'unknown'})"
        else:
            status_dot = '<span style="color: #EF4444;">●</span>'
            status_text = "Chưa kích hoạt"
        
        return {
            "key": key or "Chưa kích hoạt",
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

    def install_update(
        self,
        download_url: str,
        target_version: str,
        expected_checksum: str = "",
        progress_callback=None,
    ) -> dict:
        return self.update_mgr.download_and_install_update(
            download_url=download_url,
            target_version=target_version,
            expected_checksum=expected_checksum,
            progress_callback=progress_callback,
        )

    def start_telegram_bot(self) -> dict:
        return get_global_telegram_bot_service().start()

    def stop_telegram_bot(self) -> dict:
        return get_global_telegram_bot_service().stop()

    def get_telegram_bot_status(self) -> dict:
        service = get_global_telegram_bot_service()
        return {
            "running": service.is_running(),
            "enabled": ConfigManager.get("bot_enabled", "False") == "True",
        }

    def get_system_info(self) -> dict:
        """Lấy thông tin hệ thống cho Dashboard."""
        return {
            "os": platform.system(),
            "version": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.version(),
            "arch": platform.machine()
        }
