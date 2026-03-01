import logging
from database.db_manager import db

logger = logging.getLogger(__name__)

class MemoryManager:
    """
    Quản lý các quy tắc trí nhớ (Memory Rules) lưu trong SQLite.
    Thực hiện các thao tác CRUD để UI gọi tới.
    """

    @staticmethod
    def get_all_rules():
        """Lấy danh sách tất cả quy tắc."""
        try:
            return db.fetch_all("SELECT * FROM memory_rules ORDER BY id DESC")
        except Exception as e:
            logger.error(f"Error fetching memory rules: {e}")
            return []

    @staticmethod
    def add_rule(title, content, is_active=True):
        """Thêm quy tắc mới."""
        try:
            db.execute_query(
                "INSERT INTO memory_rules (title, content, is_active) VALUES (?, ?, ?)",
                (title, content, 1 if is_active else 0),
                commit=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding memory rule: {e}")
            return False

    @staticmethod
    def update_rule(rule_id, title, content, is_active):
        """Cập nhật quy tắc hiện có."""
        try:
            db.execute_query(
                "UPDATE memory_rules SET title = ?, content = ?, is_active = ? WHERE id = ?",
                (title, content, 1 if is_active else 0, rule_id),
                commit=True
            )
            return True
        except Exception as e:
            logger.error(f"Error updating memory rule {rule_id}: {e}")
            return False

    @staticmethod
    def delete_rule(rule_id):
        """Xoá quy tắc."""
        try:
            db.execute_query("DELETE FROM memory_rules WHERE id = ?", (rule_id,), commit=True)
            return True
        except Exception as e:
            logger.error(f"Error deleting memory rule {rule_id}: {e}")
            return False

    @staticmethod
    def toggle_rule_status(rule_id, is_active):
        """Bật/Tắt quy tắc nhanh."""
        try:
            db.execute_query(
                "UPDATE memory_rules SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, rule_id),
                commit=True
            )
            return True
        except Exception as e:
            logger.error(f"Error toggling rule {rule_id}: {e}")
            return False
