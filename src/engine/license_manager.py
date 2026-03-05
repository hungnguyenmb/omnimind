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
import requests
from engine.config_manager import ConfigManager
from engine.http_client import request_with_retry

logger = logging.getLogger(__name__)

# ─── Cấu hình API ───────────────────────────────────────────────
LICENSE_VERIFY_ENDPOINT = "/api/v1/omnimind/licenses/verify"
LICENSE_ENTITLEMENTS_ENDPOINT = "/api/v1/omnimind/licenses/{license_key}/entitlements"
LICENSE_PLANS_ENDPOINT = "/api/v1/omnimind/licenses/plans"
LICENSE_PURCHASE_ENDPOINT = "/api/v1/omnimind/licenses/purchase"
PAYMENT_ORDER_ENDPOINT = "/api/v1/omnimind/payments/orders/{order_id}"


class LicenseManager:
    """
    Engine quản lý License. Sử dụng bởi UI (license_screen.py) và main.py.
    """

    def __init__(self, db_manager=None):
        from database.db_manager import DBManager
        self.db = db_manager or DBManager()
        self._api_base_url = ConfigManager.get_api_base_url()

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
        value = str(ConfigManager.get("license_jwt", "") or "").strip()
        return value or None

    def get_saved_hwid(self) -> str | None:
        """Đọc HWID đã cache khi kích hoạt."""
        row = self.db.fetch_one(
            "SELECT value FROM app_configs WHERE key = ?", ("license_hwid",)
        )
        return row["value"] if row else None

    def get_activation_flag(self) -> bool:
        """Đọc cờ đã kích hoạt cục bộ."""
        row = self.db.fetch_one(
            "SELECT value FROM app_configs WHERE key = ?", ("license_activated",)
        )
        if not row:
            return False
        val = str(row.get("value", "")).strip().lower()
        return val in ("1", "true", "yes", "activated")

    def is_activated_locally(self) -> bool:
        """
        Kiểm tra nhanh xem thiết bị đã từng kích hoạt thành công chưa.
        Yêu cầu mới: đã kích hoạt một lần thì các lần mở app sau đi thẳng vào app.
        """
        if self.get_activation_flag():
            return True

        key = self.get_saved_license()
        token = self.get_saved_token()
        saved_hwid = self.get_saved_hwid()
        legacy_activated = bool(key and (token or saved_hwid))
        if legacy_activated:
            # Tương thích dữ liệu cũ: nếu từng lưu key + token thì nâng cấp cờ kích hoạt.
            self.db.execute_query(
                "INSERT OR REPLACE INTO app_configs (key, value) VALUES (?, ?)",
                ("license_activated", "True"),
                commit=True,
            )
            return True
        return False

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
            response = request_with_retry("POST", url, json=payload, timeout=15, max_attempts=4)
            data = response.json()

            if response.status_code == 200 and data.get("success"):
                # Kích hoạt thành công → Lưu vào DB cục bộ
                self._save_activation(license_key, data)
                # Đồng bộ entitlement mới nhất (plan/expiry/skills) để UI luôn chuẩn.
                try:
                    self.sync_entitlements(license_key)
                except Exception:
                    pass
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

    def sync_entitlements(self, license_key: str | None = None) -> dict:
        """
        Đồng bộ quyền hiện tại từ server:
        - plan, expires, trạng thái license
        - danh sách skill đã sở hữu
        Đồng thời cập nhật cache SQLite/local config để UI đọc nhanh.
        """
        key = (license_key or self.get_saved_license() or "").strip()
        if not key:
            return {"success": False, "message": "Chưa có license key để đồng bộ entitlement."}

        url = f"{self._api_base_url}{LICENSE_ENTITLEMENTS_ENDPOINT.format(license_key=key)}"
        try:
            response = request_with_retry("GET", url, timeout=15, max_attempts=4)
            data = response.json() if response.content else {}
            if response.status_code != 200 or not data.get("success"):
                return {
                    "success": False,
                    "message": data.get("message", "Không lấy được entitlement từ server."),
                    "status_code": response.status_code,
                }

            license_info = data.get("license") if isinstance(data.get("license"), dict) else {}
            entitlements = data.get("entitlements") if isinstance(data.get("entitlements"), dict) else {}
            purchased_skills = entitlements.get("purchased_skills") if isinstance(entitlements.get("purchased_skills"), list) else []

            self.db.execute_query(
                "INSERT OR REPLACE INTO app_configs (key, value) VALUES (?, ?)",
                ("license_key", key),
                commit=True,
            )
            self.db.execute_query(
                "INSERT OR REPLACE INTO app_configs (key, value) VALUES (?, ?)",
                ("license_plan", str(license_info.get("plan_id", "Standard"))),
                commit=True,
            )
            self.db.execute_query(
                "INSERT OR REPLACE INTO app_configs (key, value) VALUES (?, ?)",
                ("license_expires", str(license_info.get("expires_at", ""))),
                commit=True,
            )
            self.db.execute_query(
                "INSERT OR REPLACE INTO app_configs (key, value) VALUES (?, ?)",
                ("license_status", str(license_info.get("status", "unknown"))),
                commit=True,
            )
            self.db.execute_query(
                "INSERT OR REPLACE INTO app_configs (key, value) VALUES (?, ?)",
                ("license_activated", "True" if bool(license_info.get("is_active", False)) else "False"),
                commit=True,
            )

            self.db.execute_query(
                """
                INSERT OR REPLACE INTO license_details (license_key, plan_id, status, issued_source, activated_at, expires_at)
                VALUES (?, ?, ?, ?, COALESCE((SELECT activated_at FROM license_details WHERE license_key = ?), CURRENT_TIMESTAMP), ?)
                """,
                (
                    key,
                    str(license_info.get("plan_id", "Standard")),
                    str(license_info.get("status", "unknown")),
                    str(license_info.get("issued_source", "unknown")),
                    key,
                    str(license_info.get("expires_at", "")),
                ),
                commit=True,
            )

            self.db.execute_query(
                "DELETE FROM purchased_skills WHERE license_key = ?",
                (key,),
                commit=True,
            )
            for row in purchased_skills:
                if not isinstance(row, dict):
                    continue
                skill_id = str(row.get("skill_id", "")).strip()
                if not skill_id:
                    continue
                self.db.execute_query(
                    """
                    INSERT INTO purchased_skills (skill_id, license_key, purchased_at)
                    VALUES (?, ?, ?)
                    """,
                    (
                        skill_id,
                        key,
                        str(row.get("purchased_at", "")) or None,
                    ),
                    commit=True,
                )

            return {
                "success": True,
                "license": license_info,
                "entitlements": entitlements,
            }
        except requests.ConnectionError:
            return {"success": False, "message": "Không kết nối được máy chủ entitlement."}
        except requests.Timeout:
            return {"success": False, "message": "Timeout khi đồng bộ entitlement."}
        except Exception as e:
            logger.error(f"sync_entitlements error: {e}")
            return {"success": False, "message": str(e)}

    def fetch_license_plans(self) -> dict:
        url = f"{self._api_base_url}{LICENSE_PLANS_ENDPOINT}"
        try:
            response = request_with_retry("GET", url, timeout=15, max_attempts=4)
            data = response.json() if response.content else {}
            if response.status_code != 200 or not data.get("success"):
                return {
                    "success": False,
                    "message": data.get("message", "Không tải được bảng giá license."),
                    "code": data.get("code"),
                    "status_code": response.status_code,
                }
            plans = data.get("plans") if isinstance(data.get("plans"), list) else []
            return {"success": True, "plans": plans}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def create_license_purchase_order(self, plan_id: str, target_license_key: str = "") -> dict:
        payload = {
            "plan_id": str(plan_id or "").strip(),
            "target_license_key": str(target_license_key or "").strip(),
        }
        try:
            response = request_with_retry(
                "POST",
                f"{self._api_base_url}{LICENSE_PURCHASE_ENDPOINT}",
                json=payload,
                timeout=20,
                max_attempts=4,
            )
            data = response.json() if response.content else {}
            if response.status_code in (200, 201) and data.get("success"):
                return data
            if response.status_code == 402:
                return data
            return {
                "success": False,
                "message": data.get("message", f"Lỗi HTTP {response.status_code}"),
                "code": data.get("code"),
                "status_code": response.status_code,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_payment_order_status(self, order_id: str, order_code: str = "") -> dict:
        oid = str(order_id or "").strip()
        if not oid:
            return {"success": False, "message": "Thiếu order_id."}
        params = {}
        if order_code:
            params["order_code"] = str(order_code).strip()
        url = f"{self._api_base_url}{PAYMENT_ORDER_ENDPOINT.format(order_id=oid)}"
        try:
            response = request_with_retry("GET", url, params=params, timeout=15, max_attempts=4)
            data = response.json() if response.content else {}
            if response.status_code != 200 or not data.get("success"):
                return {
                    "success": False,
                    "message": data.get("message", "Không lấy được trạng thái giao dịch."),
                    "code": data.get("code"),
                    "status_code": response.status_code,
                }
            return {"success": True, "order": data.get("order", {})}
        except Exception as e:
            return {"success": False, "message": str(e)}

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
            "license_activated": "True",
        }
        for key, value in configs.items():
            ConfigManager.set(key, str(value))
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
                "license_expires", "license_hwid", "license_activated"]
        for key in keys:
            self.db.execute_query(
                "DELETE FROM app_configs WHERE key = ?", (key,), commit=True
            )
        logger.info("License data cleared from local DB.")
