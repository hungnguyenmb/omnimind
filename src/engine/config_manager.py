import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from database.db_manager import db

logger = logging.getLogger(__name__)
DEFAULT_API_BASE_URL = "https://license.vinhyenit.com"
ENC_PREFIX_V1 = "enc:v1:"

class ConfigManager:
    """
    Quản lý cấu hình ứng dụng lưu trong bảng app_configs (SQLite).
    Hỗ trợ Save/Load cho Telegram Token, Chat ID, Workspace Path, v.v.
    """
    SENSITIVE_KEYS = {
        "telegram_token",
        "license_jwt",
    }

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        return str(key or "").strip().lower() in cls.SENSITIVE_KEYS

    @staticmethod
    def _get_raw_value(key: str, default: str = "") -> str:
        try:
            row = db.fetch_one("SELECT value FROM app_configs WHERE key = ?", (key,))
            return str(row["value"]) if row and row.get("value") is not None else default
        except Exception as e:
            logger.error(f"Error reading raw config {key}: {e}")
            return default

    @staticmethod
    def _set_raw_value(key: str, value: str):
        db.execute_query(
            "INSERT INTO app_configs (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, str(value), str(value)),
            commit=True
        )

    @classmethod
    def _decode_sensitive_if_needed(cls, key: str, raw_value: str, default: str = "") -> str:
        if not cls._is_sensitive_key(key):
            return raw_value
        text = str(raw_value or "")
        if not text:
            return default
        if not text.startswith(ENC_PREFIX_V1):
            # Legacy plaintext data trước migration.
            return text
        token = text[len(ENC_PREFIX_V1):].strip()
        if not token:
            return default
        try:
            from engine.security_utils import SecurityUtils
            plain = SecurityUtils.decrypt(token)
            return plain if plain else default
        except Exception as e:
            logger.warning(f"Cannot decrypt config {key}: {e}")
            return default

    @classmethod
    def _encode_sensitive_if_needed(cls, key: str, value: str) -> str:
        text = str(value or "")
        if not cls._is_sensitive_key(key):
            return text
        if not text:
            return ""
        try:
            from engine.security_utils import SecurityUtils
            token = SecurityUtils.encrypt(text)
            if not token:
                raise RuntimeError(f"Encrypt sensitive config failed for key={key}")
            return f"{ENC_PREFIX_V1}{token}"
        except Exception as e:
            raise RuntimeError(f"Encrypt sensitive config exception key={key}: {e}") from e

    @classmethod
    def migrate_sensitive_configs(cls):
        """
        Migration one-way:
        - Key nhạy cảm đang ở plaintext -> mã hoá enc:v1:<token>.
        - Idempotent, an toàn khi chạy nhiều lần.
        """
        migrated = 0
        for key in cls.SENSITIVE_KEYS:
            raw = cls._get_raw_value(key, "")
            if not raw or str(raw).startswith(ENC_PREFIX_V1):
                continue
            encoded = cls._encode_sensitive_if_needed(key, raw)
            if encoded and encoded != raw:
                try:
                    cls._set_raw_value(key, encoded)
                    migrated += 1
                except Exception as e:
                    logger.warning(f"Migrate sensitive key failed ({key}): {e}")
        if migrated:
            logger.info(f"Migrated sensitive app_configs: {migrated} key(s).")

    @staticmethod
    def get(key: str, default: str = "") -> str:
        """Lấy giá trị cấu hình theo key."""
        try:
            raw = ConfigManager._get_raw_value(key, default)
            return ConfigManager._decode_sensitive_if_needed(key, raw, default)
        except Exception as e:
            logger.error(f"Error getting config {key}: {e}")
            return default

    @staticmethod
    def set(key: str, value: str):
        """Lưu hoặc cập nhật giá value cho key."""
        try:
            stored = ConfigManager._encode_sensitive_if_needed(key, str(value or ""))
            ConfigManager._set_raw_value(key, stored)
            masked = "***" if ConfigManager._is_sensitive_key(key) and str(value or "") else str(value)
            logger.info(f"Config updated: {key} = {masked}")
            return True
        except Exception as e:
            logger.error(f"Error setting config {key}: {e}")
            return False

    @classmethod
    def get_telegram_config(cls):
        """Helper lấy bộ cấu hình Telegram."""
        return {
            "token": cls.get("telegram_token"),
            "chat_id": cls.get("telegram_chat_id")
        }

    @classmethod
    def set_telegram_config(cls, token: str, chat_id: str):
        """Helper lưu bộ cấu hình Telegram."""
        cls.set("telegram_token", token)
        cls.set("telegram_chat_id", chat_id)

    @classmethod
    def get_workspace_path(cls):
        return cls.get("workspace_path")

    @classmethod
    def set_workspace_path(cls, path: str):
        cls.set("workspace_path", path)

    @classmethod
    def get_api_base_url(cls) -> str:
        """
        Resolve API base URL theo thứ tự ưu tiên:
        1) ENV OMNIMIND_API_URL
        2) DB app_configs: omnimind_api_url / OMNIMIND_API_URL
        3) Mặc định production VPS
        """
        env_val = os.environ.get("OMNIMIND_API_URL", "").strip()
        if env_val:
            return env_val
        cfg_val = (cls.get("omnimind_api_url", "").strip() or cls.get("OMNIMIND_API_URL", "").strip())
        if cfg_val:
            return cfg_val
        return DEFAULT_API_BASE_URL

    @classmethod
    def set_api_base_url(cls, url: str):
        normalized = str(url or "").strip().rstrip("/")
        if not normalized:
            normalized = DEFAULT_API_BASE_URL
        cls.set("omnimind_api_url", normalized)
        cls.set("OMNIMIND_API_URL", normalized)

    @classmethod
    def get_codex_home(cls) -> str:
        """
        Resolve CODEX_HOME theo thứ tự ưu tiên:
        1) ENV CODEX_HOME
        2) DB app_configs: codex_home / CODEX_HOME
        3) Mặc định ~/.codex
        """
        env_val = os.environ.get("CODEX_HOME", "").strip()
        if env_val:
            return str(Path(env_val).expanduser())

        cfg_val = (cls.get("codex_home", "").strip() or cls.get("CODEX_HOME", "").strip())
        if cfg_val:
            return str(Path(cfg_val).expanduser())

        return str(Path.home() / ".codex")

    @classmethod
    def set_codex_home(cls, path: str):
        normalized = str(Path(path).expanduser())
        cls.set("codex_home", normalized)
        cls.set("CODEX_HOME", normalized)

    @classmethod
    def get_codex_model(cls) -> str:
        val = cls.get("codex_model", "").strip()
        return val or "gpt-5.3-codex"

    @classmethod
    def set_codex_model(cls, model: str):
        cls.set("codex_model", str(model or "").strip())

    @classmethod
    def get_codex_approval_policy(cls) -> str:
        val = cls.get("codex_approval_policy", "").strip()
        if val in {"untrusted", "on-request", "never", "on-failure"}:
            return val
        legacy = cls.get("approval_policy", "").strip()
        if legacy in {"untrusted", "on-request", "never", "on-failure"}:
            return legacy
        return "on-request"

    @classmethod
    def set_codex_approval_policy(cls, policy: str):
        normalized = str(policy or "").strip()
        if normalized not in {"untrusted", "on-request", "never", "on-failure"}:
            normalized = "on-request"
        cls.set("codex_approval_policy", normalized)
        cls.set("approval_policy", normalized)

    @classmethod
    def get_sandbox_mode(cls) -> str:
        """
        Chuẩn hóa lựa chọn Sandbox UI thành mode dùng cho runtime/env.
        """
        new_val = cls.get("codex_sandbox_mode", "").strip()
        if new_val in {"read-only", "workspace-write", "danger-full-access"}:
            return new_val

        legacy_mode = cls.get("sandbox_mode", "").strip()
        if legacy_mode in {"read-only", "workspace-write", "danger-full-access"}:
            return legacy_mode

        val = cls.get("sandbox_permission", "").strip()
        if "read-only" in val.lower() or "chỉ đọc" in val.lower():
            return "read-only"
        if "full" in val.lower() or "danger" in val.lower() or "toàn quyền" in val.lower():
            return "danger-full-access"
        return "workspace-write"

    @classmethod
    def set_sandbox_mode(cls, mode: str):
        normalized = str(mode or "").strip()
        if normalized not in {"read-only", "workspace-write", "danger-full-access"}:
            normalized = "workspace-write"
        cls.set("codex_sandbox_mode", normalized)
        cls.set("sandbox_mode", normalized)

    @classmethod
    def get_zalo_profile_name(cls) -> str:
        val = cls.get("zalo_profile_name", "").strip()
        return val or "omnimind"

    @classmethod
    def set_zalo_profile_name(cls, profile_name: str):
        normalized = str(profile_name or "").strip() or "omnimind"
        cls.set("zalo_profile_name", normalized)

    @classmethod
    def get_zalo_runtime_config(cls) -> dict:
        return {
            "profile_name": cls.get_zalo_profile_name(),
            "openzca_version": cls.get("zalo_openzca_version", "").strip(),
            "install_status": cls.get("zalo_openzca_install_status", "not_installed").strip() or "not_installed",
            "last_error": cls.get("zalo_runtime_last_error", "").strip(),
            "last_checked_at": cls.get("zalo_runtime_last_checked_at", "").strip(),
        }

    @classmethod
    def set_zalo_runtime_status(
        cls,
        install_status: str,
        version: str = "",
        last_error: str = "",
        checked_at: str = "",
    ):
        status_value = str(install_status or "").strip() or "not_installed"
        cls.set("zalo_openzca_install_status", status_value)
        cls.set("zalo_openzca_version", str(version or "").strip())
        cls.set("zalo_runtime_last_error", str(last_error or "").strip())
        checked_value = str(checked_at or "").strip()
        if not checked_value:
            checked_value = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        cls.set("zalo_runtime_last_checked_at", checked_value)

    @classmethod
    def get_zalo_login_state(cls) -> str:
        value = cls.get("zalo_login_state", "").strip().lower()
        if value in {"not_logged_in", "qr_required", "connected", "re_auth_required"}:
            return value
        legacy = cls.get("zalo_login_state", "").strip()
        if legacy == "Re-auth required":
            return "re_auth_required"
        return "not_logged_in"

    @classmethod
    def set_zalo_login_state(
        cls,
        login_state: str,
        self_user_id: str = "",
        last_connected_at: str = "",
        last_auth_ok_at: str = "",
        last_heartbeat_at: str = "",
        last_reauth_alert_at: str = "",
        last_monitor_error: str = "",
        qr_path: str = "",
        qr_requested_at: str = "",
    ):
        normalized = str(login_state or "").strip().lower()
        if normalized not in {"not_logged_in", "qr_required", "connected", "re_auth_required"}:
            normalized = "not_logged_in"
        cls.set("zalo_login_state", normalized)
        if self_user_id != "":
            cls.set("zalo_self_user_id", str(self_user_id or "").strip())
        if last_connected_at != "":
            cls.set("zalo_last_connected_at", str(last_connected_at or "").strip())
        if last_auth_ok_at != "":
            cls.set("zalo_last_auth_ok_at", str(last_auth_ok_at or "").strip())
        if last_heartbeat_at != "":
            cls.set("zalo_last_heartbeat_at", str(last_heartbeat_at or "").strip())
        if last_reauth_alert_at != "":
            cls.set("zalo_last_reauth_alert_at", str(last_reauth_alert_at or "").strip())
        if last_monitor_error != "":
            cls.set("zalo_last_monitor_error", str(last_monitor_error or "").strip())
        if qr_path != "":
            cls.set("zalo_qr_path", str(qr_path or "").strip())
        if qr_requested_at != "":
            cls.set("zalo_qr_requested_at", str(qr_requested_at or "").strip())

    @classmethod
    def get_zalo_connection_status(cls) -> dict:
        return {
            "login_state": cls.get_zalo_login_state(),
            "self_user_id": cls.get("zalo_self_user_id", "").strip(),
            "last_connected_at": cls.get("zalo_last_connected_at", "").strip(),
            "last_auth_ok_at": cls.get("zalo_last_auth_ok_at", "").strip(),
            "last_heartbeat_at": cls.get("zalo_last_heartbeat_at", "").strip(),
            "last_reauth_alert_at": cls.get("zalo_last_reauth_alert_at", "").strip(),
            "last_monitor_error": cls.get("zalo_last_monitor_error", "").strip(),
            "qr_path": cls.get("zalo_qr_path", "").strip(),
            "qr_requested_at": cls.get("zalo_qr_requested_at", "").strip(),
        }
