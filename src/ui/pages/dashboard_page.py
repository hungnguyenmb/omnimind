"""
OmniMind - Tab 1: Dashboard Page
Trạng thái hệ thống, Update Center, điều khiển Bot.
"""
import platform
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QGridLayout, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from ui.icons import Icons
from engine.dashboard_manager import DashboardManager
from engine.config_manager import ConfigManager


def _detect_os():
    """Phát hiện hệ điều hành, trả về (name, version, icon_emoji)."""
    sys_name = platform.system()
    if sys_name == "Darwin":
        mac_ver = platform.mac_ver()[0]
        return "macOS", mac_ver or platform.release(), "🍎"
    elif sys_name == "Windows":
        win_ver = platform.version()
        return "Windows", win_ver, "🪟"
    elif sys_name == "Linux":
        return "Linux", platform.release(), "🐧"
    return sys_name, platform.release(), "💻"


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dashboard_mgr = DashboardManager()
        self.current_version = "1.0.0"
        self.os_name, self.os_version, self.os_icon = _detect_os()
        self.os_arch = platform.machine()
        
        # Widgets to update later
        self.license_val = None
        self.license_badge = None
        self.license_extra = None
        
        self.version_val = None
        self.version_badge = None
        
        self._setup_ui()
        self._load_dashboard_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        # ── Page Header ──
        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        desc = QLabel("Tổng quan trạng thái hệ thống OmniMind, cập nhật phiên bản và điều khiển AI Bot.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        header_layout.addWidget(title)
        header_layout.addWidget(desc)
        layout.addWidget(header)

        # ── Status Cards (2x2 Grid) ──
        cards_grid = QGridLayout()
        cards_grid.setSpacing(16)

        # Card 1: License
        self.license_card = self._create_status_card(
            "Bản Quyền", "...", "...",
            "#10B981", "..."
        )
        # Store refs to updateable labels
        self.license_val = self.license_card.findChild(QLabel, "ValueLbl")
        self.license_badge = self.license_card.findChild(QLabel, "BadgeLbl")
        self.license_extra = self.license_card.findChild(QLabel, "ExtraLbl")
        cards_grid.addWidget(self.license_card, 0, 0)

        # Card 2: Bot
        cards_grid.addWidget(self._create_status_card(
            "Telegram Bot", "Chờ khởi động", "⚪️ Offline",
            "#3B82F6", "Bot chưa chạy"
        ), 0, 1)

        # Card 4: Version + OS
        self.version_card = self._create_status_card(
            "Phiên Bản", f"v{self.current_version}", f"{self.os_icon} {self.os_name}",
            "#8B5CF6", "Cập nhật: 01/03/2026"
        )
        self.version_val = self.version_card.findChild(QLabel, "ValueLbl")
        self.version_badge = self.version_card.findChild(QLabel, "BadgeLbl")
        cards_grid.addWidget(self.version_card, 0, 2)

        layout.addLayout(cards_grid)

        # ── Bot Controller ──
        bot_frame = QFrame()
        bot_frame.setObjectName("Card")
        self._add_card_shadow(bot_frame)
        bot_layout = QVBoxLayout(bot_frame)
        bot_layout.setContentsMargins(28, 24, 28, 24)
        bot_layout.setSpacing(16)

        bot_header = QHBoxLayout()
        bot_title = QLabel("⚡  Điều Khiển AI Bot")
        bot_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        bot_header.addWidget(bot_title)
        bot_header.addStretch()

        self.bot_toggle_btn = QPushButton("  Bật Bot")
        self.bot_toggle_btn.setObjectName("PrimaryBtn")
        self.bot_toggle_btn.setIcon(Icons.power("#FFFFFF", 18))
        self.bot_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.bot_toggle_btn.setMinimumWidth(140)
        self.bot_toggle_btn.setMinimumHeight(42)
        bot_header.addWidget(self.bot_toggle_btn)

        bot_layout.addLayout(bot_header)

        bot_desc = QLabel("Khi bật, OmniMind sẽ lắng nghe tin nhắn từ Telegram và thực thi lệnh AI "
                          "với đầy đủ Context Injection Engine (Working Principles + Skills + Resources).")
        bot_desc.setObjectName("PageDesc")
        bot_desc.setWordWrap(True)
        bot_layout.addWidget(bot_desc)

        layout.addWidget(bot_frame)

        # ── Update Center ──
        update_frame = QFrame()
        update_frame.setObjectName("Card")
        self._add_card_shadow(update_frame)
        update_layout = QVBoxLayout(update_frame)
        update_layout.setContentsMargins(28, 24, 28, 24)
        update_layout.setSpacing(12)

        update_header = QHBoxLayout()
        update_title = QLabel("📋  Changelog & Cập Nhật")
        update_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        update_header.addWidget(update_title)
        update_header.addStretch()

        self.check_btn = QPushButton("  Kiểm Tra")
        self.check_btn.setObjectName("SecondaryBtn")
        self.check_btn.setIcon(Icons.refresh("#3B82F6", 16))
        self.check_btn.setCursor(Qt.PointingHandCursor)
        self.check_btn.setMinimumHeight(36)
        self.check_btn.clicked.connect(self._on_check_updates)
        update_header.addWidget(self.check_btn)
        update_layout.addLayout(update_header)

        self.changelog_text = QLabel(
            "• <b>v1.0.0</b> (01/03/2026): Phiên bản đầu tiên. Hỗ trợ Context Injection Engine, "
            "Skill Marketplace, License Gatekeeper.\n"
            "• Streaming Tư Duy AI trực tiếp qua Telegram.\n"
            "• System Tray, Auto-start cùng hệ điều hành."
        )
        self.changelog_text.setObjectName("ChangelogText")
        self.changelog_text.setWordWrap(True)
        self.changelog_text.setTextFormat(Qt.RichText)
        update_layout.addWidget(self.changelog_text)

        layout.addWidget(update_frame)
        layout.addStretch()

    def _create_status_card(self, label, value, badge, color, extra):
        card = QFrame()
        card.setObjectName("Card")
        self._add_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(8)

        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.5px;")
        card_layout.addWidget(lbl)

        val = QLabel(value)
        val.setObjectName("ValueLbl")
        val.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
        card_layout.addWidget(val)

        badge_lbl = QLabel(badge)
        badge_lbl.setObjectName("BadgeLbl")
        badge_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        card_layout.addWidget(badge_lbl)

        extra_lbl = QLabel(extra)
        extra_lbl.setObjectName("ExtraLbl")
        extra_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        card_layout.addWidget(extra_lbl)

        return card

    def _load_dashboard_data(self):
        """Load dữ liệu ban đầu từ config."""
        info = self.dashboard_mgr.get_license_display_info()
        if self.license_val:
            self.license_val.setText(f"{info['plan']} License")
        if self.license_badge:
            self.license_badge.setText(info['status'])
        if self.license_extra:
            expiry = info['expires_at']
            if expiry and expiry != "N/A":
                # Convert date format if needed, assuming simple string for now
                self.license_extra.setText(f"Hết hạn: {expiry}")
            else:
                self.license_extra.setText("Không giới hạn thời gian")

    def _on_check_updates(self):
        """Xử lý khi bấm nút Kiểm tra cập nhật."""
        self.check_btn.setEnabled(False)
        self.check_btn.setText("  Đang kiểm tra...")
        
        # Gọi API qua Manager
        result = self.dashboard_mgr.check_for_updates(self.current_version)
        
        self.check_btn.setEnabled(True)
        self.check_btn.setText("  Kiểm Tra")
        
        if not result.get("success"):
            QMessageBox.warning(self, "Lỗi", f"Không thể kiểm tra cập nhật: {result.get('message')}")
            return
            
        if result["has_update"]:
            new_v = result["latest_version"]
            msg = f"Đã có phiên bản mới: <b>v{new_v}</b> ({result.get('version_name')})."
            if result.get("is_critical"):
                msg += "<br><span style='color: #EF4444;'>Đây là bản cập nhật quan trọng!</span>"
            
            QMessageBox.information(self, "Cập Nhật Mới", msg)
            
            # Cập nhật changelog UI
            logs = result.get("changelogs", [])
            if logs:
                log_html = ""
                for l in logs:
                    type_tag = f"<b>[{l.get('change_type', 'feat').upper()}]</b>"
                    log_html += f"• {type_tag} {l.get('content')}<br>"
                self.changelog_text.setText(log_html)
        else:
            QMessageBox.information(self, "Thông Báo", f"Bạn đang sử dụng phiên bản mới nhất (v{self.current_version}).")

    def _add_card_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 12))
        shadow.setOffset(0, 4)
        widget.setGraphicsEffect(shadow)
