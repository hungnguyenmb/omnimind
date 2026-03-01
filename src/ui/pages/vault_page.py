"""
OmniMind - Tab 4: Vault (Resources)
Quản lý kho tài nguyên nhạy cảm (SSH, Email, API Keys, Database).
Form động thay đổi theo loại Resource.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QLineEdit, QComboBox,
    QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from ui.icons import Icons


# ─────────────────────────────────────────────
#  Cấu hình Form động theo loại Resource
# ─────────────────────────────────────────────
RESOURCE_FIELDS = {
    "SSH": [
        {"key": "host", "label": "Host / IP", "placeholder": "192.168.1.100"},
        {"key": "port", "label": "Cổng SSH", "placeholder": "22"},
        {"key": "username", "label": "Username", "placeholder": "root"},
        {"key": "password", "label": "Mật khẩu", "placeholder": "Nhập mật khẩu SSH", "secret": True},
        {"key": "description", "label": "Mô tả", "placeholder": "Ví dụ: VPS Production"},
    ],
    "Email": [
        {"key": "provider", "label": "Nhà cung cấp", "type": "combo", "options": ["Gmail", "Outlook", "Yahoo", "Khác"]},
        {"key": "username", "label": "Tài khoản Email", "placeholder": "admin@gmail.com"},
        {"key": "password", "label": "Mật khẩu / App Password", "placeholder": "Nhập mật khẩu email", "secret": True},
        {"key": "description", "label": "Mô tả", "placeholder": "Ví dụ: Gmail gửi báo cáo"},
    ],
    "API_KEY": [
        {"key": "provider", "label": "Nhà cung cấp", "type": "combo", "options": ["ChatGPT / OpenAI", "Gemini / Google", "Grok / xAI", "Claude / Anthropic", "Khác"]},
        {"key": "api_key", "label": "API Key", "placeholder": "sk-proj-...", "secret": True},
        {"key": "description", "label": "Mô tả", "placeholder": "Ví dụ: OpenAI API cho dự án X"},
    ],
    "Database": [
        {"key": "host", "label": "Host / IP", "placeholder": "localhost hoặc 192.168.1.100"},
        {"key": "port", "label": "Cổng", "placeholder": "5432"},
        {"key": "username", "label": "Username", "placeholder": "postgres"},
        {"key": "password", "label": "Mật khẩu", "placeholder": "Nhập mật khẩu DB", "secret": True},
        {"key": "db_name", "label": "Tên Database", "placeholder": "my_database"},
        {"key": "description", "label": "Mô tả", "placeholder": "Ví dụ: PostgreSQL Production"},
    ],
    "Hệ điều hành": [
        {"key": "username", "label": "Username", "placeholder": "Ví dụ: admin"},
        {"key": "password", "label": "Mật khẩu", "placeholder": "Mật khẩu đăng nhập máy tính", "secret": True},
        {"key": "description", "label": "Mô tả", "placeholder": "Ví dụ: Máy tính cá nhân Mac"},
    ],
}


class ResourceDialog(QDialog):
    """Popup Thêm / Sửa Resource. Form thay đổi động theo loại Resource."""

    def __init__(self, parent=None, mode="add", resource_type="SSH", data=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm Resource Mới" if mode == "add" else "Sửa Resource")
        self.setMinimumSize(580, 520)
        self.resize(620, 580)
        self.mode = mode
        self.field_widgets = {}
        self._setup_ui(resource_type, data or {})

    def _setup_ui(self, resource_type, data):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(32, 28, 32, 28)
        self.main_layout.setSpacing(16)

        # Loại Resource (cố định bên ngoài scroll)
        self.main_layout.addWidget(self._label("Loại Resource"))
        self.type_combo = QComboBox()
        self.type_combo.setObjectName("FormCombo")
        self.type_combo.addItems(list(RESOURCE_FIELDS.keys()))
        self.type_combo.setFixedHeight(44)
        if resource_type in RESOURCE_FIELDS:
            self.type_combo.setCurrentText(resource_type)
        self.type_combo.currentTextChanged.connect(self._rebuild_fields)
        self.main_layout.addWidget(self.type_combo)

        # ScrollArea chứa dynamic fields
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("ScrollArea")
        self.scroll_content = QWidget()
        self.fields_layout = QVBoxLayout(self.scroll_content)
        self.fields_layout.setContentsMargins(0, 8, 4, 8)
        self.fields_layout.setSpacing(6)
        self.scroll.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll, 1)

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

        save_btn = QPushButton("  Lưu")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setIcon(Icons.check_circle("#FFFFFF", 16))
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(44)
        save_btn.setMinimumWidth(140)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)
        self.main_layout.addLayout(btn_row)

        # Build initial fields
        self._rebuild_fields(resource_type, data)

    def _rebuild_fields(self, resource_type, prefill=None):
        """Xoá fields cũ, tạo fields mới theo loại Resource."""
        if prefill is None:
            prefill = {}

        # Clear old widgets + nested layouts
        def _clear_layout(layout):
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
                elif child.layout():
                    _clear_layout(child.layout())

        _clear_layout(self.fields_layout)

        self.field_widgets = {}
        fields = RESOURCE_FIELDS.get(resource_type, [])

        for field in fields:
            # Label
            lbl = self._label(field["label"])
            self.fields_layout.addWidget(lbl)

            # Widget
            if field.get("type") == "combo":
                widget = QComboBox()
                widget.setObjectName("FormCombo")
                widget.addItems(field["options"])
                widget.setFixedHeight(44)
                val = prefill.get(field["key"], "")
                if val:
                    idx = widget.findText(val)
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                self.fields_layout.addWidget(widget)
            elif field.get("secret"):
                # Mật khẩu: input + nút con mắt ẩn/hiện
                widget = QLineEdit()
                widget.setObjectName("FormInput")
                widget.setPlaceholderText(field.get("placeholder", ""))
                widget.setFixedHeight(44)
                widget.setEchoMode(QLineEdit.Password)
                widget.setText(prefill.get(field["key"], ""))

                eye_btn = QPushButton()
                eye_btn.setIcon(Icons.eye("#64748B", 16))
                eye_btn.setObjectName("IconBtn")
                eye_btn.setCursor(Qt.PointingHandCursor)
                eye_btn.setToolTip("Hiện/Ẩn mật khẩu")
                eye_btn.setFixedSize(40, 44)

                def _toggle_echo(checked, w=widget):
                    if w.echoMode() == QLineEdit.Password:
                        w.setEchoMode(QLineEdit.Normal)
                    else:
                        w.setEchoMode(QLineEdit.Password)

                eye_btn.clicked.connect(_toggle_echo)

                row = QHBoxLayout()
                row.setSpacing(6)
                row.addWidget(widget)
                row.addWidget(eye_btn)
                self.fields_layout.addLayout(row)
            else:
                widget = QLineEdit()
                widget.setObjectName("FormInput")
                widget.setPlaceholderText(field.get("placeholder", ""))
                widget.setFixedHeight(44)
                widget.setText(prefill.get(field["key"], ""))
                self.fields_layout.addWidget(widget)

            self.field_widgets[field["key"]] = widget

            # Khoảng cách giữa các nhóm field
            self.fields_layout.addSpacing(4)

        self.fields_layout.addStretch()

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setFixedHeight(20)
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #64748B;")
        return lbl

    def get_data(self):
        res_type = self.type_combo.currentText()
        data = {"type": res_type}
        for key, widget in self.field_widgets.items():
            if isinstance(widget, QComboBox):
                data[key] = widget.currentText()
            else:
                data[key] = widget.text().strip()
        return data


# ─────────────────────────────────────────────
#  Vault Page
# ─────────────────────────────────────────────
class VaultPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sample_data = [
            {"type": "SSH", "host": "192.168.1.100", "port": "22", "username": "root", "password": "my_pass_123", "description": "VPS Production"},
            {"type": "Email", "provider": "Gmail", "username": "admin@gmail.com", "password": "app_pass_abc", "description": "Gmail gửi báo cáo"},
            {"type": "API_KEY", "provider": "ChatGPT / OpenAI", "api_key": "sk-proj-abc123xyz", "description": "OpenAI API Key"},
        ]
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
        title = QLabel("Kho Tài Nguyên")
        title.setObjectName("PageTitle")
        desc = QLabel("Lưu trữ các thông tin kết nối (SSH, Email, API Key, Database) được mã hoá. "
                       "AI sẽ tham chiếu Resources này khi thực thi lệnh.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(desc)
        layout.addWidget(header)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        add_btn = QPushButton("  Thêm Resource")
        add_btn.setObjectName("PrimaryBtn")
        add_btn.setIcon(Icons.plus("#FFFFFF", 16))
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setMinimumHeight(40)
        add_btn.clicked.connect(self._show_add_dialog)
        toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)

        # ── Resources Table Card ──
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
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Loại", "Host/IP/Provider", "Username/Key", "Credentials", "Mô tả", "Hành động"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(0, 80)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(3, 100)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.table.horizontalHeader().resizeSection(5, 110)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(280)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        self._populate_table()

        card_layout.addWidget(self.table)
        layout.addWidget(table_card)
        layout.addStretch()

    def _get_display_fields(self, data):
        res_type = data.get("type", "")
        if res_type == "SSH":
            return data.get("host", ""), data.get("username", ""), data.get("password", "")
        elif res_type == "Email":
            return data.get("provider", ""), data.get("username", ""), data.get("password", "")
        elif res_type == "API_KEY":
            return data.get("provider", ""), data.get("api_key", "")[:12] + "...", data.get("api_key", "")
        elif res_type == "Database":
            return data.get("host", ""), data.get("username", ""), data.get("password", "")
        elif res_type == "Hệ điều hành":
            return "OS Login", data.get("username", ""), data.get("password", "")
        return "", "", ""

    def _populate_table(self):
        self.table.setRowCount(len(self._sample_data))
        for i, data in enumerate(self._sample_data):
            res_type = data.get("type", "")
            host_or_provider, user_or_key, cred = self._get_display_fields(data)

            type_item = QTableWidgetItem(res_type)
            type_colors = {"SSH": "#10B981", "Email": "#3B82F6", "API_KEY": "#8B5CF6", "Database": "#F59E0B"}
            type_item.setForeground(QColor(type_colors.get(res_type, "#64748B")))
            type_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, type_item)
            self.table.setItem(i, 1, QTableWidgetItem(host_or_provider))
            self.table.setItem(i, 2, QTableWidgetItem(user_or_key))
            self.table.setItem(i, 3, QTableWidgetItem("••••••••"))
            self.table.setItem(i, 4, QTableWidgetItem(data.get("description", "")))

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(8, 2, 8, 2)
            action_layout.setSpacing(6)
            action_layout.setAlignment(Qt.AlignCenter)

            edit_btn = QPushButton()
            edit_btn.setIcon(Icons.edit("#3B82F6", 16))
            edit_btn.setObjectName("IconBtn")
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setToolTip("Sửa Resource")
            edit_btn.clicked.connect(lambda checked, row=i: self._show_edit_dialog(row))
            action_layout.addWidget(edit_btn)

            del_btn = QPushButton()
            del_btn.setIcon(Icons.trash("#EF4444", 16))
            del_btn.setObjectName("IconBtn")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setToolTip("Xoá Resource")
            del_btn.clicked.connect(lambda checked, row=i: self._confirm_delete(row))
            action_layout.addWidget(del_btn)

            self.table.setCellWidget(i, 5, action_widget)
            self.table.setRowHeight(i, 52)

    def _show_add_dialog(self):
        dialog = ResourceDialog(self, mode="add")
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if any(v for k, v in data.items() if k != "type"):
                self._sample_data.append(data)
                self._populate_table()

    def _show_edit_dialog(self, row):
        if row >= len(self._sample_data):
            return
        data = self._sample_data[row]
        dialog = ResourceDialog(self, mode="edit", resource_type=data.get("type", "SSH"), data=data)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data()
            self._sample_data[row] = new_data
            self._populate_table()

    def _confirm_delete(self, row):
        if row >= len(self._sample_data):
            return
        desc = self._sample_data[row].get("description", self._sample_data[row].get("type", ""))
        reply = QMessageBox.question(
            self, "Xác nhận Xoá",
            f"Bạn có chắc chắn muốn xoá resource \"{desc}\" không?\n\nHành động này không thể hoàn tác.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            del self._sample_data[row]
            self._populate_table()
