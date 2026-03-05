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
    ENC_PREFIX_V1 = "enc:v1:"

    @classmethod
    def _pack_credentials(cls, credentials_dict) -> str:
        plain = json.dumps(credentials_dict)
        encrypted = SecurityUtils.encrypt(plain)
        if not encrypted:
            return ""
        return f"{cls.ENC_PREFIX_V1}{encrypted}"

    @classmethod
    def _unpack_credentials_text(cls, stored: str) -> str:
        text = str(stored or "")
        if not text:
            return ""

        # New format with explicit prefix.
        if text.startswith(cls.ENC_PREFIX_V1):
            token = text[len(cls.ENC_PREFIX_V1):].strip()
            return SecurityUtils.decrypt(token)

        # Legacy format: thử decrypt token Fernet cũ.
        if SecurityUtils.is_probably_fernet_token(text):
            legacy_dec = SecurityUtils.decrypt(text)
            if legacy_dec:
                return legacy_dec

        # Legacy plaintext fallback (trước khi mã hoá).
        return text

    @classmethod
    def migrate_credentials_encryption(cls):
        """
        Migration one-way:
        - credentials plaintext hoặc token cũ không prefix -> chuẩn hoá sang enc:v1:<token>.
        - Idempotent: chạy nhiều lần vẫn an toàn.
        """
        try:
            rows = db.fetch_all("SELECT id, credentials FROM vault_resources WHERE COALESCE(credentials, '') <> ''")
            migrated = 0
            for row in rows:
                raw = str(row.get("credentials") or "")
                if raw.startswith(cls.ENC_PREFIX_V1):
                    continue
                plain = cls._unpack_credentials_text(raw)
                if not plain:
                    continue
                encrypted = SecurityUtils.encrypt(plain)
                if not encrypted:
                    continue
                wrapped = f"{cls.ENC_PREFIX_V1}{encrypted}"
                if wrapped == raw:
                    continue
                db.execute_query(
                    "UPDATE vault_resources SET credentials = ? WHERE id = ?",
                    (wrapped, row.get("id")),
                    commit=True
                )
                migrated += 1
            if migrated:
                logger.info(f"Migrated vault credentials: {migrated} row(s).")
        except Exception as e:
            logger.warning(f"Vault credential migration failed: {e}")

    @staticmethod
    def get_all_resources():
        """Lấy danh sách tất cả resources, giải mã credentials."""
        try:
            rows = db.fetch_all("SELECT * FROM vault_resources ORDER BY id DESC")
            for row in rows:
                if row.get("credentials"):
                    # Giải mã credentials (thường là JSON string chứa pass/key)
                    decrypted = VaultManager._unpack_credentials_text(row["credentials"])
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
            encrypted_creds = VaultManager._pack_credentials(credentials_dict)
            
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
            encrypted_creds = VaultManager._pack_credentials(credentials_dict)
            
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
