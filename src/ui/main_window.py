"""
OmniMind - Main Window
Sidebar Navigation kèm Icon, System Tray, và Routing giữa các Tab Pages.
"""
import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QPushButton, QStackedWidget, QLabel, QFrame,
    QGraphicsDropShadowEffect, QSystemTrayIcon, QMenu, QAction, QApplication
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QFont, QIcon

from ui.icons import Icons
from ui.pages.dashboard_page import DashboardPage
from ui.pages.auth_page import AuthPage
from ui.pages.memory_page import MemoryPage
from ui.pages.vault_page import VaultPage
from ui.pages.skill_store_page import SkillStorePage
from engine.config_manager import ConfigManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.app_version = (
            ConfigManager.get("app_current_version", "").strip()
            or os.environ.get("OMNIMIND_APP_VERSION", "1.0.0")
        )
        self.setWindowTitle("OmniMind - Pro AI Assistant")
        self.resize(1180, 780)
        self.setMinimumSize(960, 680)
        
        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        self._setup_sidebar()
        self._setup_content_area()
        self._setup_system_tray()
        
    # ──────────────────────────────────────────────
    #  SIDEBAR
    # ──────────────────────────────────────────────
    def _setup_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(250)
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(20, 32, 20, 24)
        sidebar_layout.setSpacing(6)
        
        # Logo
        logo_label = QLabel("✦ OmniMind")
        logo_label.setObjectName("LogoLabel")
        logo_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(logo_label)
        
        tagline = QLabel("Pro AI Assistant")
        tagline.setObjectName("LogoTagline")
        tagline.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(tagline)
        
        sidebar_layout.addSpacing(32)
        
        # Navigation Items (Text + Icon)
        self.nav_buttons = []
        nav_items = [
            ("Dashboard",           Icons.home,     0),
            ("Xác Thực & Cấu Hình", Icons.settings, 1),
            ("Quy Tắc & Trí Nhớ",   Icons.brain,    2),
            ("Kho Tài Nguyên",       Icons.shield,   3),
            ("Skill Marketplace",    Icons.grid,     4),
        ]
        
        for text, icon_fn, index in nav_items:
            btn = QPushButton(f"  {text}")
            btn.setObjectName("NavButton")
            btn.setIcon(icon_fn("#64748B", 20))
            btn.setIconSize(QSize(20, 20))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=index, b=btn, ifn=icon_fn: self._switch_tab(idx, b, ifn))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append((btn, icon_fn))
            
        sidebar_layout.addStretch()
        
        # Version footer
        version_lbl = QLabel(f"v{self.app_version} Pro")
        version_lbl.setObjectName("VersionLabel")
        version_lbl.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(version_lbl)
        
        # Sidebar shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 12))
        shadow.setOffset(2, 0)
        self.sidebar.setGraphicsEffect(shadow)
        
        self.main_layout.addWidget(self.sidebar)

    # ──────────────────────────────────────────────
    #  CONTENT AREA
    # ──────────────────────────────────────────────
    def _setup_content_area(self):
        self.content_area = QFrame()
        self.content_area.setObjectName("ContentArea")
        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(40, 36, 40, 36)
        
        self.stacked_widget = QStackedWidget()
        
        # Thêm các Tab Pages
        self.stacked_widget.addWidget(DashboardPage())    # 0
        self.stacked_widget.addWidget(AuthPage())         # 1
        self.stacked_widget.addWidget(MemoryPage())       # 2
        self.stacked_widget.addWidget(VaultPage())        # 3
        self.stacked_widget.addWidget(SkillStorePage())   # 4
        
        content_layout.addWidget(self.stacked_widget)
        self.main_layout.addWidget(self.content_area)
        
        # Default tab
        self._switch_tab(0, self.nav_buttons[0][0], self.nav_buttons[0][1])

    # ──────────────────────────────────────────────
    #  SYSTEM TRAY
    # ──────────────────────────────────────────────
    def _setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(Icons.brain("#2563EB", 64))
        self.tray_icon.setToolTip("OmniMind - Pro AI Assistant")
        
        tray_menu = QMenu()
        
        show_action = QAction("Mở OmniMind", self)
        show_action.triggered.connect(self.showNormal)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        toggle_action = QAction("Bật/Tắt Bot", self)
        tray_menu.addAction(toggle_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction("Thoát Hoàn Toàn", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    # ──────────────────────────────────────────────
    #  NAVIGATION LOGIC
    # ──────────────────────────────────────────────
    def _switch_tab(self, index, clicked_btn=None, icon_fn=None):
        self.stacked_widget.setCurrentIndex(index)
        for i, (btn, ifn) in enumerate(self.nav_buttons):
            if i == index:
                btn.setChecked(True)
                btn.setIcon(ifn("#2563EB", 20))
            else:
                btn.setChecked(False)
                btn.setIcon(ifn("#64748B", 20))

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        """Thu nhỏ xuống System Tray thay vì đóng App."""
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "OmniMind",
            "Ứng dụng đang chạy ngầm. Click đúp icon để mở lại.",
            QSystemTrayIcon.Information,
            2000
        )
