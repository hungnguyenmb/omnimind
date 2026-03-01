"""
OmniMind - Tab 1: Dashboard Page
Trạng thái hệ thống, Update Center, điều khiển Bot.
"""
import platform
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QGridLayout
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from ui.icons import Icons


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
        self.os_name, self.os_version, self.os_icon = _detect_os()
        self.os_arch = platform.machine()
        self._setup_ui()

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
        cards_grid.addWidget(self._create_status_card(
            "Bản Quyền", "Pro License", "✅ Đã kích hoạt",
            "#10B981", "Hết hạn: 01/03/2027"
        ), 0, 0)

        # Card 2: Bot
        cards_grid.addWidget(self._create_status_card(
            "Telegram Bot", "Đang hoạt động", "🟢 Online",
            "#3B82F6", "Uptime: 2h 15m"
        ), 0, 1)

        # Card 3: Version + OS
        cards_grid.addWidget(self._create_status_card(
            "Phiên Bản", "v1.0.0", f"{self.os_icon} {self.os_name}",
            "#8B5CF6", "Cập nhật: 01/03/2026"
        ), 0, 2)

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

        check_btn = QPushButton("  Kiểm Tra")
        check_btn.setObjectName("SecondaryBtn")
        check_btn.setIcon(Icons.refresh("#3B82F6", 16))
        check_btn.setCursor(Qt.PointingHandCursor)
        check_btn.setMinimumHeight(36)
        update_header.addWidget(check_btn)
        update_layout.addLayout(update_header)

        changelog_text = QLabel(
            "• <b>v1.0.0</b> (01/03/2026): Phiên bản đầu tiên. Hỗ trợ Context Injection Engine, "
            "Skill Marketplace, License Gatekeeper.\n"
            "• Streaming Tư Duy AI trực tiếp qua Telegram.\n"
            "• System Tray, Auto-start cùng hệ điều hành."
        )
        changelog_text.setObjectName("ChangelogText")
        changelog_text.setWordWrap(True)
        changelog_text.setTextFormat(Qt.RichText)
        update_layout.addWidget(changelog_text)

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
        val.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
        card_layout.addWidget(val)

        badge_lbl = QLabel(badge)
        badge_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        card_layout.addWidget(badge_lbl)

        extra_lbl = QLabel(extra)
        extra_lbl.setStyleSheet("font-size: 12px; color: #94A3B8;")
        card_layout.addWidget(extra_lbl)

        return card

    def _add_card_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 12))
        shadow.setOffset(0, 4)
        widget.setGraphicsEffect(shadow)
