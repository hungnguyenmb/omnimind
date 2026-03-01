"""
OmniMind - Tab 3: Memory & Rules (Working Principles)
Quản lý CRUD các bộ quy tắc cốt lõi định hướng hành vi AI.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QTextEdit, QLineEdit,
    QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from ui.icons import Icons


class RuleDialog(QDialog):
    """Popup soạn thảo quy tắc (Thêm mới / Sửa). Kích thước lớn cho dễ nhập liệu."""
    def __init__(self, parent=None, title="", content="", is_active=True, mode="add"):
        super().__init__(parent)
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
                                              "Nội dung này sẽ được inject trực tiếp vào System Context "
                                              "mỗi khi AI xử lý lệnh từ Telegram.")
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
        return self.title_input.text().strip(), self.content_input.toPlainText().strip(), is_active


class MemoryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
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
                       "Nội dung này sẽ được tự động inject vào mọi lệnh AI gửi qua Telegram.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(desc)
        layout.addWidget(header)

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

        # Dữ liệu mẫu (demo UI)
        self._sample_data = [
            ("Nguyên tắc An toàn", "Luôn kiểm tra kỹ trước khi thực thi lệnh xóa hoặc sửa file hệ thống.", True),
            ("Quy tắc Báo cáo", "Sau mỗi tác vụ, gửi tóm tắt kết quả qua Telegram cho người dùng.", True),
            ("Quy tắc Skill", "Khi tạo skill mới, in tag [NEW_SKILL] kèm JSON để App tự động lưu.", True),
        ]
        self._populate_table()

        card_layout.addWidget(self.table)
        layout.addWidget(table_card)
        layout.addStretch()

    def _populate_table(self):
        self.table.setRowCount(len(self._sample_data))
        for i, (t, c, active) in enumerate(self._sample_data):
            # STT
            stt_item = QTableWidgetItem(str(i + 1))
            stt_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, stt_item)

            # Tiêu đề
            title_item = QTableWidgetItem(t)
            self.table.setItem(i, 1, title_item)

            # Nội dung
            content_item = QTableWidgetItem(c)
            content_item.setToolTip(c)
            self.table.setItem(i, 2, content_item)

            # Trạng thái
            status_item = QTableWidgetItem("🟢 On" if active else "🔴 Off")
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
            title, content, _ = dialog.get_data()
            if title and content:
                self._sample_data.append((title, content, True))
                self._populate_table()

    def _show_edit_dialog(self, row):
        if row >= len(self._sample_data):
            return
        t, c, active = self._sample_data[row]
        dialog = RuleDialog(self, title=t, content=c, is_active=active, mode="edit")
        if dialog.exec_() == QDialog.Accepted:
            new_title, new_content, new_active = dialog.get_data()
            if new_title and new_content:
                self._sample_data[row] = (new_title, new_content, new_active)
                self._populate_table()

    def _confirm_delete(self, row):
        if row >= len(self._sample_data):
            return
        title = self._sample_data[row][0]
        reply = QMessageBox.question(
            self,
            "Xác nhận Xoá",
            f"Bạn có chắc chắn muốn xoá quy tắc \"{title}\" không?\n\n"
            f"Hành động này không thể hoàn tác.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            del self._sample_data[row]
            self._populate_table()
