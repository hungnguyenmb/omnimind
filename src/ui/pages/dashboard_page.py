"""
OmniMind - Tab 1: Dashboard Page
Trạng thái hệ thống, Update Center, điều khiển Bot.
"""
import platform
import sys

from PyQt5.QtCore import QProcess, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.dashboard_manager import DashboardManager
from engine.skill_manager import SkillManager
from ui.icons import Icons


class UpdateInstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, dashboard_mgr, download_url: str, target_version: str, parent=None):
        super().__init__(parent)
        self.dashboard_mgr = dashboard_mgr
        self.download_url = download_url
        self.target_version = target_version

    def run(self):
        try:
            result = self.dashboard_mgr.install_update(
                self.download_url,
                self.target_version,
                progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
            )
        except Exception as e:
            result = {"success": False, "message": f"Lỗi cài đặt update: {str(e)[:160]}"}
        self.finished.emit(result)


class UpdateCheckWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, dashboard_mgr, current_version: str, parent=None):
        super().__init__(parent)
        self.dashboard_mgr = dashboard_mgr
        self.current_version = current_version

    def run(self):
        try:
            result = self.dashboard_mgr.check_for_updates(self.current_version)
        except Exception as e:
            result = {"success": False, "message": f"Lỗi kiểm tra cập nhật: {str(e)[:160]}"}
        self.finished.emit(result)


class BotRuntimeActionWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(
        self,
        skill_manager: SkillManager,
        skill_id: str,
        action_id: str,
        payload: dict | None = None,
        auto_request_permissions: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.skill_manager = skill_manager
        self.skill_id = skill_id
        self.action_id = action_id
        self.payload = payload or {}
        self.auto_request_permissions = auto_request_permissions

    def run(self):
        try:
            result = self.skill_manager.execute_builtin_skill_action(
                skill_id=self.skill_id,
                action_id=self.action_id,
                payload=self.payload,
                auto_request_permissions=self.auto_request_permissions,
            )
        except Exception as e:
            result = {"success": False, "code": "BOT_RUNTIME_EXCEPTION", "message": str(e)}
        self.finished.emit(result)


class BotToggleWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, dashboard_mgr: DashboardManager, enable: bool, parent=None):
        super().__init__(parent)
        self.dashboard_mgr = dashboard_mgr
        self.enable = bool(enable)

    def run(self):
        try:
            if self.enable:
                result = self.dashboard_mgr.start_telegram_bot()
            else:
                result = self.dashboard_mgr.stop_telegram_bot()
        except Exception as e:
            result = {"success": False, "message": str(e)}
        self.finished.emit(result)


def _detect_os():
    """Phát hiện hệ điều hành, trả về (name, version, icon_emoji)."""
    sys_name = platform.system()
    if sys_name == "Darwin":
        mac_ver = platform.mac_ver()[0]
        return "macOS", mac_ver or platform.release(), "🍎"
    if sys_name == "Windows":
        win_ver = platform.version()
        return "Windows", win_ver, "🪟"
    if sys_name == "Linux":
        return "Linux", platform.release(), "🐧"
    return sys_name, platform.release(), "💻"


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dashboard_mgr = DashboardManager()
        self.skill_mgr = SkillManager()
        self.current_version = self.dashboard_mgr.get_current_version()
        self.os_name, self.os_version, self.os_icon = _detect_os()
        self.os_arch = platform.machine()
        self._update_worker = None
        self._check_worker = None
        self._bot_action_worker = None
        self._bot_toggle_worker = None
        self._pending_bot_action = ""
        self._pending_bot_enable = False
        self._latest_update_info = {}

        # Widgets to update later
        self.license_val = None
        self.license_badge = None
        self.license_extra = None

        self.version_val = None
        self.version_badge = None
        self.update_btn = None
        self.update_progress = None
        self.update_progress_text = None
        self.bot_val = None
        self.bot_badge = None
        self.bot_extra = None
        self.bot_toggle_btn = None
        self.bot_test_capture_btn = None

        self._setup_ui()
        self._load_dashboard_data()
        self._load_bot_status()
        self._start_update_check(silent=True)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        # Page Header
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

        # Status Cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(16)

        self.license_card = self._create_status_card("Bản Quyền", "...", "...", "#10B981", "...")
        self.license_val = self.license_card.findChild(QLabel, "ValueLbl")
        self.license_badge = self.license_card.findChild(QLabel, "BadgeLbl")
        self.license_extra = self.license_card.findChild(QLabel, "ExtraLbl")
        cards_grid.addWidget(self.license_card, 0, 0)

        self.bot_card = self._create_status_card(
            "Telegram Bot",
            "Chờ khởi động",
            '<span style="color: #94A3B8;">●</span> Offline',
            "#3B82F6",
            "Bot chưa chạy",
        )
        self.bot_val = self.bot_card.findChild(QLabel, "ValueLbl")
        self.bot_badge = self.bot_card.findChild(QLabel, "BadgeLbl")
        self.bot_extra = self.bot_card.findChild(QLabel, "ExtraLbl")
        cards_grid.addWidget(self.bot_card, 0, 1)

        self.version_card = self._create_status_card(
            "Phiên Bản",
            f"v{self.current_version}",
            f"{self.os_icon} {self.os_name}",
            "#8B5CF6",
            "Theo dõi cập nhật tự động",
        )
        self.version_val = self.version_card.findChild(QLabel, "ValueLbl")
        self.version_badge = self.version_card.findChild(QLabel, "BadgeLbl")
        cards_grid.addWidget(self.version_card, 0, 2)

        layout.addLayout(cards_grid)

        # Bot Controller
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
        self.bot_toggle_btn.clicked.connect(self._toggle_bot)
        bot_header.addWidget(self.bot_toggle_btn)

        bot_layout.addLayout(bot_header)

        bot_desc = QLabel(
            "Khi bật, OmniMind sẽ lắng nghe tin nhắn từ Telegram và thực thi lệnh AI "
            "với đầy đủ Context Injection Engine (Working Principles + Skills + Resources)."
        )
        bot_desc.setObjectName("PageDesc")
        bot_desc.setWordWrap(True)
        bot_layout.addWidget(bot_desc)

        bot_action_row = QHBoxLayout()
        bot_action_row.addStretch()
        self.bot_test_capture_btn = QPushButton("  Test Chụp Màn Hình")
        self.bot_test_capture_btn.setObjectName("SecondaryBtn")
        self.bot_test_capture_btn.setIcon(Icons.eye("#3B82F6", 16))
        self.bot_test_capture_btn.setCursor(Qt.PointingHandCursor)
        self.bot_test_capture_btn.setMinimumWidth(210)
        self.bot_test_capture_btn.setMinimumHeight(38)
        self.bot_test_capture_btn.clicked.connect(self._test_runtime_screen_capture)
        bot_action_row.addWidget(self.bot_test_capture_btn)
        bot_layout.addLayout(bot_action_row)

        layout.addWidget(bot_frame)

        # Update Center
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

        self.update_btn = QPushButton("  Cài Cập Nhật")
        self.update_btn.setObjectName("PrimaryBtn")
        self.update_btn.setIcon(Icons.download("#FFFFFF", 16))
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.setMinimumHeight(36)
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self._on_install_update)
        update_header.addWidget(self.update_btn)
        update_layout.addLayout(update_header)

        self.changelog_text = QLabel("Đang tải changelog mới nhất từ server...")
        self.changelog_text.setObjectName("ChangelogText")
        self.changelog_text.setWordWrap(True)
        self.changelog_text.setTextFormat(Qt.RichText)
        update_layout.addWidget(self.changelog_text)

        self.update_progress = QProgressBar()
        self.update_progress.setRange(0, 100)
        self.update_progress.setValue(0)
        self.update_progress.setVisible(False)
        self.update_progress.setFixedHeight(16)
        update_layout.addWidget(self.update_progress)

        self.update_progress_text = QLabel("")
        self.update_progress_text.setStyleSheet("font-size: 12px; color: #64748B;")
        self.update_progress_text.setWordWrap(True)
        self.update_progress_text.setVisible(False)
        update_layout.addWidget(self.update_progress_text)

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
        lbl.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.5px;"
        )
        card_layout.addWidget(lbl)

        val = QLabel(value)
        val.setObjectName("ValueLbl")
        val.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
        card_layout.addWidget(val)

        badge_lbl = QLabel(badge)
        badge_lbl.setObjectName("BadgeLbl")
        badge_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        badge_lbl.setTextFormat(Qt.RichText)
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
            self.license_badge.setText(info["status"])
        if self.license_extra:
            expiry = info["expires_at"]
            if expiry and expiry != "N/A":
                self.license_extra.setText(f"Hết hạn: {expiry}")
            else:
                self.license_extra.setText("Không giới hạn thời gian")
        if self.version_val:
            self.version_val.setText(f"v{self.current_version}")

    def _load_bot_status(self):
        status = self.dashboard_mgr.get_telegram_bot_status()
        if status.get("enabled") and not status.get("running"):
            self.dashboard_mgr.start_telegram_bot()
            status = self.dashboard_mgr.get_telegram_bot_status()
        enabled = bool(status.get("running", False))
        self._apply_bot_ui(enabled)

    def _apply_bot_ui(self, enabled: bool):
        if self.bot_val:
            self.bot_val.setText("Đang hoạt động" if enabled else "Chờ khởi động")
            self.bot_val.setStyleSheet(
                "font-size: 22px; font-weight: 800; color: #10B981;"
                if enabled
                else "font-size: 22px; font-weight: 800; color: #3B82F6;"
            )
        if self.bot_badge:
            self.bot_badge.setText(
                '<span style="color: #10B981;">●</span> Online'
                if enabled
                else '<span style="color: #94A3B8;">●</span> Offline'
            )
        if self.bot_extra:
            self.bot_extra.setText("Bot runtime sẵn sàng nhận action." if enabled else "Bot đang tắt.")
        if self.bot_toggle_btn:
            self.bot_toggle_btn.setText("  Tắt Bot" if enabled else "  Bật Bot")
            self.bot_toggle_btn.setIcon(Icons.power("#FFFFFF" if not enabled else "#EF4444", 18))
            self.bot_toggle_btn.setObjectName("SecondaryBtn" if enabled else "PrimaryBtn")
            self.bot_toggle_btn.style().unpolish(self.bot_toggle_btn)
            self.bot_toggle_btn.style().polish(self.bot_toggle_btn)

    @staticmethod
    def _extract_missing_permission_names(result: dict) -> str:
        preflight = result.get("preflight", {}) or {}
        missing = preflight.get("missing_permissions", []) or []
        names = sorted({str(item.get("permission", "")).strip() for item in missing if item.get("permission")})
        return ", ".join([n for n in names if n])

    def _run_bot_action(
        self,
        op_name: str,
        action_id: str,
        payload: dict | None = None,
        auto_request_permissions: bool = False,
    ):
        if self._bot_action_worker and self._bot_action_worker.isRunning():
            return

        self._pending_bot_action = op_name
        self.bot_toggle_btn.setEnabled(False)
        self.bot_test_capture_btn.setEnabled(False)

        self._bot_action_worker = BotRuntimeActionWorker(
            self.skill_mgr,
            skill_id="system-bot",
            action_id=action_id,
            payload=payload or {},
            auto_request_permissions=auto_request_permissions,
            parent=self,
        )
        self._bot_action_worker.finished.connect(self._on_bot_action_finished)
        self._bot_action_worker.start()

    def _toggle_bot(self):
        if self._bot_toggle_worker and self._bot_toggle_worker.isRunning():
            return
        current = self.dashboard_mgr.get_telegram_bot_status()
        enable = not bool(current.get("running", False))
        self._pending_bot_enable = enable

        self.bot_toggle_btn.setEnabled(False)
        self.bot_test_capture_btn.setEnabled(False)
        self.bot_toggle_btn.setText("  Đang bật..." if enable else "  Đang tắt...")

        self._bot_toggle_worker = BotToggleWorker(self.dashboard_mgr, enable=enable, parent=self)
        self._bot_toggle_worker.finished.connect(self._on_bot_toggle_finished)
        self._bot_toggle_worker.start()

    def _on_bot_toggle_finished(self, result: dict):
        enable = self._pending_bot_enable
        self._bot_toggle_worker = None
        self.bot_toggle_btn.setEnabled(True)
        self.bot_test_capture_btn.setEnabled(True)

        if not result.get("success"):
            self._load_bot_status()
            QMessageBox.warning(
                self,
                "Điều khiển Bot thất bại",
                result.get("message", "Không thể thay đổi trạng thái Telegram bot."),
            )
            return
        self._apply_bot_ui(enable)

    def _test_runtime_screen_capture(self):
        enabled = bool(self.dashboard_mgr.get_telegram_bot_status().get("running", False))
        if not enabled:
            QMessageBox.information(self, "Bot chưa bật", "Hãy bật Bot trước khi test runtime action.")
            return

        self._run_bot_action(
            "screen_capture_test",
            "screen_capture",
            payload={"subdir": "runtime_tests"},
            auto_request_permissions=True,
        )

    def _on_bot_action_finished(self, result: dict):
        self.bot_toggle_btn.setEnabled(True)
        self.bot_test_capture_btn.setEnabled(True)
        self._bot_action_worker = None

        op = self._pending_bot_action
        self._pending_bot_action = ""

        if op == "screen_capture_test":
            if result.get("success"):
                msg = result.get("message", "Chụp màn hình thành công.")
                artifact = result.get("artifact_path", "")
                if artifact:
                    msg += f"\n\nFile: {artifact}"
                QMessageBox.information(self, "Runtime Test", msg)
                return

            if result.get("code") == "PERMISSION_REQUIRED":
                missing = self._extract_missing_permission_names(result)
                QMessageBox.warning(
                    self,
                    "Thiếu quyền hệ thống",
                    (
                        "Runtime action chưa thể chạy do thiếu quyền.\n"
                        f"Quyền còn thiếu: {missing or 'Không xác định'}"
                    ),
                )
                return

            QMessageBox.warning(self, "Runtime Test thất bại", result.get("message", "Không thể chạy action."))

    def _set_update_progress(self, visible: bool, value: int = 0, message: str = ""):
        self.update_progress.setVisible(visible)
        self.update_progress_text.setVisible(visible)
        if visible:
            self.update_progress.setValue(max(0, min(100, int(value))))
            self.update_progress_text.setText(message)
        else:
            self.update_progress.setValue(0)
            self.update_progress_text.setText("")

    def _render_changelog(self, logs: list):
        if logs:
            log_html = ""
            for log in logs:
                type_tag = f"<b>[{log.get('change_type', 'feat').upper()}]</b>"
                log_html += f"• {type_tag} {log.get('content')}<br>"
            self.changelog_text.setText(log_html)
            return
        self.changelog_text.setText("Không có changelog mới từ server.")

    def _start_update_check(self, silent: bool):
        if self._check_worker and self._check_worker.isRunning():
            return
        if self._update_worker and self._update_worker.isRunning():
            return

        self.check_btn.setEnabled(False)
        self.check_btn.setText("  Đang kiểm tra...")
        self._check_worker = UpdateCheckWorker(self.dashboard_mgr, self.current_version, self)
        self._check_worker.finished.connect(lambda result, s=silent: self._on_update_check_finished(result, s))
        self._check_worker.start()

    def _on_update_check_finished(self, result: dict, silent: bool):
        self.check_btn.setEnabled(True)
        self.check_btn.setText("  Kiểm Tra")
        self._check_worker = None

        if not result.get("success"):
            if not silent:
                QMessageBox.warning(self, "Lỗi", f"Không thể kiểm tra cập nhật: {result.get('message')}")
            return

        self._render_changelog(result.get("changelogs", []))

        if result.get("has_update"):
            new_v = result.get("latest_version")
            self._latest_update_info = dict(result)
            self.update_btn.setVisible(True)
            self.update_btn.setEnabled(bool(result.get("download_url")))
            self.update_btn.setText(f"  Cài v{new_v}")
            self._set_update_progress(False)
            if self.version_badge:
                self.version_badge.setText("<span style='color:#F59E0B;'>●</span> Có bản cập nhật")

            if not silent:
                msg = f"Đã có phiên bản mới: <b>v{new_v}</b> ({result.get('version_name')})."
                if result.get("is_critical"):
                    msg += "<br><span style='color: #EF4444;'>Đây là bản cập nhật quan trọng!</span>"
                QMessageBox.information(self, "Cập Nhật Mới", msg)
            return

        self._latest_update_info = {}
        self.update_btn.setVisible(False)
        if not silent:
            QMessageBox.information(self, "Thông Báo", f"Bạn đang sử dụng phiên bản mới nhất (v{self.current_version}).")

    def _on_check_updates(self):
        self._start_update_check(silent=False)

    def _on_install_update(self):
        if self._update_worker and self._update_worker.isRunning():
            return

        target_version = self._latest_update_info.get("latest_version")
        download_url = (self._latest_update_info.get("download_url") or "").strip()
        if not target_version or not download_url:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Không có link tải bản cập nhật từ server.")
            return

        approved = QMessageBox.question(
            self,
            "Cài đặt cập nhật",
            (
                "OmniMind sẽ tải payload update vào thư mục dữ liệu người dùng và không thay app gốc.\n"
                "Cách này giúp tránh mất quyền đã cấp trên macOS.\n\n"
                "Tiếp tục cài đặt?"
            ),
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )
        if approved != QMessageBox.Ok:
            return

        self.check_btn.setEnabled(False)
        self.update_btn.setEnabled(False)
        self._set_update_progress(True, 5, "Khởi tạo cập nhật...")
        self.update_progress_text.setStyleSheet("font-size: 12px; color: #3B82F6;")

        self._update_worker = UpdateInstallWorker(self.dashboard_mgr, download_url, target_version, self)
        self._update_worker.progress.connect(self._on_update_install_progress)
        self._update_worker.finished.connect(self._on_update_install_finished)
        self._update_worker.start()

    def _on_update_install_progress(self, percent: int, message: str):
        self._set_update_progress(True, percent, message)

    def _on_update_install_finished(self, result: dict):
        self.check_btn.setEnabled(True)
        self.update_btn.setEnabled(True)
        self._update_worker = None

        if not result.get("success"):
            self.update_progress_text.setStyleSheet("font-size: 12px; color: #EF4444;")
            self._set_update_progress(True, 100, result.get("message", "Cài đặt cập nhật thất bại."))
            QMessageBox.warning(self, "Cập nhật thất bại", result.get("message", "Không thể cài đặt update."))
            return

        installed_version = result.get("version", self._latest_update_info.get("latest_version", self.current_version))
        self.current_version = installed_version
        if self.version_val:
            self.version_val.setText(f"v{installed_version}")
        if self.version_badge:
            self.version_badge.setText("<span style='color:#F59E0B;'>●</span> Cần khởi động lại")
        self.update_btn.setVisible(False)
        self.update_progress_text.setStyleSheet("font-size: 12px; color: #10B981;")
        self._set_update_progress(True, 100, "Đã cài update. Khởi động lại ứng dụng để áp dụng.")

        ask_restart = QMessageBox.question(
            self,
            "Cập nhật thành công",
            (
                f"Đã cài đặt bản v{installed_version}.\n"
                "Bạn có muốn khởi động lại ứng dụng ngay bây giờ không?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ask_restart == QMessageBox.Yes:
            self._restart_app()

    def _restart_app(self):
        executable = sys.executable
        args = sys.argv
        started = QProcess.startDetached(executable, args)
        if started:
            QApplication.quit()
        else:
            QMessageBox.warning(
                self,
                "Không thể khởi động lại",
                "Không thể tự động khởi động lại ứng dụng. Vui lòng mở lại OmniMind thủ công.",
            )

    def _add_card_shadow(self, widget):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 12))
        shadow.setOffset(0, 4)
        widget.setGraphicsEffect(shadow)
