"""
OmniMind - Tab 5: Skill Marketplace
Gian hàng kỹ năng VIP dựa trên phân quyền License. Download/Install/Delete Skills.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QTabWidget,
    QScrollArea, QDialog, QTextEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from ui.icons import Icons


# ── Dữ liệu mẫu Skills ──
STORE_SKILLS = [
    {"id": "web_crawler", "icon": "🌐", "name": "Web Crawler Pro", "badge": "VIP", "color": "#3B82F6",
     "version": "1.2.0", "author": "OmniMind Team",
     "short": "Tự động crawl và trích xuất dữ liệu từ hàng trăm website.",
     "detail": "Kỹ năng giúp AI tự động truy cập, phân tích và trích xuất dữ liệu có cấu trúc từ các trang web. "
               "Hỗ trợ: pagination, login bypass, proxy rotation, export CSV/JSON."},
    {"id": "email_auto", "icon": "📧", "name": "Email Automation", "badge": "VIP", "color": "#10B981",
     "version": "2.0.1", "author": "OmniMind Team",
     "short": "Soạn, gửi email hàng loạt thông minh qua Gmail/SMTP.",
     "detail": "Cho phép AI soạn nội dung email thông minh, gửi hàng loạt qua Gmail hoặc SMTP tùy chỉnh. "
               "Hỗ trợ template, đính kèm file, lên lịch gửi và theo dõi trạng thái."},
    {"id": "vps_mgr", "icon": "🖥", "name": "VPS Manager", "badge": "Pro", "color": "#8B5CF6",
     "version": "1.5.0", "author": "OmniMind Team",
     "short": "Quản lý, deploy ứng dụng Docker trên VPS từ xa.",
     "detail": "Kỹ năng quản lý VPS từ xa: SSH kết nối tự động, deploy Docker container, "
               "giám sát tài nguyên (CPU/RAM/Disk), cấu hình Nginx reverse proxy, SSL."},
    {"id": "data_analyst", "icon": "📊", "name": "Data Analyst", "badge": "VIP", "color": "#F59E0B",
     "version": "1.0.0", "author": "OmniMind Team",
     "short": "Phân tích dữ liệu Excel/CSV, tạo biểu đồ tự động.",
     "detail": "Phân tích file dữ liệu Excel/CSV với pandas, tạo biểu đồ matplotlib tự động, "
               "thống kê mô tả, pivot table, và xuất báo cáo PDF."},
    {"id": "security_scan", "icon": "🔒", "name": "Security Scanner", "badge": "Pro", "color": "#EF4444",
     "version": "1.1.0", "author": "OmniMind Team",
     "short": "Quét lỗ hổng bảo mật, audit server và ứng dụng web.",
     "detail": "Quét bảo mật tự động: kiểm tra port mở, SSL certificate, HTTP headers, "
               "phát hiện lỗ hổng OWASP Top 10, và tạo báo cáo audit chi tiết."},
    {"id": "social_poster", "icon": "📱", "name": "Social Poster", "badge": "VIP", "color": "#EC4899",
     "version": "1.3.0", "author": "OmniMind Team",
     "short": "Đăng bài tự động lên nhiều mạng xã hội đồng thời.",
     "detail": "Tự động đăng bài lên Facebook, Twitter/X, LinkedIn, Instagram đồng thời. "
               "Hỗ trợ lên lịch, tạo nội dung AI, upload hình ảnh và theo dõi engagement."},
]

# Skills đã cài (theo ID)
INSTALLED_IDS = {"web_crawler", "email_auto"}


class SkillDetailDialog(QDialog):
    """Popup hiển thị chi tiết Skill."""

    def __init__(self, parent=None, skill=None, installed=False):
        super().__init__(parent)
        self.skill = skill or {}
        self.setWindowTitle(skill.get("name", "Skill"))
        self.setMinimumSize(500, 380)
        self.resize(540, 420)
        self._setup_ui(installed)

    def _setup_ui(self, installed):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header: Icon + Name + Badge
        header_row = QHBoxLayout()
        icon_lbl = QLabel(self.skill.get("icon", ""))
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

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E2E8F0;")
        layout.addWidget(sep)

        # Short description
        short_lbl = QLabel(self.skill.get("short", ""))
        short_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #334155;")
        short_lbl.setWordWrap(True)
        layout.addWidget(short_lbl)

        # Detail description
        detail_lbl = QLabel(self.skill.get("detail", ""))
        detail_lbl.setStyleSheet("font-size: 14px; color: #64748B; line-height: 1.6;")
        detail_lbl.setWordWrap(True)
        layout.addWidget(detail_lbl)

        layout.addStretch()

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        close_btn = QPushButton("Đóng")
        close_btn.setObjectName("SecondaryBtn")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(44)
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        if installed:
            status_btn = QPushButton("  Đã cài đặt")
            status_btn.setIcon(Icons.check_circle("#10B981", 16))
            status_btn.setObjectName("InstalledBtn")
            status_btn.setEnabled(False)
            status_btn.setFixedHeight(44)
            status_btn.setMinimumWidth(160)
            btn_row.addWidget(status_btn)
        else:
            dl_btn = QPushButton("  Tải Về & Cài Đặt")
            dl_btn.setIcon(Icons.download("#FFFFFF", 16))
            dl_btn.setObjectName("PrimaryBtn")
            dl_btn.setCursor(Qt.PointingHandCursor)
            dl_btn.setFixedHeight(44)
            dl_btn.setMinimumWidth(180)
            dl_btn.clicked.connect(self.accept)
            btn_row.addWidget(dl_btn)

        layout.addLayout(btn_row)


class SkillStorePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # ── Page Header ──
        header = QWidget()
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)
        title = QLabel("Skill Marketplace")
        title.setObjectName("PageTitle")
        desc = QLabel("Tải về các kỹ năng AI chuyên biệt được cấp phép qua License Key. "
                       "Skill sẽ tự động inject vào AI Context cho lệnh Telegram tiếp theo.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(desc)
        layout.addWidget(header)

        # ── Tab Widget: Store / My Skills (stretch=1 để chiếm hết) ──
        tabs = QTabWidget()
        tabs.setObjectName("SkillTabs")

        # Sub-tab: Store
        store_tab = self._build_store_tab()
        tabs.addTab(store_tab, "🏪  Kho Kỹ Năng")

        # Sub-tab: My Skills
        my_skills_tab = self._build_my_skills_tab()
        tabs.addTab(my_skills_tab, "📦  Đã Cài Đặt")

        layout.addWidget(tabs, 1)  # stretch=1 để chiếm hết khoảng trống

    def _build_store_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("ScrollArea")

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(16)
        grid.setContentsMargins(16, 16, 16, 16)
        # Cột đều nhau
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        for i, skill in enumerate(STORE_SKILLS):
            is_installed = skill["id"] in INSTALLED_IDS
            card = self._create_skill_card(skill, installed=is_installed)
            grid.addWidget(card, i // 3, i % 3, Qt.AlignTop)

        scroll.setWidget(container)
        return scroll

    def _build_my_skills_tab(self):
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

        installed = [s for s in STORE_SKILLS if s["id"] in INSTALLED_IDS]

        for i, skill in enumerate(installed):
            card = self._create_skill_card(skill, installed=True)
            grid.addWidget(card, i // 3, i % 3, Qt.AlignTop)

        scroll.setWidget(container)
        return scroll

    def _create_skill_card(self, skill, installed=False):
        card = QFrame()
        card.setObjectName("SkillCard")
        card.setFixedHeight(230)
        card.setCursor(Qt.PointingHandCursor)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 10))
        shadow.setOffset(0, 3)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(10)

        # Icon + Badge row
        top_row = QHBoxLayout()
        icon_lbl = QLabel(skill.get("icon", ""))
        icon_lbl.setStyleSheet("font-size: 36px; background: transparent;")
        top_row.addWidget(icon_lbl)
        top_row.addStretch()
        badge_lbl = QLabel(skill.get("badge", ""))
        badge_lbl.setStyleSheet(
            f"background-color: {skill.get('color', '#64748B')}; color: white; font-size: 11px; "
            f"font-weight: 700; padding: 3px 10px; border-radius: 10px;"
        )
        top_row.addWidget(badge_lbl, alignment=Qt.AlignTop)
        card_layout.addLayout(top_row)

        # Name
        name_lbl = QLabel(skill.get("name", ""))
        name_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        card_layout.addWidget(name_lbl)

        # Short description
        desc_lbl = QLabel(skill.get("short", ""))
        desc_lbl.setStyleSheet("font-size: 13px; color: #64748B; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl)

        card_layout.addStretch()

        # Action Button / Status
        if installed:
            btn = QPushButton("  Đã cài đặt")
            btn.setIcon(Icons.check_circle("#10B981", 16))
            btn.setObjectName("InstalledBtn")
            btn.setEnabled(False)
        else:
            btn = QPushButton("  Tải Về")
            btn.setIcon(Icons.download("#FFFFFF", 16))
            btn.setObjectName("PrimaryBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(38)

        # Click card hoặc button mở popup chi tiết
        btn.clicked.connect(lambda checked, s=skill, inst=installed: self._show_detail(s, inst))
        card_layout.addWidget(btn)

        # Click vùng card cũng mở popup
        card.mousePressEvent = lambda event, s=skill, inst=installed: self._show_detail(s, inst)

        return card

    def _show_detail(self, skill, installed):
        dialog = SkillDetailDialog(self, skill=skill, installed=installed)
        if dialog.exec_() == QDialog.Accepted and not installed:
            # Khi user bấm "Tải Về & Cài Đặt" → thêm vào installed
            INSTALLED_IDS.add(skill["id"])
            # Refresh cả 2 tab
            parent_tabs = self.findChild(QTabWidget, "SkillTabs")
            if parent_tabs:
                # Rebuild Store tab
                parent_tabs.removeTab(0)
                parent_tabs.insertTab(0, self._build_store_tab(), "🏪  Kho Kỹ Năng")
                # Rebuild My Skills tab
                parent_tabs.removeTab(1)
                parent_tabs.addTab(self._build_my_skills_tab(), "📦  Đã Cài Đặt")
                parent_tabs.setCurrentIndex(0)
