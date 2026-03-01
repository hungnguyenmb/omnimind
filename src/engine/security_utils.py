import logging
import base64
from cryptography.fernet import Fernet
from engine.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class SecurityUtils:
    """
    Tiện ích mã hoá và giải mã dữ liệu nhạy cảm.
    Sử dụng thuật toán Fernet (AES). Key được lưu trong database để đảm bảo 
    khả năng giải mã sau khi khởi động lại app.
    """
    _fernet = None

    @classmethod
    def _get_fernet(cls):
        if cls._fernet is None:
            # Thử lấy key từ DB
            key = ConfigManager.get("security_encryption_key")
            if not key:
                # Nếu chưa có -> tạo mới và lưu lại
                logger.info("Generating new encryption key for Vault...")
                key = Fernet.generate_key().decode()
                ConfigManager.set("security_encryption_key", key)
            
            try:
                cls._fernet = Fernet(key.encode())
            except Exception as e:
                logger.error(f"Failed to initialize Fernet with key: {e}")
                # Nếu lỗi key cũ, tạo key mới (cảnh báo: sẽ không giải mã được dữ liệu cũ)
                key = Fernet.generate_key().decode()
                ConfigManager.set("security_encryption_key", key)
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
            logger.error(f"Decryption error: {e}")
            return "[ENCRYPTED_DATA]"
