import logging
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
