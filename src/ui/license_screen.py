"""
OmniMind - License Gatekeeper Screen
Hiển thị khi chưa kích hoạt bản quyền. Block toàn bộ tính năng.
Tích hợp License Manager Engine (HWID + API Verify).
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from ui.icons import Icons


class LicenseVerifyWorker(QThread):
    """Worker thread để gọi API verify mà không block UI."""
    finished = pyqtSignal(dict)

    def __init__(self, license_key: str, parent=None):
        super().__init__(parent)
        self.license_key = license_key

    def run(self):
        from engine.license_manager import LicenseManager
        manager = LicenseManager()
        result = manager.verify_license(self.license_key)
        self.finished.emit(result)


class LicenseScreen(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OmniMind - Kích Hoạt Bản Quyền")
        self.setFixedSize(520, 480)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setObjectName("LicenseDialog")
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header gradient ──
        header = QFrame()
        header.setObjectName("LicenseHeader")
        header.setFixedHeight(160)
        header_layout = QVBoxLayout(header)
        header_layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel("🔐")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px; background: transparent;")
        header_layout.addWidget(icon_label)

        title = QLabel("OmniMind")
        title.setObjectName("LicenseTitle")
        title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title)

        subtitle = QLabel("Pro AI Assistant")
        subtitle.setObjectName("LicenseSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(subtitle)

        layout.addWidget(header)

        # ── Form Card ──
        form_card = QFrame()
        form_card.setObjectName("LicenseFormCard")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(48, 36, 48, 36)
        form_layout.setSpacing(16)

        prompt_label = QLabel("Nhập License Key để mở khóa ứng dụng")
        prompt_label.setObjectName("LicensePrompt")
        prompt_label.setAlignment(Qt.AlignCenter)
        prompt_label.setWordWrap(True)
        form_layout.addWidget(prompt_label)

        # Input field
        self.key_input = QLineEdit()
        self.key_input.setObjectName("LicenseInput")
        self.key_input.setPlaceholderText("XXXX-XXXX-XXXX-XXXX")
        self.key_input.setAlignment(Qt.AlignCenter)
        self.key_input.setMinimumHeight(50)
        form_layout.addWidget(self.key_input)

        # Status message
        self.status_label = QLabel("")
        self.status_label.setObjectName("LicenseStatus")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        form_layout.addWidget(self.status_label)

        # Activate button
        self.activate_btn = QPushButton("  Kích Hoạt Bản Quyền")
        self.activate_btn.setObjectName("LicenseActivateBtn")
        self.activate_btn.setIcon(Icons.key("#FFFFFF", 20))
        self.activate_btn.setCursor(Qt.PointingHandCursor)
        self.activate_btn.setMinimumHeight(48)
        self.activate_btn.clicked.connect(self._on_activate)
        form_layout.addWidget(self.activate_btn)

        # Get key link
        get_key_btn = QPushButton("Chưa có Key? Liên hệ ngay →")
        get_key_btn.setObjectName("LicenseGetKeyBtn")
        get_key_btn.setCursor(Qt.PointingHandCursor)
        get_key_btn.setFlat(True)
        form_layout.addWidget(get_key_btn)

        layout.addWidget(form_card)

    def _on_activate(self):
        """Gọi License Manager Engine qua Worker Thread (không block UI)."""
        key = self.key_input.text().strip()
        if not key:
            self.status_label.setStyleSheet("color: #EF4444; font-size: 13px;")
            self.status_label.setText("⚠ Vui lòng nhập License Key.")
            return

        # Vô hiệu hoá nút để tránh spam
        self.activate_btn.setEnabled(False)
        self.activate_btn.setText("  Đang xác thực...")
        self.status_label.setStyleSheet("color: #3B82F6; font-size: 13px;")
        self.status_label.setText("⏳ Đang kết nối tới máy chủ xác thực...")

        # Chạy verify trên thread riêng
        self._worker = LicenseVerifyWorker(key)
        self._worker.finished.connect(self._on_verify_result)
        self._worker.start()

    def _on_verify_result(self, result: dict):
        """Callback từ Worker Thread sau khi có kết quả từ Server."""
        self.activate_btn.setEnabled(True)
        self.activate_btn.setText("  Kích Hoạt Bản Quyền")

        if result.get("success"):
            plan = result.get("plan", "Standard")
            self.status_label.setStyleSheet("color: #10B981; font-size: 13px;")
            self.status_label.setText(f"✅ Kích hoạt thành công! Gói: {plan}")
            # Đợi 1 giây rồi đóng dialog (accept = cho phép vào App)
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(1000, self.accept)
        else:
            message = result.get("message", "Lỗi không xác định.")
            self.status_label.setStyleSheet("color: #EF4444; font-size: 13px;")
            self.status_label.setText(f"❌ {message}")

    def get_license_key(self):
        return self.key_input.text().strip()
