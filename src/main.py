"""
OmniMind - Entry Point
Khởi chạy ứng dụng: License Gate → Main Window.
Tích hợp License Manager: Tự động skip Gate nếu đã kích hoạt trước đó.
"""
import sys
import os
import logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")


def main():
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
