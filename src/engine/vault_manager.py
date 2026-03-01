import logging
import json
from database.db_manager import db
from engine.security_utils import SecurityUtils

logger = logging.getLogger(__name__)

class VaultManager:
    """
    Quản lý Kho tài nguyên (Vault Resources) trong SQLite.
    Tự động mã hoá 'credentials' (mật khẩu/key) trước khi lưu.
    """

    @staticmethod
    def get_all_resources():
        """Lấy danh sách tất cả resources, giải mã credentials."""
        try:
            rows = db.fetch_all("SELECT * FROM vault_resources ORDER BY id DESC")
            for row in rows:
                if row.get("credentials"):
                    # Giải mã credentials (thường là JSON string chứa pass/key)
                    decrypted = SecurityUtils.decrypt(row["credentials"])
                    try:
                        row["credentials_data"] = json.loads(decrypted)
                    except json.JSONDecodeError:
                        row["credentials_data"] = {}
            return rows
        except Exception as e:
            logger.error(f"Error fetching vault resources: {e}")
            return []

    @staticmethod
    def add_resource(res_type, identifier, username, credentials_dict, description):
        """Thêm resource mới, mã hoá credentials."""
        try:
            # Chuyển credentials sang JSON then mã hoá
            encrypted_creds = SecurityUtils.encrypt(json.dumps(credentials_dict))
            
            db.execute_query(
                "INSERT INTO vault_resources (type, identifier, username, credentials, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (res_type, identifier, username, encrypted_creds, description),
                commit=True
            )
            return True
        except Exception as e:
            logger.error(f"Error adding vault resource: {e}")
            return False

    @staticmethod
    def update_resource(res_id, res_type, identifier, username, credentials_dict, description):
        """Cập nhật resource."""
        try:
            encrypted_creds = SecurityUtils.encrypt(json.dumps(credentials_dict))
            
            db.execute_query(
                "UPDATE vault_resources SET type = ?, identifier = ?, username = ?, "
                "credentials = ?, description = ? WHERE id = ?",
                (res_type, identifier, username, encrypted_creds, description, res_id),
                commit=True
            )
            return True
        except Exception as e:
            logger.error(f"Error updating vault resource {res_id}: {e}")
            return False

    @staticmethod
    def delete_resource(res_id):
        """Xoá resource."""
        try:
            db.execute_query("DELETE FROM vault_resources WHERE id = ?", (res_id,), commit=True)
            return True
        except Exception as e:
            logger.error(f"Error deleting vault resource {res_id}: {e}")
            return False
