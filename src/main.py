"""
OmniMind - Entry Point
Khởi chạy ứng dụng: License Gate → Main Window.
"""
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt


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
    # TODO: Kiểm tra DB xem đã có license_key hợp lệ chưa.
    #       Nếu đã có, bỏ qua popup License.
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
