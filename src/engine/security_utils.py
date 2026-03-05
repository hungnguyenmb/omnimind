import logging
import base64
import hashlib
import os
import platform
import uuid
from cryptography.fernet import Fernet
from engine.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class SecurityUtils:
    """
    Tiện ích mã hoá và giải mã dữ liệu nhạy cảm.
    Sử dụng thuật toán Fernet (AES).
    Data key được "wrap" theo dấu vân tay máy + salt cục bộ để giảm rủi ro copy DB sang máy khác.
    """
    _fernet = None

    @staticmethod
    def is_probably_fernet_token(value: str) -> bool:
        text = str(value or "").strip()
        # Token Fernet thường bắt đầu bằng "gAAAAA" (base64 urlsafe).
        return len(text) > 40 and text.startswith("gAAAA")

    @classmethod
    def _is_valid_fernet_key(cls, key: str) -> bool:
        try:
            Fernet(str(key or "").encode())
            return True
        except Exception:
            return False

    @staticmethod
    def _get_or_create_install_salt() -> str:
        salt = str(ConfigManager.get("security_install_salt", "") or "").strip()
        if salt:
            return salt
        generated = base64.urlsafe_b64encode(os.urandom(16)).decode()
        ConfigManager.set("security_install_salt", generated)
        return generated

    @staticmethod
    def _machine_fingerprint() -> str:
        parts = [
            platform.system(),
            platform.machine(),
            platform.node(),
            str(uuid.getnode()),
        ]
        return "|".join(str(x or "").strip() for x in parts)

    @classmethod
    def _derive_machine_wrap_key(cls, salt: str) -> str:
        seed = f"{cls._machine_fingerprint()}|{salt}".encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        return base64.urlsafe_b64encode(digest).decode()

    @classmethod
    def _wrap_data_key(cls, data_key: str) -> bool:
        try:
            salt = cls._get_or_create_install_salt()
            wrap_key = cls._derive_machine_wrap_key(salt)
            wrapper = Fernet(wrap_key.encode())
            wrapped = wrapper.encrypt(data_key.encode()).decode()
            ConfigManager.set("security_encryption_key_wrapped", wrapped)
            # Xoá key plaintext legacy sau khi wrap thành công.
            ConfigManager.set("security_encryption_key", "")
            return True
        except Exception as e:
            logger.warning(f"Cannot wrap security key: {e}")
            return False

    @classmethod
    def _unwrap_data_key(cls) -> str:
        wrapped = str(ConfigManager.get("security_encryption_key_wrapped", "") or "").strip()
        if not wrapped:
            return ""
        try:
            salt = cls._get_or_create_install_salt()
            wrap_key = cls._derive_machine_wrap_key(salt)
            wrapper = Fernet(wrap_key.encode())
            return wrapper.decrypt(wrapped.encode()).decode()
        except Exception as e:
            logger.warning(f"Cannot unwrap security key on this machine: {e}")
            return ""

    @classmethod
    def _resolve_data_key(cls) -> str:
        # 1) Ưu tiên wrapped key.
        key = cls._unwrap_data_key()
        if key and cls._is_valid_fernet_key(key):
            return key

        # 2) Fallback legacy plaintext key (cho dữ liệu cũ).
        legacy_key = str(ConfigManager.get("security_encryption_key", "") or "").strip()
        if legacy_key and cls._is_valid_fernet_key(legacy_key):
            cls._wrap_data_key(legacy_key)
            return legacy_key

        # 3) Tạo mới.
        logger.info("Generating new local encryption key...")
        key = Fernet.generate_key().decode()
        if not cls._wrap_data_key(key):
            # Fallback cuối: vẫn lưu legacy key để tránh lockout nếu wrap thất bại.
            ConfigManager.set("security_encryption_key", key)
        return key

    @classmethod
    def _get_fernet(cls):
        if cls._fernet is None:
            key = cls._resolve_data_key()
            try:
                cls._fernet = Fernet(key.encode())
            except Exception as e:
                logger.error(f"Failed to initialize Fernet with key: {e}")
                key = Fernet.generate_key().decode()
                cls._wrap_data_key(key)
                cls._fernet = Fernet(key.encode())

        return cls._fernet

    @classmethod
    def encrypt(cls, text: str) -> str:
        """Mã hoá chuỗi văn bản sang token (string)."""
        if not text:
            return ""
        try:
            f = cls._get_fernet()
            token = f.encrypt(text.encode())
            return token.decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return ""

    @classmethod
    def decrypt(cls, token_str: str) -> str:
        """Giải mã token sang văn bản gốc."""
        if not token_str:
            return ""
        try:
            f = cls._get_fernet()
            text_bytes = f.decrypt(token_str.encode())
            return text_bytes.decode()
        except Exception as e:
            logger.warning(f"Decryption error: {e}")
            return ""
