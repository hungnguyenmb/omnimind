import logging
import os
from pathlib import Path
from database.db_manager import db

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Quản lý cấu hình ứng dụng lưu trong bảng app_configs (SQLite).
    Hỗ trợ Save/Load cho Telegram Token, Chat ID, Workspace Path, v.v.
    """

    @staticmethod
    def get(key: str, default: str = "") -> str:
        """Lấy giá trị cấu hình theo key."""
        try:
            row = db.fetch_one("SELECT value FROM app_configs WHERE key = ?", (key,))
            return row["value"] if row else default
        except Exception as e:
            logger.error(f"Error getting config {key}: {e}")
            return default

    @staticmethod
    def set(key: str, value: str):
        """Lưu hoặc cập nhật giá value cho key."""
        try:
            db.execute_query(
                "INSERT INTO app_configs (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = ?",
                (key, str(value), str(value)),
                commit=True
            )
            logger.info(f"Config updated: {key} = {value}")
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
