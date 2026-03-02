import sqlite3
import os
import threading
import logging
import platform
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

class DBManager:
    """
    Quản lý kết nối Cơ sở dữ liệu SQLite cục bộ (Client-Side).
    Sử dụng mẫu Singleton và Thread-Lock để đảm bảo an toàn khi
    cả UI Thread và Bot Engine Thread cùng truy cập.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBManager, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path=None):
        if self._initialized:
            return

        # Ưu tiên DB path ổn định theo user profile để tránh lệch dữ liệu khi update payload.
        if db_path is None:
            env_db = os.environ.get("OMNIMIND_DB_PATH", "").strip()
            if env_db:
                self.db_path = str(Path(env_db).expanduser())
            else:
                self.db_path = str(self._default_db_path())
        else:
            self.db_path = str(Path(db_path).expanduser())

        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_db_if_needed(db_file)

        self._db_lock = threading.Lock()
        self.init_db()
        self._initialized = True

    @staticmethod
    def _default_db_path() -> Path:
        sys_name = platform.system()
        if sys_name == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            return Path(base) / "OmniMind" / "data" / "omnimind.db"
        if sys_name == "Darwin":
            return Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind" / "data" / "omnimind.db"
        return Path(os.path.expanduser("~/.omnimind")) / "data" / "omnimind.db"

    @staticmethod
    def _legacy_db_candidates() -> list[Path]:
        # Legacy path từng dùng theo source tree (gây lệch khi chạy từ payload update)
        source_relative = Path(__file__).resolve().parents[2] / "data" / "omnimind.db"
        cwd_relative = Path.cwd() / "data" / "omnimind.db"
        candidates = [source_relative, cwd_relative]
        unique = []
        for path in candidates:
            if path not in unique:
                unique.append(path)
        return unique

    def _migrate_legacy_db_if_needed(self, target_db: Path):
        if target_db.exists():
            return
        for legacy in self._legacy_db_candidates():
            if not legacy.exists():
                continue
            try:
                if legacy.resolve() == target_db.resolve():
                    continue
            except Exception:
                pass

            try:
                shutil.copy2(legacy, target_db)
                logger.info(f"Migrated legacy DB from {legacy} -> {target_db}")
                return
            except Exception as e:
                logger.warning(f"Failed to migrate DB from {legacy}: {e}")

    def get_connection(self):
        """Trả về connection mới. Tránh lỗi thread."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Trả về dict-like thay vì tuple
        return conn

    def init_db(self):
        """Tạo các bảng cục bộ [CLIENT-SQLITE] và Cache [BOTH] nếu chưa tồn tại"""
        logger.info(f"Initializing database at {self.db_path}")
        with self._db_lock:
            conn = self.get_connection()
            cursor = conn.cursor()

            try:
                # 1. app_configs [CLIENT-SQLITE]
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS app_configs (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                ''')

                # 2. memory_rules [CLIENT-SQLITE]
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS memory_rules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        content TEXT,
                        is_active BOOLEAN DEFAULT 1
                    )
                ''')

                # 3. vault_resources [CLIENT-SQLITE]
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS vault_resources (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        type TEXT,
                        identifier TEXT,
                        username TEXT,
                        credentials TEXT,
                        description TEXT
                    )
                ''')

                # 4. marketplace_skills [BOTH] (Cache)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS marketplace_skills (
                        id TEXT PRIMARY KEY,
                        name TEXT,
                        description TEXT,
                        skill_type TEXT,
                        price REAL,
                        author TEXT,
                        version TEXT,
                        manifest_json TEXT,
                        is_vip BOOLEAN
                    )
                ''')

                # 5. purchased_skills [BOTH] (Cache/Receipt)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS purchased_skills (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        skill_id TEXT,
                        license_key TEXT,
                        purchased_at TIMESTAMP
                    )
                ''')

                # 6. installed_skills [CLIENT-SQLITE]
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS installed_skills (
                        skill_id TEXT PRIMARY KEY,
                        name TEXT,
                        version TEXT,
                        local_path TEXT,
                        installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 7. app_versions [BOTH] (Cache)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS app_versions (
                        version_id TEXT PRIMARY KEY,
                        version_name TEXT,
                        release_date TIMESTAMP,
                        is_critical BOOLEAN
                    )
                ''')

                # 8. license_details [BOTH] (Cache)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS license_details (
                        license_key TEXT PRIMARY KEY,
                        plan_id TEXT,
                        status TEXT,
                        issued_source TEXT,
                        activated_at TIMESTAMP,
                        expires_at TIMESTAMP
                    )
                ''')

                # 9. skill_capabilities [CLIENT-SQLITE]
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS skill_capabilities (
                        skill_id TEXT PRIMARY KEY,
                        capabilities_json TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 10. action_audit_logs [CLIENT-SQLITE]
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS action_audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        action_id TEXT,
                        capability TEXT,
                        status TEXT,
                        detail TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                conn.commit()
                logger.info("Database initialized successfully.")
            except Exception as e:
                logger.error(f"Error initializing DB: {e}")
                conn.rollback()
                raise e
            finally:
                conn.close()

    def execute_query(self, query, params=(), commit=False):
        """Thực thi query an toàn (cho INSERT, UPDATE, DELETE)"""
        with self._db_lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                if commit:
                    conn.commit()
                return cursor.lastrowid
            except Exception as e:
                conn.rollback()
                logger.error(f"DB Execute Error: {e} - Query: {query}")
                raise e
            finally:
                conn.close()

    def fetch_all(self, query, params=()):
        """Lấy nhiều bản ghi"""
        with self._db_lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"DB Fetch All Error: {e} - Query: {query}")
                raise e
            finally:
                conn.close()

    def fetch_one(self, query, params=()):
        """Lấy 1 bản ghi duy nhất"""
        with self._db_lock:
            conn = self.get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"DB Fetch One Error: {e} - Query: {query}")
                raise e
            finally:
                conn.close()

# Export instance for global use easily
db = DBManager()
