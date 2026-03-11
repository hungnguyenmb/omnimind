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
import time
from pathlib import Path
from logging.handlers import RotatingFileHandler
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from engine.process_lock import InterProcessFileLock

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)
_APP_INSTANCE_LOCK: InterProcessFileLock | None = None


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


def _get_runtime_root_dir() -> Path:
    db_path = _get_local_db_path()
    data_dir = db_path.parent
    root = data_dir.parent if data_dir.name == "data" else data_dir
    root.mkdir(parents=True, exist_ok=True)
    return root


def _acquire_app_instance_lock(wait_timeout_sec: float = 0.0) -> tuple[bool, int | None]:
    global _APP_INSTANCE_LOCK
    if _APP_INSTANCE_LOCK and _APP_INSTANCE_LOCK.is_acquired():
        return True, None

    lock = InterProcessFileLock(_get_runtime_root_dir() / "omnimind_app.instance.lock")
    wait_sec = max(0.0, float(wait_timeout_sec or 0.0))
    deadline = time.monotonic() + wait_sec
    while True:
        if lock.acquire():
            _APP_INSTANCE_LOCK = lock
            return True, None
        if time.monotonic() >= deadline:
            break
        time.sleep(0.2)
    return False, lock.read_owner_pid()


def _release_app_instance_lock():
    global _APP_INSTANCE_LOCK
    if _APP_INSTANCE_LOCK:
        _APP_INSTANCE_LOCK.release()
    _APP_INSTANCE_LOCK = None


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


def _consume_instance_wait_flag(argv: list[str]) -> tuple[list[str], float]:
    cleaned = []
    wait_sec = 0.0
    prefix = "--wait-instance-unlock="
    for arg in argv:
        if isinstance(arg, str) and arg.startswith(prefix):
            raw = arg[len(prefix) :].strip()
            try:
                wait_sec = max(0.0, min(30.0, float(raw)))
            except Exception:
                wait_sec = 0.0
            continue
        cleaned.append(arg)
    return cleaned, wait_sec


def _resolve_stylesheet_path() -> Path | None:
    """
    Resolve styles.qss for both dev mode and frozen (PyInstaller) mode.
    """
    candidates: list[Path] = []

    # Dev mode: src/main.py -> src/ui/styles.qss
    candidates.append(Path(__file__).resolve().parent / "ui" / "styles.qss")

    # PyInstaller mode: _MEIPASS points to extracted bundle root.
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "ui" / "styles.qss")
        candidates.append(Path(meipass) / "_internal" / "ui" / "styles.qss")

    # Fallback: next to executable bundle paths.
    exe_parent = Path(sys.executable).resolve().parent
    candidates.append(exe_parent / "ui" / "styles.qss")
    candidates.append(exe_parent / "_internal" / "ui" / "styles.qss")

    for path in candidates:
        try:
            if path.is_file():
                return path
        except Exception:
            continue
    return None


def _resolve_app_icon_path() -> Path | None:
    """
    Resolve app icon PNG cho runtime (window/tray) ở cả dev và frozen mode.
    """
    candidates: list[Path] = []

    # Dev mode.
    candidates.append(Path(__file__).resolve().parent / "ui" / "assets" / "omnimind-app.png")

    # PyInstaller mode.
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        candidates.append(Path(meipass) / "ui" / "assets" / "omnimind-app.png")
        candidates.append(Path(meipass) / "_internal" / "ui" / "assets" / "omnimind-app.png")

    # Fallback: near executable.
    exe_parent = Path(sys.executable).resolve().parent
    candidates.append(exe_parent / "ui" / "assets" / "omnimind-app.png")
    candidates.append(exe_parent / "_internal" / "ui" / "assets" / "omnimind-app.png")

    for path in candidates:
        try:
            if path.is_file():
                return path
        except Exception:
            continue
    return None


def main():
    # Đồng bộ DB path ổn định trước khi import các module có thể khởi tạo DB singleton.
    os.environ["OMNIMIND_DB_PATH"] = str(_get_local_db_path())
    _configure_runtime_logging()
    _bootstrap_update_overlay()

    # Chuẩn hóa CODEX_HOME ngay khi app khởi động để các module dùng cùng 1 path skills/auth.
    from engine.config_manager import ConfigManager
    from engine.vault_manager import VaultManager
    os.environ["CODEX_HOME"] = ConfigManager.get_codex_home()

    # Sprint 2 migration: mã hoá key nhạy cảm local + chuyển dữ liệu vault cũ.
    try:
        ConfigManager.migrate_sensitive_configs()
        VaultManager.migrate_credentials_encryption()
    except Exception as e:
        logger.warning(f"Sensitive data migration warning: {e}")

    # Enable High DPI trước khi tạo QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    argv_with_wait, wait_instance_unlock_sec = _consume_instance_wait_flag(sys.argv)
    qt_argv, start_minimized = _consume_minimized_flag(argv_with_wait)
    app = QApplication(qt_argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    locked, owner_pid = _acquire_app_instance_lock(wait_timeout_sec=wait_instance_unlock_sec)
    if not locked:
        owner_suffix = f" (PID {owner_pid})" if owner_pid else ""
        logger.warning(f"OmniMind đã chạy ở process khác{owner_suffix}; bỏ qua lần mở mới.")
        QMessageBox.information(
            None,
            "OmniMind đang chạy",
            (
                "OmniMind đang chạy ở một phiên khác trên máy này.\n"
                "Hãy mở lại từ icon tray hoặc đóng phiên cũ trước khi mở phiên mới."
            ),
        )
        sys.exit(0)
    app.aboutToQuit.connect(_release_app_instance_lock)

    try:
        icon_path = _resolve_app_icon_path()
        if icon_path:
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception as e:
        logger.warning(f"Could not set app icon: {e}")

    from engine.telegram_bot_service import stop_global_telegram_bot_service
    from engine.zalo_bot_service import get_global_zalo_bot_service, stop_global_zalo_bot_service
    app.aboutToQuit.connect(stop_global_telegram_bot_service)
    app.aboutToQuit.connect(stop_global_zalo_bot_service)

    # Load stylesheet
    try:
        styles_path = _resolve_stylesheet_path()
        if not styles_path:
            raise FileNotFoundError("ui/styles.qss not found in runtime paths")
        with open(styles_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except Exception as e:
        logger.warning(f"Could not load stylesheet: {e}")

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

    try:
        zalo_cfg = ConfigManager.get_zalo_bot_config()
        zalo_conn = ConfigManager.get_zalo_connection_status()
        if zalo_cfg.get("enabled") and zalo_conn.get("login_state") == "connected":
            result = get_global_zalo_bot_service().start()
            if not result.get("success"):
                logger.warning(f"Cannot auto-start Zalo bot: {result.get('message')}")
    except Exception as e:
        logger.warning(f"Zalo bot auto-start warning: {e}")
    _mark_payload_boot_success()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
