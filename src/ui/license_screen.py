"""
OmniMind - License Gatekeeper Screen
Hiển thị khi chưa kích hoạt bản quyền. Block toàn bộ tính năng.
Tích hợp License Manager Engine (HWID + API Verify).
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QGraphicsDropShadowEffect, QMessageBox, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QDesktopServices
from PyQt5.QtCore import QUrl
import time
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


class LicensePurchaseWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, plan_id: str, target_license_key: str = "", parent=None):
        super().__init__(parent)
        self.plan_id = str(plan_id or "").strip()
        self.target_license_key = str(target_license_key or "").strip()

    def run(self):
        from engine.license_manager import LicenseManager
        manager = LicenseManager()
        result = manager.create_license_purchase_order(self.plan_id, self.target_license_key)
        self.finished.emit(result)


class LicensePaymentPollWorker(QThread):
    status_changed = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(self, order_id: str, order_code: str = "", timeout_sec: int = 600, parent=None):
        super().__init__(parent)
        self.order_id = str(order_id or "").strip()
        self.order_code = str(order_code or "").strip()
        self.timeout_sec = max(30, int(timeout_sec))

    def run(self):
        from engine.license_manager import LicenseManager
        manager = LicenseManager()
        elapsed = 0
        while elapsed <= self.timeout_sec:
            if self.isInterruptionRequested():
                self.finished.emit({"success": False, "message": "Đã dừng theo dõi thanh toán."})
                return
            result = manager.get_payment_order_status(self.order_id, self.order_code)
            if result.get("success"):
                order = result.get("order") if isinstance(result.get("order"), dict) else {}
                status = str(order.get("status", "PENDING") or "PENDING").upper()
                self.status_changed.emit(status)
                if status == "SUCCESS":
                    issued_key = str(order.get("issued_license_key", "") or "").strip()
                    self.finished.emit({
                        "success": True,
                        "order": order,
                        "issued_license_key": issued_key,
                    })
                    return
                if status in {"FAILED", "EXPIRED", "CANCELLED"}:
                    self.finished.emit({"success": False, "order": order, "message": f"Giao dịch {status}."})
                    return
            else:
                self.status_changed.emit("RETRYING")
            time.sleep(3)
            elapsed += 3
        self.finished.emit({"success": False, "message": "Hết thời gian chờ thanh toán."})


class LicenseScreen(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OmniMind - Kích Hoạt Bản Quyền")
        self.setFixedSize(520, 480)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setObjectName("LicenseDialog")
        self._worker = None
        self._purchase_worker = None
        self._payment_poll_worker = None
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
        get_key_btn = QPushButton("Chưa có Key? Mua ngay qua SePay →")
        get_key_btn.setObjectName("LicenseGetKeyBtn")
        get_key_btn.setCursor(Qt.PointingHandCursor)
        get_key_btn.setFlat(True)
        get_key_btn.clicked.connect(self._on_buy_license)
        self.buy_btn = get_key_btn
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

    def _on_buy_license(self):
        from engine.license_manager import LicenseManager
        manager = LicenseManager()
        plans_result = manager.fetch_license_plans()
        if not plans_result.get("success"):
            QMessageBox.warning(self, "Mua license", plans_result.get("message", "Không tải được bảng giá license."))
            return
        plans = plans_result.get("plans", [])
        if not plans:
            QMessageBox.warning(self, "Mua license", "Hiện không có gói license khả dụng.")
            return

        items = []
        plan_by_label = {}
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            pid = str(plan.get("plan_id", "")).strip()
            if not pid:
                continue
            label = f"{plan.get('display_name', pid)} | {plan.get('duration_days', 0)} ngày | {plan.get('price', 0)} VND"
            items.append(label)
            plan_by_label[label] = plan

        if not items:
            QMessageBox.warning(self, "Mua license", "Bảng giá plan chưa hợp lệ.")
            return

        selected, ok = QInputDialog.getItem(self, "Chọn gói license", "Gói khả dụng:", items, 0, False)
        if not ok or not selected:
            return

        plan = plan_by_label.get(selected, {})
        plan_id = str(plan.get("plan_id", "")).strip()
        if not plan_id:
            return

        self.buy_btn.setEnabled(False)
        self.activate_btn.setEnabled(False)
        self.status_label.setStyleSheet("color: #3B82F6; font-size: 13px;")
        self.status_label.setText("⏳ Đang tạo đơn thanh toán...")

        self._purchase_worker = LicensePurchaseWorker(plan_id=plan_id, target_license_key="")
        self._purchase_worker.finished.connect(self._on_purchase_created)
        self._purchase_worker.start()

    def _on_purchase_created(self, result: dict):
        self._purchase_worker = None
        self.buy_btn.setEnabled(True)
        self.activate_btn.setEnabled(True)

        if result.get("success") and str(result.get("issued_license_key", "")).strip():
            issued = str(result.get("issued_license_key", "")).strip()
            self.key_input.setText(issued)
            self.status_label.setStyleSheet("color: #10B981; font-size: 13px;")
            self.status_label.setText("✅ Đã cấp license miễn phí. Đang kích hoạt...")
            self._on_activate()
            return

        code = str(result.get("code", "")).upper()
        if code not in {"PAYMENT_REQUIRED", "PAYMENT_PENDING"}:
            self.status_label.setStyleSheet("color: #EF4444; font-size: 13px;")
            self.status_label.setText(f"❌ {result.get('message', 'Không thể tạo đơn thanh toán.')}")
            return

        payment = result.get("payment") if isinstance(result.get("payment"), dict) else {}
        order_id = str(payment.get("id", "")).strip()
        order_code = str(payment.get("payment_content", "")).strip()
        qr_url = str(payment.get("qr_url", "")).strip()
        amount = payment.get("amount", "")
        message_text = result.get("message", "Vui lòng thanh toán để tiếp tục.")

        if qr_url:
            ask = QMessageBox.question(
                self,
                "Thanh toán license",
                f"{message_text}\n\nSố tiền: {amount} VND\nNội dung: {order_code}\n\nMở QR để thanh toán?",
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Ok,
            )
            if ask == QMessageBox.Ok:
                QDesktopServices.openUrl(QUrl(qr_url))
        else:
            QMessageBox.information(
                self,
                "Thanh toán license",
                f"{message_text}\n\nSố tiền: {amount} VND\nNội dung: {order_code}",
            )

        if not order_id:
            self.status_label.setStyleSheet("color: #EF4444; font-size: 13px;")
            self.status_label.setText("❌ Không lấy được mã order để theo dõi thanh toán.")
            return

        self.status_label.setStyleSheet("color: #3B82F6; font-size: 13px;")
        self.status_label.setText("⏳ Đang chờ xác nhận thanh toán...")
        self._payment_poll_worker = LicensePaymentPollWorker(order_id=order_id, order_code=order_code)
        self._payment_poll_worker.status_changed.connect(self._on_payment_status_changed)
        self._payment_poll_worker.finished.connect(self._on_payment_poll_finished)
        self._payment_poll_worker.start()

    def _on_payment_status_changed(self, status: str):
        mapping = {
            "PENDING": "⏳ Chờ thanh toán...",
            "PROCESSING": "⏳ Giao dịch đang xử lý...",
            "RETRYING": "⏳ Đang kiểm tra lại trạng thái...",
            "SUCCESS": "✅ Thanh toán thành công, đang cấp key...",
        }
        self.status_label.setStyleSheet("color: #3B82F6; font-size: 13px;")
        self.status_label.setText(mapping.get(str(status).upper(), f"⏳ Trạng thái: {status}"))

    def _on_payment_poll_finished(self, result: dict):
        self._payment_poll_worker = None
        if not result.get("success"):
            self.status_label.setStyleSheet("color: #EF4444; font-size: 13px;")
            self.status_label.setText(f"❌ {result.get('message', 'Thanh toán chưa hoàn tất.')}")
            return

        issued = str(result.get("issued_license_key", "")).strip()
        if not issued:
            self.status_label.setStyleSheet("color: #EF4444; font-size: 13px;")
            self.status_label.setText("❌ Thanh toán thành công nhưng chưa nhận được license key.")
            return

        self.key_input.setText(issued)
        self.status_label.setStyleSheet("color: #10B981; font-size: 13px;")
        self.status_label.setText("✅ Đã nhận license key mới. Đang kích hoạt...")
        self._on_activate()

    def get_license_key(self):
        return self.key_input.text().strip()

    def closeEvent(self, event):
        if self._payment_poll_worker and self._payment_poll_worker.isRunning():
            self._payment_poll_worker.requestInterruption()
            self._payment_poll_worker.wait(1200)
        super().closeEvent(event)
