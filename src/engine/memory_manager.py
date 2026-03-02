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
    def get_active_rules():
        """Lấy danh sách quy tắc đang bật để inject vào prompt runtime."""
        try:
            return db.fetch_all(
                "SELECT id, title, content FROM memory_rules WHERE is_active = 1 ORDER BY id ASC"
            )
        except Exception as e:
            logger.error(f"Error fetching active memory rules: {e}")
            return []

    @staticmethod
    def build_rules_prompt(max_chars: int = 2400) -> str:
        """
        Gom các rule active thành khối text ngắn gọn để chèn vào prompt.
        """
        rules = MemoryManager.get_active_rules()
        if not rules:
            return ""

        out = []
        used = 0
        limit = max(400, int(max_chars or 2400))
        for idx, rule in enumerate(rules, start=1):
            title = str(rule.get("title") or "").strip()
            content = str(rule.get("content") or "").strip()
            if not content:
                continue
            line = f"{idx}. [{title or 'Rule'}] {content}"
            if used + len(line) > limit:
                break
            out.append(line)
            used += len(line)
        return "\n".join(out).strip()

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
