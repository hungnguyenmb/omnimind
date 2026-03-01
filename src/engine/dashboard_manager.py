import logging
import requests
import platform
from engine.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class DashboardManager:
    """
    Quản lý dữ liệu cho trang Dashboard.
    - Lấy thông tin bản quyền từ local config.
    - Kiểm tra cập nhật từ Server API.
    """

    def __init__(self):
        self.api_base_url = ConfigManager.get("OMNIMIND_API_URL", "http://localhost:8050")

    def get_license_display_info(self) -> dict:
        """Lấy thông tin bản quyền để hiển thị trên Dashboard."""
        return {
            "key": ConfigManager.get("license_key", "Chưa kích hoạt"),
            "plan": ConfigManager.get("license_plan", "N/A"),
            "expires_at": ConfigManager.get("license_expires", "N/A"),
            "status": "✅ Đã kích hoạt" if ConfigManager.get("license_key") else "❌ Chưa kích hoạt"
        }

    def check_for_updates(self, current_version: str = "1.0.0") -> dict:
        """
        Gọi API kiểm tra version mới nhất.
        Returns: { "has_update": bool, "latest_version": str, "changelog": list, ... }
        """
        url = f"{self.api_base_url}/api/v1/omnimind/app/version"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                latest_v = data.get("latest_version")
                
                # Logic so sánh version đơn giản (có thể cải thiện bằng packaging.version)
                has_update = latest_v and latest_v != current_version
                
                return {
                    "success": True,
                    "has_update": has_update,
                    "latest_version": latest_v,
                    "version_name": data.get("version_name"),
                    "download_url": data.get("download_url"),
                    "changelogs": data.get("changelogs", []),
                    "is_critical": data.get("is_critical", False)
                }
            return {"success": False, "message": "Không nhận được phản hồi từ Server."}
        except Exception as e:
            logger.error(f"Version check error: {e}")
            return {"success": False, "message": str(e)}

    def get_system_info(self) -> dict:
        """Lấy thông tin hệ thống cho Dashboard."""
        return {
            "os": platform.system(),
            "version": platform.mac_ver()[0] if platform.system() == "Darwin" else platform.version(),
            "arch": platform.machine()
        }
