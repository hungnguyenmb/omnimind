"""
OmniMind - Tab 3: Memory & Rules (Working Principles)
Quản lý CRUD các bộ quy tắc cốt lõi định hướng hành vi AI.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QTextEdit, QLineEdit,
    QComboBox, QMessageBox, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from ui.icons import Icons
from engine.memory_manager import MemoryManager
from engine.assistant_memory_manager import AssistantMemoryManager


class RuleDialog(QDialog):
    """Popup soạn thảo quy tắc (Thêm mới / Sửa). Kích thước lớn cho dễ nhập liệu."""
    def __init__(self, parent=None, rule_id=None, title="", content="", is_active=True, mode="add"):
        super().__init__(parent)
        self.rule_id = rule_id
        self.setWindowTitle("Thêm Quy Tắc Mới" if mode == "add" else "Sửa Quy Tắc")
        self.setMinimumSize(640, 520)
        self.resize(700, 560)
        self._setup_ui(title, content, is_active, mode)

    def _setup_ui(self, title, content, is_active, mode):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Title input
        layout.addWidget(self._label("Tiêu đề Quy Tắc"))
        self.title_input = QLineEdit()
        self.title_input.setObjectName("FormInput")
        self.title_input.setFixedHeight(44)
        self.title_input.setPlaceholderText("Ví dụ: Nguyên tắc An toàn")
        self.title_input.setText(title)
        layout.addWidget(self.title_input)

        # Content input (lớn, chiếm phần lớn popup)
        layout.addWidget(self._label("Nội dung Chi tiết"))
        self.content_input = QTextEdit()
        self.content_input.setObjectName("FormInput")
        self.content_input.setPlaceholderText("Mô tả chi tiết quy tắc cho AI tuân thủ...\n\n"
                                              "Nội dung này sẽ được nạp trực tiếp vào System Context "
                                              "mỗi khi AI xử lý lệnh.")
        self.content_input.setText(content)
        self.content_input.setMinimumHeight(240)
        layout.addWidget(self.content_input, 1)  # stretch=1 chiếm không gian còn lại

        # Status combo (chỉ hiển thị khi Sửa)
        if mode == "edit":
            layout.addWidget(self._label("Trạng thái"))
            self.status_combo = QComboBox()
            self.status_combo.setObjectName("FormCombo")
            self.status_combo.addItems(["🟢 On", "🔴 Off"])
            self.status_combo.setCurrentIndex(0 if is_active else 1)
            self.status_combo.setFixedHeight(44)
            layout.addWidget(self.status_combo)
        else:
            self.status_combo = None

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Huỷ")
        cancel_btn.setObjectName("SecondaryBtn")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(44)
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("  Lưu Quy Tắc")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setIcon(Icons.check_circle("#FFFFFF", 16))
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(44)
        save_btn.setMinimumWidth(160)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setFixedHeight(20)
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #64748B;")
        return lbl

    def get_data(self):
        is_active = True
        if self.status_combo:
            is_active = self.status_combo.currentIndex() == 0
        return self.rule_id, self.title_input.text().strip(), self.content_input.toPlainText().strip(), is_active


class MemoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.memory_mgr = MemoryManager()
        self.assistant_mem_mgr = AssistantMemoryManager()
        self.assistant_name_input = None
        self.assistant_persona_input = None
        self.assistant_hint = None
        self._setup_ui()
        self._load_profile()
        self._load_rules()

    def _setup_ui(self):
        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("ScrollArea")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        # ── Page Header ──
        header = QWidget()
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)
        title = QLabel("Quy Tắc & Trí Nhớ")
        title.setObjectName("PageTitle")
        desc = QLabel("Định nghĩa các quy tắc cốt lõi (Working Principles). "
                       "Nội dung này sẽ được tự động nạp vào bộ nhớ của AI.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(desc)
        layout.addWidget(header)

        # ── Assistant Profile Card ──
        profile_card = QFrame()
        profile_card.setObjectName("Card")
        profile_shadow = QGraphicsDropShadowEffect()
        profile_shadow.setBlurRadius(20)
        profile_shadow.setColor(QColor(0, 0, 0, 12))
        profile_shadow.setOffset(0, 4)
        profile_card.setGraphicsEffect(profile_shadow)

        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(22, 18, 22, 18)
        profile_layout.setSpacing(10)

        profile_title = QLabel("Hồ Sơ Trợ Lý (Assistant Profile)")
        profile_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        profile_layout.addWidget(profile_title)

        profile_desc = QLabel(
            "Thông tin này sẽ được nạp vào bộ nhớ để OmniMind hiểu cách xưng hô và phong cách phản hồi mong muốn."
        )
        profile_desc.setStyleSheet("font-size: 12px; color: #64748B;")
        profile_desc.setWordWrap(True)
        profile_layout.addWidget(profile_desc)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.assistant_name_input = QLineEdit()
        self.assistant_name_input.setObjectName("FormInput")
        self.assistant_name_input.setPlaceholderText("Tên hiển thị người dùng (VD: Sếp, Boss, Chủ tịch...)")
        self.assistant_name_input.setMinimumHeight(40)
        row1.addWidget(self.assistant_name_input, 1)

        save_profile_btn = QPushButton("  Lưu Hồ Sơ")
        save_profile_btn.setObjectName("PrimaryBtn")
        save_profile_btn.setIcon(Icons.check_circle("#FFFFFF", 16))
        save_profile_btn.setCursor(Qt.PointingHandCursor)
        save_profile_btn.setMinimumHeight(40)
        save_profile_btn.setMinimumWidth(150)
        save_profile_btn.clicked.connect(self._save_profile)
        row1.addWidget(save_profile_btn)
        profile_layout.addLayout(row1)

        self.assistant_persona_input = QTextEdit()
        self.assistant_persona_input.setObjectName("FormInput")
        self.assistant_persona_input.setPlaceholderText(
            "Persona của trợ lý (VD: Luôn trả lời ngắn gọn, rõ hành động, xưng em gọi người dùng là sếp...)"
        )
        self.assistant_persona_input.setMinimumHeight(110)
        self.assistant_persona_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        profile_layout.addWidget(self.assistant_persona_input)

        self.assistant_hint = QLabel("")
        self.assistant_hint.setStyleSheet("font-size: 12px; color: #64748B; padding: 2px 2px 4px 2px;")
        self.assistant_hint.setWordWrap(True)
        profile_layout.addWidget(self.assistant_hint)

        layout.addWidget(profile_card)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        add_btn = QPushButton("  Thêm Quy Tắc")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.setIcon(Icons.plus("#FFFFFF", 16))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setMinimumHeight(40)
        add_btn.clicked.connect(self._show_add_dialog)
        toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)

        # ── Rules Table Card ──
        table_card = QFrame()
        table_card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 12))
        shadow.setOffset(0, 4)
        table_card.setGraphicsEffect(shadow)
        card_layout = QVBoxLayout(table_card)
        card_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setObjectName("DataTable")
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["STT", "Tiêu đề", "Nội dung", "Trạng thái", "Hành động"])

        # Column sizes
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(0, 50)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(1, 180)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(3, 110)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(4, 110)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(300)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self._rules_data = []
        # self._populate_table() # Will be called by _load_rules

        card_layout.addWidget(self.table)
        layout.addWidget(table_card)
        layout.addStretch()
        scroll.setWidget(scroll_content)
        wrapper.addWidget(scroll)

    def _load_rules(self):
        """Tải dữ liệu quy tắc từ DB."""
        self._rules_data = self.memory_mgr.get_all_rules()
        self._populate_table()

    def _load_profile(self):
        profile = self.assistant_mem_mgr.get_profile()
        if self.assistant_name_input is not None:
            self.assistant_name_input.setText(str(profile.get("display_name") or ""))
        if self.assistant_persona_input is not None:
            self.assistant_persona_input.setPlainText(str(profile.get("persona_prompt") or ""))
        if self.assistant_hint is not None:
            self.assistant_hint.setStyleSheet("font-size: 12px; color: #64748B; padding: 2px 2px 4px 2px;")
            self.assistant_hint.setText(
                "Đã nạp hồ sơ vào bộ não của OmniMind."
            )

    def _save_profile(self):
        display_name = (self.assistant_name_input.text() if self.assistant_name_input else "").strip()
        persona_prompt = (
            self.assistant_persona_input.toPlainText() if self.assistant_persona_input else ""
        ).strip()
        ok = self.assistant_mem_mgr.update_profile(
            display_name=display_name,
            persona_prompt=persona_prompt,
            preferences=None,
        )
        if ok:
            if self.assistant_hint is not None:
                self.assistant_hint.setStyleSheet("font-size: 12px; color: #10B981;")
                self.assistant_hint.setText("Đã lưu Assistant Profile. Áp dụng cho các tin nhắn Telegram mới.")
            return

        if self.assistant_hint is not None:
            self.assistant_hint.setStyleSheet("font-size: 12px; color: #EF4444;")
            self.assistant_hint.setText("Lưu Assistant Profile thất bại.")
        QMessageBox.warning(self, "Lỗi", "Không thể lưu Assistant Profile vào database.")

    def _populate_table(self):
        self.table.setRowCount(len(self._rules_data))
        for i, rule in enumerate(self._rules_data):
            # STT
            stt_item = QTableWidgetItem(str(i + 1))
            stt_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, stt_item)

            # Tiêu đề
            title_item = QTableWidgetItem(rule["title"])
            self.table.setItem(i, 1, title_item)

            # Nội dung
            content_item = QTableWidgetItem(rule["content"])
            content_item.setToolTip(rule["content"])
            self.table.setItem(i, 2, content_item)

            # Trạng thái
            status_item = QTableWidgetItem("🟢 On" if rule["is_active"] else "🔴 Off")
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, status_item)

            # Action buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(8, 2, 8, 2)
            action_layout.setSpacing(6)
            action_layout.setAlignment(Qt.AlignCenter)

            edit_btn = QPushButton()
            edit_btn.setIcon(Icons.edit("#3B82F6", 16))
            edit_btn.setObjectName("IconBtn")
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setToolTip("Sửa quy tắc")
            edit_btn.clicked.connect(lambda checked, row=i: self._show_edit_dialog(row))
            action_layout.addWidget(edit_btn)

            del_btn = QPushButton()
            del_btn.setIcon(Icons.trash("#EF4444", 16))
            del_btn.setObjectName("IconBtn")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setToolTip("Xoá quy tắc")
            del_btn.clicked.connect(lambda checked, row=i: self._confirm_delete(row))
            action_layout.addWidget(del_btn)

            self.table.setCellWidget(i, 4, action_widget)
            self.table.setRowHeight(i, 52)

    def _show_add_dialog(self):
        dialog = RuleDialog(self, mode="add")
        if dialog.exec_() == QDialog.Accepted:
            _, title, content, is_active = dialog.get_data()
            if title and content:
                if self.memory_mgr.add_rule(title, content, is_active):
                    self._load_rules()
                else:
                    QMessageBox.warning(self, "Lỗi", "Không thể lưu quy tắc vào database.")

    def _show_edit_dialog(self, row):
        if row >= len(self._rules_data):
            return
        rule = self._rules_data[row]
        dialog = RuleDialog(self, rule_id=rule["id"], title=rule["title"], content=rule["content"], is_active=rule["is_active"], mode="edit")
        if dialog.exec_() == QDialog.Accepted:
            rule_id, new_title, new_content, new_active = dialog.get_data()
            if new_title and new_content:
                if self.memory_mgr.update_rule(rule_id, new_title, new_content, new_active):
                    self._load_rules()
                else:
                    QMessageBox.warning(self, "Lỗi", "Không thể cập nhật quy tắc.")

    def _confirm_delete(self, row):
        if row >= len(self._rules_data):
            return
        rule = self._rules_data[row]
        reply = QMessageBox.question(
            self,
            "Xác nhận Xoá",
            f"Bạn có chắc chắn muốn xoá quy tắc \"{rule['title']}\" không?\n\n"
            f"Hành động này không thể hoàn tác.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.memory_mgr.delete_rule(rule["id"]):
                self._load_rules()
            else:
                QMessageBox.warning(self, "Lỗi", "Không thể xoá quy tắc.")
