"""
OmniMind - Entry Point
Khởi chạy ứng dụng: License Gate → Main Window.
Tích hợp License Manager: Tự động skip Gate nếu đã kích hoạt trước đó.
"""
import sys
import os
import logging
import sqlite3
import platform
from pathlib import Path
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def _get_local_db_path() -> Path:
    env_db = os.environ.get("OMNIMIND_DB_PATH", "").strip()
    if env_db:
        db_path = Path(env_db).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path

    sys_name = platform.system()
    if sys_name == "Windows":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        data_dir = Path(base) / "OmniMind" / "data"
    elif sys_name == "Darwin":
        data_dir = Path(os.path.expanduser("~/Library/Application Support")) / "OmniMind" / "data"
    else:
        data_dir = Path(os.path.expanduser("~/.omnimind")) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "omnimind.db"


def _read_config_value_raw(key: str, default: str = "") -> str:
    db_path = _get_local_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_configs WHERE key = ?", (key,))
        row = cursor.fetchone()
        return str(row[0]) if row and row[0] is not None else default
    except Exception:
        return default
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _set_config_value_raw(key: str, value: str):
    db_path = _get_local_db_path()
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS app_configs (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute(
            "INSERT INTO app_configs (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Cannot persist raw config {key}: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _configure_runtime_logging():
    """
    Bật logging tập trung vào file runtime để dễ monitoring + rollback điều tra.
    """
    try:
        db_path = _get_local_db_path()
        data_dir = db_path.parent
        app_root = data_dir.parent if data_dir.name == "data" else data_dir
        logs_dir = app_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / "omnimind_app.log"

        root = logging.getLogger()
        has_file_handler = any(
            isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "").endswith("omnimind_app.log")
            for h in root.handlers
        )
        if not has_file_handler:
            fh = RotatingFileHandler(str(log_file), maxBytes=8 * 1024 * 1024, backupCount=5, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s"))
            fh.setLevel(logging.INFO)
            root.addHandler(fh)
        root.setLevel(logging.INFO)
    except Exception as e:
        logger.warning(f"Cannot setup runtime file logging: {e}")


def _rollback_to_previous_payload(reason: str):
    default_version = os.environ.get("OMNIMIND_APP_VERSION", "1.0.0")
    prev_path = _read_config_value_raw("app_payload_prev_path", "").strip()
    prev_version = _read_config_value_raw("app_payload_prev_version", "").strip()
    restored = False
    if prev_path and (Path(prev_path).expanduser() / "src").is_dir():
        _set_config_value_raw("app_payload_path", prev_path)
        _set_config_value_raw("app_payload_version", prev_version)
        _set_config_value_raw("app_current_version", prev_version or default_version)
        restored = True
    else:
        _set_config_value_raw("app_payload_path", "")
        _set_config_value_raw("app_payload_version", "")
        _set_config_value_raw("app_current_version", default_version)
    _set_config_value_raw("app_update_pending_restart", "false")
    _set_config_value_raw("app_payload_boot_status", "rolled_back")
    _set_config_value_raw("app_payload_boot_attempts", "0")
    _set_config_value_raw("app_payload_last_error", str(reason or "payload_boot_failed"))
    logger.warning(f"Rollback payload update: restored_previous={restored}, reason={reason}")


def _bootstrap_update_overlay():
    """
    Load payload update từ thư mục dữ liệu user (nếu có) trước khi import phần còn lại.
    Cơ chế này tránh thay app bundle trên macOS, giúp giữ nguyên quyền đã cấp.
    """
    try:
        payload_path = _read_config_value_raw("app_payload_path", "").strip()
        payload_version = _read_config_value_raw("app_payload_version", "").strip()
        current_version = _read_config_value_raw("app_current_version", "").strip()
        default_version = os.environ.get("OMNIMIND_APP_VERSION", "1.0.0")
        boot_status = _read_config_value_raw("app_payload_boot_status", "").strip().lower()
        try:
            boot_attempts = int(_read_config_value_raw("app_payload_boot_attempts", "0") or 0)
        except Exception:
            boot_attempts = 0

        if not payload_path:
            if not current_version:
                _set_config_value_raw("app_current_version", default_version)
            return

        # Nếu payload đang pending mà đã từng thử boot >= 1 lần, coi như payload lỗi boot.
        if boot_status == "pending" and boot_attempts >= 1:
            _rollback_to_previous_payload("payload_boot_failed_previous_launch")
            payload_path = _read_config_value_raw("app_payload_path", "").strip()
            payload_version = _read_config_value_raw("app_payload_version", "").strip()
            if not payload_path:
                return
            boot_status = _read_config_value_raw("app_payload_boot_status", "").strip().lower()

        src_dir = Path(payload_path).expanduser() / "src"
        if not src_dir.is_dir():
            # Payload không còn tồn tại -> tự chữa để app chạy fallback bản gốc.
            _set_config_value_raw("app_payload_path", "")
            _set_config_value_raw("app_payload_version", "")
            _set_config_value_raw("app_update_pending_restart", "false")
            if not current_version:
                _set_config_value_raw("app_current_version", default_version)
            return

        if boot_status == "pending":
            _set_config_value_raw("app_payload_boot_attempts", str(max(0, boot_attempts) + 1))

        src_path = str(src_dir)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        if payload_version:
            os.environ["OMNIMIND_APP_VERSION"] = payload_version
            _set_config_value_raw("app_current_version", payload_version)
        _set_config_value_raw("app_update_pending_restart", "false")
    except Exception as e:
        logger.warning(f"Update overlay bootstrap warning: {e}")


def _mark_payload_boot_success():
    try:
        status = _read_config_value_raw("app_payload_boot_status", "").strip().lower()
        if status != "pending":
            return
        _set_config_value_raw("app_payload_boot_status", "active")
        _set_config_value_raw("app_payload_boot_attempts", "0")
        _set_config_value_raw("app_payload_last_error", "")
        logger.info("Payload update marked as active after successful boot.")
    except Exception as e:
        logger.warning(f"Cannot mark payload boot success: {e}")


def _consume_minimized_flag(argv: list[str]) -> tuple[list[str], bool]:
    cleaned = []
    minimized = False
    for arg in argv:
        if arg == "--minimized":
            minimized = True
            continue
        cleaned.append(arg)
    return cleaned, minimized


def main():
    # Đồng bộ DB path ổn định trước khi import các module có thể khởi tạo DB singleton.
    os.environ["OMNIMIND_DB_PATH"] = str(_get_local_db_path())
    _configure_runtime_logging()
    _bootstrap_update_overlay()

    # Chuẩn hóa CODEX_HOME ngay khi app khởi động để các module dùng cùng 1 path skills/auth.
    from engine.config_manager import ConfigManager
    os.environ["CODEX_HOME"] = ConfigManager.get_codex_home()

    # Enable High DPI trước khi tạo QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    qt_argv, start_minimized = _consume_minimized_flag(sys.argv)
    app = QApplication(qt_argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    from engine.telegram_bot_service import stop_global_telegram_bot_service
    app.aboutToQuit.connect(stop_global_telegram_bot_service)

    # Load stylesheet
    try:
        styles_path = os.path.join(os.path.dirname(__file__), "ui", "styles.qss")
        with open(styles_path, "r") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        print(f"[OmniMind] Warning: Could not load stylesheet: {e}")

    # ── License Gatekeeper ──
    # Kiểm tra DB xem đã có license_key hợp lệ chưa.
    from engine.license_manager import LicenseManager
    license_mgr = LicenseManager()

    if not license_mgr.is_activated_locally():
        # Chưa kích hoạt → Hiện popup License
        from ui.license_screen import LicenseScreen
        license_dialog = LicenseScreen()
        result = license_dialog.exec_()

        if result != LicenseScreen.Accepted:
            # Người dùng đóng popup mà không kích hoạt → Thoát app
            sys.exit(0)

    # Đồng bộ entitlement ngay khi mở app để plan/expiry/purchased skills luôn mới.
    try:
        license_key = license_mgr.get_saved_license()
        if license_key:
            license_mgr.sync_entitlements(license_key)
    except Exception as e:
        print(f"[OmniMind] Warning: Entitlement sync failed: {e}")

    # ── Main Application ──
    from ui.main_window import MainWindow
    window = MainWindow()
    if start_minimized:
        window.hide()
    else:
        window.show()
    _mark_payload_boot_success()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
