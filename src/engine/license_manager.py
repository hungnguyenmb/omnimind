"""
OmniMind - License Manager Engine
Xử lý toàn bộ logic kích hoạt bản quyền:
  - Tạo Hardware ID (HWID) dựa trên thông tin phần cứng.
  - Gọi API Server để xác thực License Key + HWID.
  - Lưu trạng thái kích hoạt vào SQLite cục bộ (app_configs).

CROSS-PLATFORM: Logic này PHẢI hoạt động trên cả macOS và Windows.
"""
import platform
import subprocess
import hashlib
import logging
import json
import os

logger = logging.getLogger(__name__)

# ─── Cấu hình API ───────────────────────────────────────────────
# Biến môi trường OMNIMIND_API_URL quy định Server trỏ tới.
# - Dev/Test (localhost): http://localhost:8050
# - Production (VPS):     https://license.vinhyenit.com
DEFAULT_API_BASE_URL = os.environ.get("OMNIMIND_API_URL", "http://localhost:8050")
LICENSE_VERIFY_ENDPOINT = "/api/v1/omnimind/licenses/verify"


class LicenseManager:
    """
    Engine quản lý License. Sử dụng bởi UI (license_screen.py) và main.py.
    """

    def __init__(self, db_manager=None):
        from database.db_manager import DBManager
        self.db = db_manager or DBManager()
        self._api_base_url = DEFAULT_API_BASE_URL

    # ──────────────────────────────────────────────────────────────
    # 1. HARDWARE ID (HWID) - Cross-Platform
    # ──────────────────────────────────────────────────────────────
    def get_hwid(self) -> str:
        """
        Tạo mã Hardware ID duy nhất dựa trên thông tin phần cứng.
        - macOS: IOPlatformSerialNumber (Serial mainboard)
        - Windows: BIOS Serial Number (wmic)
        Kết quả: SHA-256 hash của chuỗi serial gốc.
        """
        raw_id = ""
        os_name = platform.system()

        try:
            if os_name == "Darwin":  # macOS
                result = subprocess.run(
                    ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split("\n"):
                    if "IOPlatformSerialNumber" in line:
                        raw_id = line.split("=")[-1].strip().strip('"')
                        break

            elif os_name == "Windows":
                result = subprocess.run(
                    ["wmic", "bios", "get", "serialnumber"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW
                       if os_name == "Windows" else 0
                )
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                if len(lines) > 1:
                    raw_id = lines[1]

            else:
                # Linux fallback (cho dev/test)
                raw_id = platform.node()

        except Exception as e:
            logger.warning(f"Error getting HWID: {e}")
            raw_id = platform.node()  # fallback to hostname

        if not raw_id:
            raw_id = platform.node()

        # SHA-256 hash để chuẩn hoá và bảo mật
        hwid = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:32]
        logger.info(f"Generated HWID: {hwid[:8]}...")
        return hwid

    def get_os_info(self) -> dict:
        """Thu thập thông tin OS để gửi kèm khi kích hoạt."""
        return {
            "os_name": platform.system(),      # "Darwin" / "Windows"
            "os_version": platform.version(),
            "machine": platform.machine(),
        }

    # ──────────────────────────────────────────────────────────────
    # 2. KIỂM TRA LICENSE CỤC BỘ (Offline Check)
    # ──────────────────────────────────────────────────────────────
    def get_saved_license(self) -> str | None:
        """Đọc license_key đã lưu trong SQLite (app_configs)."""
        row = self.db.fetch_one(
            "SELECT value FROM app_configs WHERE key = ?", ("license_key",)
        )
        return row["value"] if row else None

    def get_saved_token(self) -> str | None:
        """Đọc JWT token xác thực đã cache."""
        row = self.db.fetch_one(
            "SELECT value FROM app_configs WHERE key = ?", ("license_jwt",)
        )
        return row["value"] if row else None

    def is_activated_locally(self) -> bool:
        """Kiểm tra nhanh xem thiết bị đã từng kích hoạt thành công chưa."""
        key = self.get_saved_license()
        token = self.get_saved_token()
        return bool(key and token)

    # ──────────────────────────────────────────────────────────────
    # 3. XÁC THỰC VỚI SERVER (Online Verify)
    # ──────────────────────────────────────────────────────────────
    def verify_license(self, license_key: str) -> dict:
        """
        Gọi API Server: POST /api/v1/licenses/verify
        Gửi: license_key, hwid, os_info
        Nhận: { success, token, plan, message, expires_at }

        Returns:
            dict: { "success": bool, "message": str, "plan": str|None, ... }
        """
        import requests

        hwid = self.get_hwid()
        os_info = self.get_os_info()

        payload = {
            "license_key": license_key,
            "hwid": hwid,
            "os_name": os_info["os_name"],
            "os_version": os_info["os_version"],
        }

        url = f"{self._api_base_url}{LICENSE_VERIFY_ENDPOINT}"
        logger.info(f"Verifying license at {url}...")

        try:
            response = requests.post(url, json=payload, timeout=15)
            data = response.json()

            if response.status_code == 200 and data.get("success"):
                # Kích hoạt thành công → Lưu vào DB cục bộ
                self._save_activation(license_key, data)
                return {
                    "success": True,
                    "message": data.get("message", "Kích hoạt thành công!"),
                    "plan": data.get("plan", "Standard"),
                    "expires_at": data.get("expires_at"),
                }
            else:
                return {
                    "success": False,
                    "message": data.get("message", "License Key không hợp lệ hoặc đã hết hạn."),
                }

        except requests.ConnectionError:
            # Không có mạng → cho phép offline nếu đã kích hoạt trước đó
            if self.is_activated_locally():
                return {
                    "success": True,
                    "message": "Chế độ Offline. Đã xác thực trước đó.",
                    "plan": self._get_cached_plan(),
                    "offline": True,
                }
            return {
                "success": False,
                "message": "Không thể kết nối tới máy chủ. Vui lòng kiểm tra mạng.",
            }
        except requests.Timeout:
            return {
                "success": False,
                "message": "Máy chủ không phản hồi. Vui lòng thử lại sau.",
            }
        except Exception as e:
            logger.error(f"License verify error: {e}")
            return {
                "success": False,
                "message": f"Lỗi không xác định: {str(e)}",
            }

    # ──────────────────────────────────────────────────────────────
    # 4. LƯU TRẠNG THÁI KÍCH HOẠT VÀO DB CỤC BỘ
    # ──────────────────────────────────────────────────────────────
    def _save_activation(self, license_key: str, server_data: dict):
        """Lưu thông tin kích hoạt vào app_configs (SQLite)."""
        configs = {
            "license_key": license_key,
            "license_jwt": server_data.get("token", ""),
            "license_plan": server_data.get("plan", "Standard"),
            "license_expires": server_data.get("expires_at", ""),
            "license_hwid": self.get_hwid(),
        }
        for key, value in configs.items():
            self.db.execute_query(
                "INSERT OR REPLACE INTO app_configs (key, value) VALUES (?, ?)",
                (key, str(value)),
                commit=True,
            )
        logger.info("License activation saved to local DB.")

    def _get_cached_plan(self) -> str:
        """Đọc plan đã cache."""
        row = self.db.fetch_one(
            "SELECT value FROM app_configs WHERE key = ?", ("license_plan",)
        )
        return row["value"] if row else "Standard"

    def clear_license(self):
        """Xoá toàn bộ dữ liệu license cục bộ (dùng khi Deactivate/Logout)."""
        keys = ["license_key", "license_jwt", "license_plan",
                "license_expires", "license_hwid"]
        for key in keys:
            self.db.execute_query(
                "DELETE FROM app_configs WHERE key = ?", (key,), commit=True
            )
        logger.info("License data cleared from local DB.")
