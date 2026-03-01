"""
OmniMind - Entry Point
Khởi chạy ứng dụng: License Gate → Main Window.
Tích hợp License Manager: Tự động skip Gate nếu đã kích hoạt trước đó.
"""
import sys
import os
import logging
import sqlite3
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
logger = logging.getLogger(__name__)


def _get_local_db_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
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

        if not payload_path:
            if not current_version:
                _set_config_value_raw("app_current_version", default_version)
            return

        src_dir = Path(payload_path).expanduser() / "src"
        if not src_dir.is_dir():
            # Payload không còn tồn tại -> tự chữa để app chạy fallback bản gốc.
            _set_config_value_raw("app_payload_path", "")
            _set_config_value_raw("app_payload_version", "")
            _set_config_value_raw("app_update_pending_restart", "false")
            if not current_version:
                _set_config_value_raw("app_current_version", default_version)
            return

        src_path = str(src_dir)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)

        if payload_version:
            os.environ["OMNIMIND_APP_VERSION"] = payload_version
            _set_config_value_raw("app_current_version", payload_version)
        _set_config_value_raw("app_update_pending_restart", "false")
    except Exception as e:
        logger.warning(f"Update overlay bootstrap warning: {e}")


def main():
    _bootstrap_update_overlay()

    # Chuẩn hóa CODEX_HOME ngay khi app khởi động để các module dùng cùng 1 path skills/auth.
    from engine.config_manager import ConfigManager
    os.environ["CODEX_HOME"] = ConfigManager.get_codex_home()

    # Enable High DPI trước khi tạo QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

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

    # ── Main Application ──
    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
