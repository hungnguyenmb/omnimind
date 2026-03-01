"""
OmniMind - Tab 5: Skill Marketplace
Kết nối API thật để xem marketplace, cài đặt và gỡ skills cho Codex.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QTabWidget,
    QScrollArea, QDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor

from ui.icons import Icons
from engine.skill_manager import SkillManager


class SkillLoadWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, manager: SkillManager, parent=None):
        super().__init__(parent)
        self.manager = manager

    def run(self):
        result = self.manager.fetch_marketplace_skills()
        if result.get("success"):
            skills = result.get("skills", [])
            message = ""
            success = True
        else:
            skills = self.manager.get_cached_marketplace_skills()
            message = result.get("message", "Không kết nối được server, đang dùng dữ liệu cache.")
            success = bool(skills)

        installed = self.manager.get_installed_skills()
        installed_ids = {row.get("skill_id") for row in installed}
        self.finished.emit({
            "success": success,
            "skills": skills,
            "installed_ids": installed_ids,
            "message": message,
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

        price = float(self.skill.get("price", 0) or 0)
        owned = bool(self.skill.get("is_owned", False))
        status_text = "Miễn phí" if price <= 0 else f"Giá: {price:.2f}"
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = SkillManager()
        self.skills = []
        self.installed_ids = set()
        self._load_worker = None
        self._action_worker = None
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
            "Tải về các kỹ năng AI chuyên biệt từ server và cài vào Codex local. "
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

    def _set_busy(self, busy: bool, text: str = ""):
        self.refresh_btn.setEnabled(not busy)
        if text:
            self.status_label.setText(text)

    def _reload_data(self):
        if self._load_worker and self._load_worker.isRunning():
            return
        self._set_busy(True, "Đang tải marketplace...")
        self._load_worker = SkillLoadWorker(self.manager, self)
        self._load_worker.finished.connect(self._on_loaded)
        self._load_worker.start()

    def _on_loaded(self, payload: dict):
        self._set_busy(False)
        self._load_worker = None
        self.skills = payload.get("skills", [])
        self.installed_ids = set(payload.get("installed_ids", set()))

        msg = payload.get("message", "")
        if msg:
            self.status_label.setText(msg)
        else:
            self.status_label.setText(f"Sẵn sàng · {len(self.skills)} skills")

        self._rebuild_tabs()

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

        for i, skill in enumerate(self.skills):
            installed = skill.get("id") in self.installed_ids
            card = self._create_skill_card(skill, installed=installed)
            grid.addWidget(card, i // 3, i % 3, Qt.AlignTop)

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

        installed_skills = [s for s in self.skills if s.get("id") in self.installed_ids]
        for i, skill in enumerate(installed_skills):
            card = self._create_skill_card(skill, installed=True)
            grid.addWidget(card, i // 3, i % 3, Qt.AlignTop)

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

    def _run_action(self, action: str, skill: dict):
        if self._action_worker and self._action_worker.isRunning():
            return

        skill_id = skill.get("id", "")
        requires_purchase = bool(skill.get("requires_purchase", False))
        verb = "cài đặt" if action == "install" else "gỡ cài đặt"
        self._set_busy(True, f"Đang {verb} skill '{skill_id}'...")

        self._action_worker = SkillActionWorker(
            self.manager, skill_id, action=action, requires_purchase=requires_purchase, parent=self
        )
        self._action_worker.finished.connect(self._on_action_finished)
        self._action_worker.start()

    def _on_action_finished(self, result: dict):
        self._set_busy(False)
        self._action_worker = None
        if result.get("success"):
            QMessageBox.information(self, "Skill Marketplace", result.get("message", "Thành công."))
            self._reload_data()
        else:
            QMessageBox.warning(self, "Skill Marketplace", result.get("message", "Thao tác thất bại."))
            self.status_label.setText("Có lỗi xảy ra, vui lòng thử lại.")
