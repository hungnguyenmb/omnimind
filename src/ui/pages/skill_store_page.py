"""
OmniMind - Tab 5: Skill Marketplace
Kết nối API thật để xem marketplace, cài đặt và gỡ skills cho OmniMind.
"""
from datetime import datetime
import unicodedata

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QTabWidget, QLineEdit,
    QScrollArea, QDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap

from ui.icons import Icons
from engine.http_client import request_with_retry
from engine.skill_manager import SkillManager


class SkillLoadWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, manager: SkillManager, page: int = 1, per_page: int = 50, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.page = max(1, int(page or 1))
        self.per_page = max(1, int(per_page or 50))

    def run(self):
        result = self.manager.fetch_marketplace_skills(page=self.page, per_page=self.per_page)
        if result.get("success"):
            skills = result.get("skills", [])
            raw = result.get("raw") if isinstance(result.get("raw"), dict) else {}
            total = int(raw.get("total", len(skills)) or len(skills))
            page = int(raw.get("page", self.page) or self.page)
            per_page = int(raw.get("per_page", self.per_page) or self.per_page)
            message = ""
            success = True
        else:
            if self.page == 1:
                skills = self.manager.get_cached_marketplace_skills()
                total = len(skills)
                page = 1
                per_page = self.per_page
                message = result.get("message", "Không kết nối được server, đang dùng dữ liệu cache.")
                success = bool(skills)
            else:
                skills = []
                total = 0
                page = self.page
                per_page = self.per_page
                message = result.get("message", "Không tải thêm được skills.")
                success = False

        installed = self.manager.get_installed_skills()
        installed_ids = {row.get("skill_id") for row in installed}
        self.finished.emit({
            "success": success,
            "skills": skills,
            "installed_ids": installed_ids,
            "message": message,
            "page": page,
            "per_page": per_page,
            "total": total,
        })


class SkillActionWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, manager: SkillManager, skill_id: str, action: str, requires_purchase=False, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.skill_id = skill_id
        self.action = action
        self.requires_purchase = requires_purchase

    def run(self):
        try:
            if self.action == "install":
                if self.requires_purchase:
                    purchase_result = self.manager.purchase_skill(self.skill_id)
                    if not purchase_result.get("success"):
                        self.finished.emit(purchase_result)
                        return
                self.finished.emit(self.manager.install_skill(self.skill_id))
                return

            if self.action == "uninstall":
                self.finished.emit(self.manager.uninstall_skill(self.skill_id))
                return

            self.finished.emit({"success": False, "message": "Action không hợp lệ."})
        except Exception as e:
            self.finished.emit({"success": False, "message": str(e)})


class PaymentStatusWorker(QThread):
    status_changed = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(
        self,
        manager: SkillManager,
        order_id: str,
        timeout_ms: int = 10 * 60 * 1000,
        poll_interval_ms: int = 3000,
        parent=None,
    ):
        super().__init__(parent)
        self.manager = manager
        self.order_id = str(order_id or "").strip()
        self.timeout_ms = max(30_000, int(timeout_ms))
        self.poll_interval_ms = max(1000, int(poll_interval_ms))

    def run(self):
        elapsed_ms = 0
        last_error = ""
        while elapsed_ms <= self.timeout_ms:
            if self.isInterruptionRequested():
                self.finished.emit(
                    {"success": False, "paid": False, "message": "Đã dừng theo dõi thanh toán."}
                )
                return

            result = self.manager.get_payment_order_status(self.order_id)
            if result.get("success"):
                order = result.get("order") if isinstance(result.get("order"), dict) else {}
                status = str(order.get("status", "PENDING") or "PENDING").upper()
                self.status_changed.emit(status)
                if status == "SUCCESS":
                    self.finished.emit({"success": True, "paid": True, "order": order, "status": status})
                    return
                if status in {"FAILED", "EXPIRED", "CANCELLED"}:
                    self.finished.emit(
                        {
                            "success": False,
                            "paid": False,
                            "order": order,
                            "status": status,
                            "message": f"Thanh toán kết thúc với trạng thái {status}.",
                        }
                    )
                    return
                last_error = ""
            else:
                last_error = str(result.get("message", "") or "Không kiểm tra được trạng thái thanh toán.")
                self.status_changed.emit("RETRYING")

            self.msleep(self.poll_interval_ms)
            elapsed_ms += self.poll_interval_ms

        self.finished.emit(
            {
                "success": False,
                "paid": False,
                "status": "TIMEOUT",
                "message": last_error or "Hết thời gian chờ thanh toán.",
            }
        )


class SkillPaymentQrDialog(QDialog):
    def __init__(self, skill_name: str, amount_text: str, qr_url: str, expires_at: str = "", parent=None):
        super().__init__(parent)
        self._qr_url = str(qr_url or "").strip()
        self._expiry_dt = self._parse_expiry(expires_at)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick_countdown)
        self.setWindowTitle("Thanh toán skill")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Quét mã QR để thanh toán")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        skill_lbl = QLabel(f"Skill: {skill_name}")
        skill_lbl.setStyleSheet("font-size: 14px; color: #334155;")
        layout.addWidget(skill_lbl)

        amount_lbl = QLabel(f"Số tiền: {amount_text}")
        amount_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        layout.addWidget(amount_lbl)

        note_lbl = QLabel("Sau khi thanh toán thành công, cửa sổ sẽ tự đóng và skill sẽ tự cài đặt.")
        note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(note_lbl)

        self.countdown_label = QLabel("")
        self.countdown_label.setAlignment(Qt.AlignCenter)
        self.countdown_label.setStyleSheet("font-size: 12px; color: #0F172A; font-weight: 700;")
        layout.addWidget(self.countdown_label)

        self.qr_label = QLabel("Đang tải mã QR...")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setFixedSize(300, 300)
        self.qr_label.setStyleSheet("border: 1px solid #E2E8F0; border-radius: 10px; background: #FFFFFF;")
        layout.addWidget(self.qr_label, alignment=Qt.AlignHCenter)

        self.status_label = QLabel("Đang chờ thanh toán...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._load_qr()
        self._tick_countdown()
        if self._expiry_dt:
            self._timer.start()

    @staticmethod
    def _parse_expiry(value: str):
        text = str(value or "").strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            return None

    def _tick_countdown(self):
        if not self._expiry_dt:
            self.countdown_label.setText("")
            return
        now = datetime.now(self._expiry_dt.tzinfo) if self._expiry_dt.tzinfo else datetime.now()
        remain = int((self._expiry_dt - now).total_seconds())
        if remain <= 0:
            self.countdown_label.setText("Thời gian thanh toán: đã hết hạn")
            self.countdown_label.setStyleSheet("font-size: 12px; color: #EF4444; font-weight: 700;")
            self._timer.stop()
            return
        minutes, seconds = divmod(remain, 60)
        self.countdown_label.setText(f"Thời gian thanh toán còn lại: {minutes:02d}:{seconds:02d}")
        self.countdown_label.setStyleSheet("font-size: 12px; color: #0F172A; font-weight: 700;")

    def _load_qr(self):
        if not self._qr_url:
            self.qr_label.setText("Không có mã QR.")
            return
        try:
            resp = request_with_retry("GET", self._qr_url, timeout=20, max_attempts=3)
            if resp.status_code != 200 or not resp.content:
                self.qr_label.setText("Không tải được mã QR.")
                return
            pix = QPixmap()
            if not pix.loadFromData(resp.content):
                self.qr_label.setText("Không tải được mã QR.")
                return
            scaled = pix.scaled(280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.qr_label.setPixmap(scaled)
            self.qr_label.setText("")
        except Exception:
            self.qr_label.setText("Không tải được mã QR.")

    def set_runtime_status(self, text: str):
        self.status_label.setText(str(text or "").strip() or "Đang chờ thanh toán...")
        self.status_label.setStyleSheet("font-size: 12px; color: #64748B;")

    def mark_paid(self):
        self.status_label.setText("Đã nhận thanh toán. Đang cài đặt skill...")
        self.status_label.setStyleSheet("font-size: 12px; color: #10B981; font-weight: 700;")
        self._timer.stop()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


class SkillDetailDialog(QDialog):
    INSTALL_RESULT = 1
    UNINSTALL_RESULT = 2

    def __init__(self, parent=None, skill=None, installed=False):
        super().__init__(parent)
        self.skill = skill or {}
        self.installed = installed
        self.setWindowTitle(self.skill.get("name", "Skill"))
        self.setMinimumSize(540, 420)
        self.resize(560, 460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        icon_lbl = QLabel(self.skill.get("icon", "🧩"))
        icon_lbl.setStyleSheet("font-size: 42px; background: transparent;")
        header_row.addWidget(icon_lbl)

        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_lbl = QLabel(self.skill.get("name", ""))
        name_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #0F172A;")
        name_col.addWidget(name_lbl)

        meta_lbl = QLabel(f"v{self.skill.get('version', '1.0')}  ·  {self.skill.get('author', '')}")
        meta_lbl.setStyleSheet("font-size: 13px; color: #94A3B8;")
        name_col.addWidget(meta_lbl)
        header_row.addLayout(name_col)

        header_row.addStretch()
        badge = self.skill.get("badge", "")
        color = self.skill.get("color", "#64748B")
        badge_lbl = QLabel(badge)
        badge_lbl.setStyleSheet(
            f"background-color: {color}; color: white; font-size: 12px; font-weight: 700; "
            f"padding: 4px 14px; border-radius: 12px;"
        )
        header_row.addWidget(badge_lbl, alignment=Qt.AlignTop)
        layout.addLayout(header_row)

        short_lbl = QLabel(self.skill.get("short", self.skill.get("description", "")))
        short_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #334155;")
        short_lbl.setWordWrap(True)
        layout.addWidget(short_lbl)

        detail_lbl = QLabel(self.skill.get("detail", self.skill.get("description", "")))
        detail_lbl.setStyleSheet("font-size: 14px; color: #64748B; line-height: 1.6;")
        detail_lbl.setWordWrap(True)
        layout.addWidget(detail_lbl)

        pricing = self.skill.get("pricing") if isinstance(self.skill.get("pricing"), dict) else {}
        price = float(self.skill.get("effective_price", self.skill.get("price", 0)) or 0)
        owned = bool(self.skill.get("is_owned", False))
        status_text = "Miễn phí" if price <= 0 else f"Giá: {price:.2f} VND"
        discount_amount = float(pricing.get("discount_amount", 0) or 0)
        if discount_amount > 0:
            status_text += f" · Giảm: {discount_amount:.2f} VND"
        if owned:
            status_text += " · Đã có quyền"
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet("font-size: 12px; color: #64748B;")
        layout.addWidget(status_lbl)
        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("SecondaryBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(44)
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        if self.installed:
            uninstall_btn = QPushButton("  Gỡ Cài Đặt")
            uninstall_btn.setObjectName("SecondaryBtn")
            uninstall_btn.setIcon(Icons.trash("#EF4444", 16))
            uninstall_btn.setCursor(Qt.PointingHandCursor)
            uninstall_btn.setFixedHeight(44)
            uninstall_btn.setMinimumWidth(170)
            uninstall_btn.clicked.connect(lambda: self.done(self.UNINSTALL_RESULT))
            btn_row.addWidget(uninstall_btn)
        else:
            install_btn = QPushButton("  Tải Về & Cài Đặt")
            install_btn.setObjectName("PrimaryBtn")
            install_btn.setIcon(Icons.download("#FFFFFF", 16))
            install_btn.setCursor(Qt.PointingHandCursor)
            install_btn.setFixedHeight(44)
            install_btn.setMinimumWidth(190)
            install_btn.clicked.connect(lambda: self.done(self.INSTALL_RESULT))
            btn_row.addWidget(install_btn)

        layout.addLayout(btn_row)


class SkillStorePage(QWidget):
    DEFAULT_PER_PAGE = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = SkillManager()
        self.skills = []
        self.installed_ids = set()
        self._load_worker = None
        self._action_worker = None
        self._payment_worker = None
        self._payment_dialog = None
        self._payment_cancelled_by_user = False
        self._pending_action = None
        self._pending_payment = None
        self._search_query = ""
        self._last_sync_message = ""
        self._current_page = 0
        self._total_skills = 0
        self._per_page = self.DEFAULT_PER_PAGE
        self._has_more = False
        self._pending_append = False
        self._setup_ui()
        self._reload_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QWidget()
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)
        title = QLabel("Skill Marketplace")
        title.setObjectName("PageTitle")
        desc = QLabel(
            "Tải về các kỹ năng AI chuyên biệt từ server và cài vào OmniMind local. "
            "Sau khi cài, skill sẽ khả dụng cho các phiên làm việc mới."
        )
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(desc)
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        self.status_label = QLabel("Đang đồng bộ danh sách skills...")
        self.status_label.setStyleSheet("font-size: 12px; color: #64748B;")
        toolbar.addWidget(self.status_label)
        toolbar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔎 Tìm skill theo tên, mô tả, tác giả...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(38)
        self.search_input.setMinimumWidth(340)
        self.search_input.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_input)

        self.refresh_btn = QPushButton("  Làm mới")
        self.refresh_btn.setObjectName("SecondaryBtn")
        self.refresh_btn.setIcon(Icons.refresh("#3B82F6", 16))
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setMinimumHeight(38)
        self.refresh_btn.clicked.connect(self._reload_data)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("SkillTabs")
        layout.addWidget(self.tabs, 1)

        pager_row = QHBoxLayout()
        pager_row.addStretch()
        self.load_more_btn = QPushButton("  Tải thêm")
        self.load_more_btn.setObjectName("SecondaryBtn")
        self.load_more_btn.setIcon(Icons.download("#3B82F6", 16))
        self.load_more_btn.setCursor(Qt.PointingHandCursor)
        self.load_more_btn.setMinimumHeight(36)
        self.load_more_btn.clicked.connect(self._load_more)
        self.load_more_btn.setVisible(False)
        pager_row.addWidget(self.load_more_btn)
        pager_row.addStretch()
        layout.addLayout(pager_row)

    def _set_busy(self, busy: bool, text: str = ""):
        self.refresh_btn.setEnabled(not busy)
        self.search_input.setEnabled(not busy)
        if busy:
            self.load_more_btn.setEnabled(False)
        else:
            self.load_more_btn.setEnabled(self._has_more)
        if text:
            self.status_label.setText(text)

    @staticmethod
    def _normalize_text(value: str) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        normalized = unicodedata.normalize("NFD", raw)
        no_accent = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return " ".join(no_accent.split())

    def _skill_matches_query(self, skill: dict, query_norm: str) -> bool:
        if not query_norm:
            return True
        fields = [
            skill.get("name", ""),
            skill.get("short", ""),
            skill.get("description", ""),
            skill.get("author", ""),
            skill.get("id", ""),
        ]
        for field in fields:
            if query_norm in self._normalize_text(str(field or "")):
                return True
        return False

    def _filtered_skills(self, installed_only: bool = False) -> list[dict]:
        query_norm = self._normalize_text(self._search_query)
        source = self.skills
        if installed_only:
            source = [s for s in self.skills if s.get("id") in self.installed_ids]
        return [s for s in source if self._skill_matches_query(s, query_norm)]

    def _update_status_summary(self):
        if self._search_query.strip():
            total = len(self.skills)
            filtered = len(self._filtered_skills(installed_only=False))
            installed_total = len([s for s in self.skills if s.get("id") in self.installed_ids])
            installed_filtered = len(self._filtered_skills(installed_only=True))
            self.status_label.setText(
                f"Kết quả: {filtered}/{total} skills · Đã cài: {installed_filtered}/{installed_total}"
            )
            return
        if self._last_sync_message:
            self.status_label.setText(self._last_sync_message)
            return
        if self._total_skills > 0:
            self.status_label.setText(
                f"Sẵn sàng · đã tải {len(self.skills)}/{self._total_skills} skills"
                f" (trang {max(1, self._current_page)})"
            )
        else:
            self.status_label.setText(f"Sẵn sàng · {len(self.skills)} skills")

    def _on_search_changed(self, text: str):
        self._search_query = str(text or "")
        self.load_more_btn.setVisible(self._has_more and not bool(self._search_query.strip()))
        self.load_more_btn.setEnabled(self._has_more and not bool(self._search_query.strip()))
        if self._load_worker and self._load_worker.isRunning():
            return
        self._rebuild_tabs()
        self._update_status_summary()

    def _reload_data(self):
        if self._load_worker and self._load_worker.isRunning():
            return
        self._pending_append = False
        self._set_busy(True, "Đang tải marketplace...")
        self._load_worker = SkillLoadWorker(self.manager, page=1, per_page=self._per_page, parent=self)
        self._load_worker.finished.connect(self._on_loaded)
        self._load_worker.start()

    def _load_more(self):
        if not self._has_more:
            return
        if self._load_worker and self._load_worker.isRunning():
            return
        next_page = self._current_page + 1 if self._current_page > 0 else 2
        self._pending_append = True
        self._set_busy(True, f"Đang tải thêm skills (trang {next_page})...")
        self._load_worker = SkillLoadWorker(self.manager, page=next_page, per_page=self._per_page, parent=self)
        self._load_worker.finished.connect(self._on_loaded)
        self._load_worker.start()

    def _on_loaded(self, payload: dict):
        self._set_busy(False)
        self._load_worker = None
        incoming = payload.get("skills", [])
        if self._pending_append:
            existing_ids = {str(s.get("id", "")).strip() for s in self.skills}
            appended = [s for s in incoming if str(s.get("id", "")).strip() not in existing_ids]
            self.skills.extend(appended)
        else:
            self.skills = incoming

        self.installed_ids = set(payload.get("installed_ids", set()))
        self._current_page = int(payload.get("page", self._current_page or 1) or 1)
        self._per_page = int(payload.get("per_page", self._per_page or self.DEFAULT_PER_PAGE) or self.DEFAULT_PER_PAGE)
        self._total_skills = int(payload.get("total", len(self.skills)) or len(self.skills))
        self._has_more = len(self.skills) < self._total_skills
        self.load_more_btn.setVisible(self._has_more and not bool(self._search_query.strip()))
        self.load_more_btn.setEnabled(self._has_more)

        msg = payload.get("message", "")
        self._last_sync_message = msg
        self._pending_append = False

        self._rebuild_tabs()
        self._update_status_summary()

    def _rebuild_tabs(self):
        while self.tabs.count():
            self.tabs.removeTab(0)
        self.tabs.addTab(self._build_store_tab(), "🏪  Kho Kỹ Năng")
        self.tabs.addTab(self._build_installed_tab(), "📦  Đã Cài Đặt")

    def _build_store_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("ScrollArea")

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(16)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        filtered_skills = self._filtered_skills(installed_only=False)
        for i, skill in enumerate(filtered_skills):
            installed = skill.get("id") in self.installed_ids
            card = self._create_skill_card(skill, installed=installed)
            grid.addWidget(card, i // 3, i % 3, Qt.AlignTop)

        if not filtered_skills:
            empty = QLabel("Không tìm thấy skill phù hợp.")
            empty.setStyleSheet("font-size: 14px; color: #94A3B8; padding: 8px;")
            empty.setAlignment(Qt.AlignCenter)
            grid.addWidget(empty, 0, 0, 1, 3, Qt.AlignCenter)

        scroll.setWidget(container)
        return scroll

    def _build_installed_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("ScrollArea")

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(16)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        installed_skills = self._filtered_skills(installed_only=True)
        for i, skill in enumerate(installed_skills):
            card = self._create_skill_card(skill, installed=True)
            grid.addWidget(card, i // 3, i % 3, Qt.AlignTop)

        if not installed_skills:
            empty = QLabel("Chưa có skill đã cài khớp điều kiện tìm kiếm.")
            empty.setStyleSheet("font-size: 14px; color: #94A3B8; padding: 8px;")
            empty.setAlignment(Qt.AlignCenter)
            grid.addWidget(empty, 0, 0, 1, 3, Qt.AlignCenter)

        scroll.setWidget(container)
        return scroll

    def _create_skill_card(self, skill, installed=False):
        card = QFrame()
        card.setObjectName("SkillCard")
        card.setFixedHeight(236)
        card.setCursor(Qt.PointingHandCursor)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 10))
        shadow.setOffset(0, 3)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        top_row = QHBoxLayout()
        icon_lbl = QLabel(skill.get("icon", "🧩"))
        icon_lbl.setStyleSheet("font-size: 36px; background: transparent;")
        top_row.addWidget(icon_lbl)
        top_row.addStretch()
        badge_lbl = QLabel(skill.get("badge", "SKILL"))
        badge_lbl.setStyleSheet(
            f"background-color: {skill.get('color', '#64748B')}; color: white; font-size: 11px; "
            "font-weight: 700; padding: 3px 10px; border-radius: 10px;"
        )
        top_row.addWidget(badge_lbl, alignment=Qt.AlignTop)
        card_layout.addLayout(top_row)

        name_lbl = QLabel(skill.get("name", ""))
        name_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        card_layout.addWidget(name_lbl)

        desc_lbl = QLabel(skill.get("short", skill.get("description", "")))
        desc_lbl.setStyleSheet("font-size: 13px; color: #64748B; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl)
        card_layout.addStretch()

        if installed:
            btn = QPushButton("  Đã cài đặt")
            btn.setIcon(Icons.check_circle("#10B981", 16))
            btn.setObjectName("InstalledBtn")
        else:
            btn = QPushButton("  Xem chi tiết")
            btn.setIcon(Icons.download("#FFFFFF", 16))
            btn.setObjectName("PrimaryBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(38)
        btn.clicked.connect(lambda checked, s=skill, inst=installed: self._show_detail(s, inst))
        card_layout.addWidget(btn)

        card.mousePressEvent = lambda event, s=skill, inst=installed: self._show_detail(s, inst)
        return card

    def _show_detail(self, skill, installed):
        dialog = SkillDetailDialog(self, skill=skill, installed=installed)
        result = dialog.exec_()

        if result == SkillDetailDialog.INSTALL_RESULT and not installed:
            self._run_action("install", skill)
        elif result == SkillDetailDialog.UNINSTALL_RESULT and installed:
            self._run_action("uninstall", skill)

    def _run_action(self, action: str, skill: dict, force_skip_purchase: bool = False):
        if self._action_worker and self._action_worker.isRunning():
            return
        if self._payment_worker and self._payment_worker.isRunning():
            QMessageBox.information(self, "Skill Marketplace", "Đang chờ thanh toán. Vui lòng đợi hoàn tất.")
            return

        skill_id = skill.get("id", "")
        requires_purchase = bool(skill.get("requires_purchase", False)) and not force_skip_purchase
        verb = "cài đặt" if action == "install" else "gỡ cài đặt"
        self._set_busy(True, f"Đang {verb} skill '{skill_id}'...")
        self._pending_action = {"action": action, "skill_id": skill_id}

        self._action_worker = SkillActionWorker(
            self.manager, skill_id, action=action, requires_purchase=requires_purchase, parent=self
        )
        self._action_worker.finished.connect(self._on_action_finished)
        self._action_worker.start()

    def _find_skill_by_id(self, skill_id: str):
        sid = str(skill_id or "").strip()
        if not sid:
            return None
        for skill in self.skills:
            if str(skill.get("id", "")).strip() == sid:
                return skill
        return None

    def _start_payment_poll(self, skill_id: str, order_id: str):
        if self._payment_worker and self._payment_worker.isRunning():
            return
        self._payment_cancelled_by_user = False
        self._pending_payment = {"skill_id": skill_id, "order_id": order_id}
        self._set_busy(True, f"Đang chờ thanh toán cho skill '{skill_id}'...")
        self._payment_worker = PaymentStatusWorker(self.manager, order_id=order_id, parent=self)
        self._payment_worker.status_changed.connect(self._on_payment_status_changed)
        self._payment_worker.finished.connect(self._on_payment_finished)
        self._payment_worker.start()

    def _format_money(self, amount, currency: str = "VND") -> str:
        try:
            num = float(amount)
            if abs(num - int(num)) < 1e-9:
                return f"{int(num):,} {currency}".replace(",", ".")
            return f"{num:,.2f} {currency}".replace(",", ".")
        except Exception:
            raw = str(amount or "").strip() or "0"
            return f"{raw} {currency}".strip()

    def _close_payment_dialog(self, accepted: bool):
        if not self._payment_dialog:
            return
        dlg = self._payment_dialog
        self._payment_dialog = None
        if accepted:
            dlg.accept()
        else:
            dlg.reject()

    def _on_payment_status_changed(self, status: str):
        status_map = {
            "PENDING": "Chờ thanh toán...",
            "PROCESSING": "Đang xử lý giao dịch...",
            "SUCCESS": "Đã nhận thanh toán.",
            "RETRYING": "Đang thử kiểm tra lại thanh toán...",
        }
        msg = status_map.get(str(status or "").upper(), f"Trạng thái thanh toán: {status}")
        self.status_label.setText(msg)
        if self._payment_dialog:
            self._payment_dialog.set_runtime_status(msg)

    def _on_payment_finished(self, payload: dict):
        self._set_busy(False)
        self._payment_worker = None

        payment_ctx = self._pending_payment or {}
        self._pending_payment = None
        skill_id = payment_ctx.get("skill_id", "")

        if payload.get("success") and payload.get("paid"):
            if self._payment_dialog:
                self._payment_dialog.mark_paid()
            self._close_payment_dialog(accepted=True)
            self.status_label.setText("Thanh toán thành công. Đang cài đặt skill...")
            skill = self._find_skill_by_id(skill_id) or {"id": skill_id, "requires_purchase": False}
            self._run_action("install", skill, force_skip_purchase=True)
            return

        self._close_payment_dialog(accepted=False)

        message = payload.get("message", "Thanh toán chưa hoàn tất.")
        status = str(payload.get("status", "") or "").upper()
        if self._payment_cancelled_by_user:
            self._payment_cancelled_by_user = False
            self.status_label.setText("Đã hủy chờ thanh toán.")
            return
        if status == "TIMEOUT":
            QMessageBox.information(
                self,
                "Thanh toán skill",
                message + "\n\nBạn có thể thanh toán sau và bấm cài lại để kiểm tra quyền.",
            )
        else:
            QMessageBox.warning(self, "Thanh toán skill", message)
        self.status_label.setText("Thanh toán chưa hoàn tất.")

    def _on_action_finished(self, result: dict):
        self._set_busy(False)
        self._action_worker = None
        action_ctx = self._pending_action or {}
        self._pending_action = None
        if result.get("success"):
            QMessageBox.information(self, "Skill Marketplace", result.get("message", "Thành công."))

            if action_ctx.get("action") == "install":
                preflight = result.get("permission_preflight", {}) or {}
                if not preflight.get("success"):
                    missing = preflight.get("missing_permissions", []) or []
                    missing_names = ", ".join(
                        sorted({m.get("permission", "") for m in missing if m.get("permission")})
                    )
                    ask = QMessageBox.question(
                        self,
                        "Cấp quyền cho skill",
                        (
                            "Skill đã cài đặt nhưng chưa đủ quyền để chạy một số action.\n\n"
                            f"Quyền còn thiếu: {missing_names or 'Không xác định'}\n\n"
                            "Bạn có muốn mở màn hình cấp quyền ngay bây giờ không?"
                        ),
                        QMessageBox.Ok | QMessageBox.Cancel,
                        QMessageBox.Ok,
                    )
                    if ask == QMessageBox.Ok:
                        retry = self.manager.retry_skill_action_with_permission_request(
                            skill_id=result.get("skill_id", action_ctx.get("skill_id", "")),
                            action_id="runtime_bootstrap",
                            payload={},
                            required_capabilities=result.get("required_capabilities", []),
                            runner=None,
                        )
                        if retry.get("success"):
                            QMessageBox.information(
                                self,
                                "Cấp quyền",
                                "Đã preflight lại thành công. Skill sẵn sàng cho runtime action.",
                            )
                        else:
                            retry_preflight = retry.get("preflight", {}) or {}
                            retry_missing = retry_preflight.get("missing_permissions", []) or []
                            retry_names = ", ".join(
                                sorted({m.get("permission", "") for m in retry_missing if m.get("permission")})
                            )
                            QMessageBox.warning(
                                self,
                                "Cấp quyền chưa hoàn tất",
                                (
                                    "Một số quyền vẫn chưa được cấp sau khi mở Settings.\n"
                                    f"Còn thiếu: {retry_names or 'Không xác định'}"
                                ),
                            )
            self._reload_data()
        else:
            if result.get("code") in {"PAYMENT_REQUIRED", "PAYMENT_PENDING"}:
                payment = result.get("payment") if isinstance(result.get("payment"), dict) else {}
                payment_id = str(payment.get("id", "") or "").strip()
                qr_url = str(payment.get("qr_url", "") or "").strip()
                amount = payment.get("amount")
                currency = str(payment.get("currency", "VND") or "VND").strip()
                expires_at = str(payment.get("expires_at", "") or "").strip()
                skill_id = action_ctx.get("skill_id", "")
                skill = self._find_skill_by_id(skill_id) or {}
                skill_name = str(skill.get("name") or skill_id or "Skill")
                amount_text = self._format_money(amount, currency)

                if not payment_id or not skill_id or not qr_url:
                    self.status_label.setText("Không lấy được mã thanh toán, vui lòng thử lại.")
                    QMessageBox.warning(
                        self,
                        "Thanh toán skill",
                        "Không lấy được thông tin mã QR thanh toán. Vui lòng thử lại.",
                    )
                    return

                ask = QMessageBox.question(
                    self,
                    "Thanh toán skill",
                    (
                        f"Skill: {skill_name}\n"
                        f"Số tiền: {amount_text}\n\n"
                        "Nhấn OK để hiển thị mã QR thanh toán trong ứng dụng."
                    ),
                    QMessageBox.Ok | QMessageBox.Cancel,
                    QMessageBox.Ok,
                )
                if ask != QMessageBox.Ok:
                    self.status_label.setText("Đã hủy thanh toán.")
                    return

                self._payment_dialog = SkillPaymentQrDialog(
                    skill_name=skill_name,
                    amount_text=amount_text,
                    qr_url=qr_url,
                    expires_at=expires_at,
                    parent=self,
                )
                self._start_payment_poll(skill_id=skill_id, order_id=payment_id)
                dialog_result = self._payment_dialog.exec_()
                if dialog_result != QDialog.Accepted and self._payment_worker and self._payment_worker.isRunning():
                    self._payment_cancelled_by_user = True
                    self._payment_worker.requestInterruption()
                    self.status_label.setText("Đã hủy chờ thanh toán.")
                return

            QMessageBox.warning(self, "Skill Marketplace", result.get("message", "Thao tác thất bại."))
            self.status_label.setText("Có lỗi xảy ra, vui lòng thử lại.")

    def closeEvent(self, event):
        if self._payment_worker and self._payment_worker.isRunning():
            self._payment_worker.requestInterruption()
            self._payment_worker.wait(1200)
        self._close_payment_dialog(accepted=False)
        super().closeEvent(event)
