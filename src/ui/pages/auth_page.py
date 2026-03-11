"""
OmniMind - Tab 2: Auth & Core Settings Page
Form Token Telegram, Workspace Path, OmniMind Config, Auto-start.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QCheckBox, QFileDialog, QScrollArea, QMessageBox, QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QColor
from ui.icons import Icons
from engine.config_manager import ConfigManager
from engine.environment_manager import EnvironmentManager
from engine.openzca_manager import OpenZcaManager
from engine.permission_manager import PermissionManager
from engine.zalo_connection_monitor import get_global_zalo_connection_monitor
import logging
import time

logger = logging.getLogger(__name__)


class CodexVerifyWorker(QThread):
    """Chạy verify Codex trên thread riêng để không block UI."""
    finished = pyqtSignal(dict)

    def __init__(self, env_manager, parent=None):
        super().__init__(parent)
        self.env_manager = env_manager

    def run(self):
        try:
            result = self.env_manager.verify_codex_auth()
            if not result.get("success"):
                message = (result.get("message") or "").lower()
                if "chưa đăng nhập" in message:
                    login_result = self.env_manager.login_codex()
                    if login_result.get("success"):
                        result = self.env_manager.verify_codex_auth()
                    else:
                        result = login_result
        except Exception as e:
            logger.exception("Codex verify worker failed")
            result = {"success": False, "message": f"Lỗi: {str(e)[:40]}"}
        self.finished.emit(result)


class RuntimeInstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, env_manager, components, install_policy: dict, parent=None):
        super().__init__(parent)
        self.env_manager = env_manager
        if isinstance(components, (list, tuple, set)):
            self.components = [str(c).strip() for c in components if str(c).strip()]
        else:
            comp = str(components).strip()
            self.components = [comp] if comp else []
        self.install_policy = install_policy or {}

    def run(self):
        try:
            if not self.components:
                self.finished.emit({
                    "success": True,
                    "components": [],
                    "status": self.env_manager.check_prerequisites(),
                    "message": "Không có môi trường cần cài đặt.",
                })
                return

            target = ", ".join(self.components)
            self.progress.emit(5, f"Đang chuẩn bị cài đặt: {target}...")
            ok = self.env_manager.install_missing_env(
                self.components,
                self.install_policy,
                progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
            )
            recheck = self.env_manager.check_prerequisites()
            missing_after = [comp for comp in self.components if recheck.get(comp) == "MISSING"]
            success = bool(ok and not missing_after)

            self.finished.emit({
                "success": success,
                "components": list(self.components),
                "status": recheck,
                "missing_after": missing_after,
                "message": (
                    "Cài đặt môi trường thành công."
                    if success
                    else f"Không thể cài đầy đủ: {', '.join(missing_after)}."
                ),
            })
        except Exception as e:
            logger.exception("Runtime install worker failed")
            target = ", ".join(self.components) if self.components else "runtime"
            self.finished.emit({
                "success": False,
                "components": list(self.components),
                "message": f"Lỗi cài đặt {target}: {str(e)[:80]}",
            })


class CodexInstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(dict)

    def __init__(self, env_manager, release_manifest: dict, parent=None):
        super().__init__(parent)
        self.env_manager = env_manager
        self.release_manifest = release_manifest or {}

    def run(self):
        try:
            release_data = self.env_manager.resolve_codex_download_info(self.release_manifest)
            dl_url = (release_data.get("url") or "").strip()
            if not dl_url:
                self.finished.emit({
                    "success": False,
                    "message": (
                        "Server chưa cấu hình gói OmniMind cho thiết bị này "
                        f"({release_data.get('platform', 'unknown')}/{release_data.get('arch', 'unknown')}). "
                        "Vui lòng cập nhật OmniMind CLI Releases trên CMS."
                    ),
                })
                return

            ok = self.env_manager.download_and_install_codex(
                dl_url,
                expected_checksum=(release_data.get("checksum") or ""),
                progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
            )
            fail_msg = (
                getattr(self.env_manager, "last_install_error", "") or
                "Không tải/cài được OmniMind."
            )
            self.finished.emit({
                "success": bool(ok),
                "message": "Cài đặt OmniMind thành công." if ok else fail_msg,
            })
        except Exception as e:
            logger.exception("Codex install worker failed")
            self.finished.emit({"success": False, "message": f"Lỗi cài OmniMind: {str(e)[:80]}"})


class OpenZcaRuntimeWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, manager: OpenZcaManager | None, operation: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.operation = str(operation or "inspect").strip().lower()

    def run(self):
        if self.manager is None:
            self.finished.emit({"success": False, "message": "Không thể khởi tạo OpenZCA Manager."})
            return
        try:
            if self.operation == "install":
                result = self.manager.install_openzca()
            elif self.operation == "repair":
                result = self.manager.repair_openzca()
            else:
                result = self.manager.inspect_runtime()
        except Exception as e:
            logger.exception("OpenZCA runtime worker failed")
            result = {"success": False, "message": f"Lỗi OpenZCA: {str(e)[:120]}"}
        self.finished.emit(result)


class OpenZcaAuthWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, manager: OpenZcaManager | None, operation: str, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.operation = str(operation or "status").strip().lower()

    def run(self):
        if self.manager is None:
            self.finished.emit({"success": False, "message": "Không thể khởi tạo OpenZCA Manager."})
            return
        try:
            if self.operation == "login":
                result = self.manager.run_auth_login()
            elif self.operation == "logout":
                result = self.manager.run_auth_logout()
            else:
                result = self.manager.run_auth_status()
        except Exception as e:
            logger.exception("OpenZCA auth worker failed")
            result = {"success": False, "message": f"Lỗi auth OpenZCA: {str(e)[:120]}"}
        self.finished.emit(result)


class ZaloStatusWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, monitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor

    def run(self):
        if self.monitor is None:
            self.finished.emit({"success": False, "message": "Không thể khởi tạo bộ theo dõi Zalo."})
            return
        try:
            result = self.monitor.refresh_once()
            result = {"success": True, **(result or {})}
        except Exception as e:
            logger.exception("Zalo status worker failed")
            result = {"success": False, "message": f"Lỗi cập nhật Zalo: {str(e)[:120]}"}
        self.finished.emit(result)


class AuthPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._verify_worker = None
        self._runtime_worker = None
        self._codex_install_worker = None
        self._openzca_worker = None
        self._openzca_auth_worker = None
        self._zalo_status_worker = None
        self._pending_openzca_auth_op = ""
        self._last_zalo_auto_refresh_ts = 0.0
        self._missing_runtime = []
        self._runtime_installing = False
        self._codex_installing = False
        self._runtime_installer_ready = False
        self._runtime_installer_info = {}
        self._auto_install_codex_after_runtime = False
        self._pending_codex_manifest = None
        try:
            self.env_manager = EnvironmentManager()
        except Exception as e:
            logger.error(f"EnvironmentManager init failed: {e}")
            self.env_manager = None
        try:
            self.openzca_manager = OpenZcaManager(self.env_manager) if self.env_manager else OpenZcaManager()
        except Exception as e:
            logger.error(f"OpenZcaManager init failed: {e}")
            self.openzca_manager = None
        self.zalo_monitor = get_global_zalo_connection_monitor()
        try:
            self.permission_manager = PermissionManager()
        except Exception as e:
            logger.error(f"PermissionManager init failed: {e}")
            self.permission_manager = None
        self._setup_ui()
        try:
            self._load_settings()
        except Exception as e:
            logger.error(f"Load settings failed: {e}")

    def _setup_ui(self):
        # Wrapper layout chứa ScrollArea để nội dung không bị cắt
        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("ScrollArea")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(24)

        # ── Page Header ──
        header = QWidget()
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)
        title = QLabel("Xác Thực & Cấu Hình")
        title.setObjectName("PageTitle")
        desc = QLabel("Cấu hình Telegram Bot, Workspace, xác thực OmniMind CLI và các tuỳ chọn hệ thống.")
        desc.setObjectName("PageDesc")
        desc.setWordWrap(True)
        h_layout.addWidget(title)
        h_layout.addWidget(desc)
        layout.addWidget(header)

        # ── Save Button (đặt trên cùng để dễ quan sát) ──
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_btn = QPushButton("  Lưu Cấu Hình")
        save_btn.setObjectName("PrimaryBtn")
        save_btn.setIcon(Icons.check_circle("#FFFFFF", 18))
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(46)
        save_btn.setMinimumWidth(180)
        save_btn.clicked.connect(self._save_settings)
        self.save_btn = save_btn
        save_row.addWidget(save_btn)
        layout.addLayout(save_row)

        # ── Telegram Config Card ──
        tg_card = self._create_card("🤖  Telegram Bot")
        tg_layout = tg_card.layout()

        # Bot Token
        tg_layout.addWidget(self._create_field_label("Bot Token"))
        self.token_input = QLineEdit()
        self.token_input.setObjectName("FormInput")
        self.token_input.setPlaceholderText("Dán Bot Token từ @BotFather")
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setFixedHeight(44)
        tg_layout.addWidget(self.token_input)

        tg_layout.addSpacing(4)

        # User ID Telegram
        tg_layout.addWidget(self._create_field_label("User ID Telegram"))
        self.user_id_input = QLineEdit()
        self.user_id_input.setObjectName("FormInput")
        self.user_id_input.setPlaceholderText("ID người dùng Telegram (số)")
        self.user_id_input.setFixedHeight(44)
        tg_layout.addWidget(self.user_id_input)

        layout.addWidget(tg_card)

        # ── Workspace Card ──
        ws_card = self._create_card("📂  Workspace")
        ws_layout = ws_card.layout()

        ws_layout.addWidget(self._create_field_label("Đường dẫn Workspace, nơi AI được phép đọc/ghi file"))
        ws_row = QHBoxLayout()
        ws_row.setSpacing(10)
        self.workspace_input = QLineEdit()
        self.workspace_input.setObjectName("FormInput")
        self.workspace_input.setPlaceholderText(".../your-workspace")
        self.workspace_input.setFixedHeight(44)
        ws_row.addWidget(self.workspace_input)

        browse_btn = QPushButton("  Chọn")
        browse_btn.setObjectName("SecondaryBtn")
        browse_btn.setIcon(Icons.folder("#3B82F6", 16))
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setFixedHeight(44)
        browse_btn.setMinimumWidth(100)
        browse_btn.clicked.connect(self._browse_folder)
        ws_row.addWidget(browse_btn)
        ws_layout.addLayout(ws_row)

        layout.addWidget(ws_card)

        # ── Zalo Connection Card ──
        zalo_card = self._create_card("💬  Kết nối Zalo")
        zalo_layout = zalo_card.layout()

        zalo_status_row = QHBoxLayout()
        zalo_status_icon = QLabel("⚪")
        zalo_status_icon.setFixedWidth(20)
        zalo_status_icon.setStyleSheet("font-size: 14px; background: transparent;")
        self.zalo_runtime_status_icon = zalo_status_icon
        self.zalo_runtime_status_label = QLabel("Chưa kiểm tra môi trường Zalo.")
        self.zalo_runtime_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #94A3B8;")
        zalo_status_row.addWidget(zalo_status_icon)
        zalo_status_row.addWidget(self.zalo_runtime_status_label)
        zalo_status_row.addStretch()

        self.zalo_check_btn = QPushButton("  Kiểm tra môi trường")
        self.zalo_check_btn.setObjectName("SecondaryBtn")
        self.zalo_check_btn.setIcon(Icons.refresh("#3B82F6", 16))
        self.zalo_check_btn.setCursor(Qt.PointingHandCursor)
        self.zalo_check_btn.setFixedHeight(40)
        self.zalo_check_btn.clicked.connect(self._check_openzca_runtime)
        zalo_status_row.addWidget(self.zalo_check_btn)

        self.zalo_install_btn = QPushButton("  Cài môi trường")
        self.zalo_install_btn.setObjectName("PrimaryBtn")
        self.zalo_install_btn.setIcon(Icons.download("#FFFFFF", 16))
        self.zalo_install_btn.setCursor(Qt.PointingHandCursor)
        self.zalo_install_btn.setFixedHeight(40)
        self.zalo_install_btn.clicked.connect(self._install_openzca_runtime)
        zalo_status_row.addWidget(self.zalo_install_btn)

        self.zalo_repair_btn = QPushButton("  Khắc phục môi trường")
        self.zalo_repair_btn.setObjectName("SecondaryBtn")
        self.zalo_repair_btn.setIcon(Icons.refresh("#3B82F6", 16))
        self.zalo_repair_btn.setCursor(Qt.PointingHandCursor)
        self.zalo_repair_btn.setFixedHeight(40)
        self.zalo_repair_btn.clicked.connect(self._repair_openzca_runtime)
        zalo_status_row.addWidget(self.zalo_repair_btn)

        zalo_layout.addLayout(zalo_status_row)

        self.zalo_runtime_hint = QLabel("")
        self.zalo_runtime_hint.setStyleSheet("font-size: 12px; color: #64748B;")
        self.zalo_runtime_hint.setWordWrap(True)
        self.zalo_runtime_hint.setVisible(False)
        zalo_layout.addWidget(self.zalo_runtime_hint)

        self.zalo_runtime_meta = QLabel("")
        self.zalo_runtime_meta.setStyleSheet("font-size: 12px; color: #334155;")
        self.zalo_runtime_meta.setWordWrap(True)
        zalo_layout.addWidget(self.zalo_runtime_meta)

        self.zalo_runtime_paths = QLabel("")
        self.zalo_runtime_paths.setStyleSheet("font-size: 12px; color: #64748B;")
        self.zalo_runtime_paths.setWordWrap(True)
        self.zalo_runtime_paths.setVisible(False)
        zalo_layout.addWidget(self.zalo_runtime_paths)

        self.zalo_runtime_progress = QProgressBar()
        self.zalo_runtime_progress.setRange(0, 100)
        self.zalo_runtime_progress.setValue(0)
        self.zalo_runtime_progress.setVisible(False)
        self.zalo_runtime_progress.setFixedHeight(18)
        zalo_layout.addWidget(self.zalo_runtime_progress)

        self.zalo_runtime_progress_text = QLabel("")
        self.zalo_runtime_progress_text.setStyleSheet("font-size: 12px; color: #64748B;")
        self.zalo_runtime_progress_text.setWordWrap(True)
        self.zalo_runtime_progress_text.setVisible(False)
        zalo_layout.addWidget(self.zalo_runtime_progress_text)

        auth_sep = QFrame()
        auth_sep.setFrameShape(QFrame.HLine)
        auth_sep.setStyleSheet("color: #E2E8F0;")
        zalo_layout.addWidget(auth_sep)

        self.zalo_auth_status_label = QLabel("Trạng thái đăng nhập: Not logged in")
        self.zalo_auth_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #64748B;")
        self.zalo_auth_status_label.setWordWrap(True)
        zalo_layout.addWidget(self.zalo_auth_status_label)

        self.zalo_auth_hint = QLabel("Đăng nhập Zalo để chuẩn bị cho các phase bot listener và auto-reply.")
        self.zalo_auth_hint.setStyleSheet("font-size: 12px; color: #64748B;")
        self.zalo_auth_hint.setWordWrap(True)
        zalo_layout.addWidget(self.zalo_auth_hint)

        self.zalo_auth_meta = QLabel("")
        self.zalo_auth_meta.setStyleSheet("font-size: 12px; color: #334155;")
        self.zalo_auth_meta.setWordWrap(True)
        zalo_layout.addWidget(self.zalo_auth_meta)

        zalo_auth_btn_row = QHBoxLayout()
        self.zalo_refresh_auth_btn = QPushButton("  Cập nhật trạng thái")
        self.zalo_refresh_auth_btn.setObjectName("SecondaryBtn")
        self.zalo_refresh_auth_btn.setIcon(Icons.refresh("#3B82F6", 16))
        self.zalo_refresh_auth_btn.setCursor(Qt.PointingHandCursor)
        self.zalo_refresh_auth_btn.setFixedHeight(40)
        self.zalo_refresh_auth_btn.clicked.connect(self._refresh_zalo_auth_status)
        zalo_auth_btn_row.addWidget(self.zalo_refresh_auth_btn)

        self.zalo_login_btn = QPushButton("  Login Zalo")
        self.zalo_login_btn.setObjectName("PrimaryBtn")
        self.zalo_login_btn.setIcon(Icons.check_circle("#FFFFFF", 16))
        self.zalo_login_btn.setCursor(Qt.PointingHandCursor)
        self.zalo_login_btn.setFixedHeight(40)
        self.zalo_login_btn.clicked.connect(self._login_zalo)
        zalo_auth_btn_row.addWidget(self.zalo_login_btn)

        self.zalo_relogin_btn = QPushButton("  Re-login Zalo")
        self.zalo_relogin_btn.setObjectName("SecondaryBtn")
        self.zalo_relogin_btn.setIcon(Icons.refresh("#3B82F6", 16))
        self.zalo_relogin_btn.setCursor(Qt.PointingHandCursor)
        self.zalo_relogin_btn.setFixedHeight(40)
        self.zalo_relogin_btn.clicked.connect(self._relogin_zalo)
        zalo_auth_btn_row.addWidget(self.zalo_relogin_btn)

        self.zalo_logout_btn = QPushButton("  Logout Zalo")
        self.zalo_logout_btn.setObjectName("SecondaryBtn")
        self.zalo_logout_btn.setIcon(Icons.power("#EF4444", 16))
        self.zalo_logout_btn.setCursor(Qt.PointingHandCursor)
        self.zalo_logout_btn.setFixedHeight(40)
        self.zalo_logout_btn.clicked.connect(self._logout_zalo)
        zalo_auth_btn_row.addWidget(self.zalo_logout_btn)
        zalo_auth_btn_row.addStretch()
        zalo_layout.addLayout(zalo_auth_btn_row)

        layout.addWidget(zalo_card)

        # ── OmniMind CLI Authentication Card ──
        codex_card = self._create_card("🧠  Xác thực OmniMind")
        codex_layout = codex_card.layout()

        # Status indicator
        status_row = QHBoxLayout()
        status_icon = QLabel("🔴")
        status_icon.setFixedWidth(20)
        status_icon.setStyleSheet("font-size: 14px; background: transparent;")
        self.codex_status_label = QLabel("Đang kiểm tra...")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #94A3B8;")
        status_row.addWidget(status_icon)
        status_row.addWidget(self.codex_status_label)
        status_row.addStretch()

        # Nút "Tải bộ não AI" (ẩn mặc định, hiện khi chưa cài OmniMind)
        self.codex_download_btn = QPushButton("  Tải bộ não AI")
        self.codex_download_btn.setObjectName("PrimaryBtn")
        self.codex_download_btn.setIcon(Icons.download("#FFFFFF", 16))
        self.codex_download_btn.setCursor(Qt.PointingHandCursor)
        self.codex_download_btn.setFixedHeight(40)
        self.codex_download_btn.setMinimumWidth(180)
        self.codex_download_btn.clicked.connect(self._download_codex)
        self.codex_download_btn.setVisible(False)
        status_row.addWidget(self.codex_download_btn)

        # Nút "Xác thực tài khoản" (ẩn mặc định, hiện khi đã cài OmniMind)
        self.codex_verify_btn = QPushButton("  Xác thực tài khoản")
        self.codex_verify_btn.setObjectName("PrimaryBtn")
        self.codex_verify_btn.setIcon(Icons.check_circle("#FFFFFF", 16))
        self.codex_verify_btn.setCursor(Qt.PointingHandCursor)
        self.codex_verify_btn.setFixedHeight(40)
        self.codex_verify_btn.setMinimumWidth(180)
        self.codex_verify_btn.clicked.connect(self._verify_codex)
        self.codex_verify_btn.setVisible(False)
        status_row.addWidget(self.codex_verify_btn)

        # Nút "Đăng xuất" (ẩn mặc định, hiện sau khi xác thực thành công)
        self.codex_logout_btn = QPushButton("  Đăng xuất")
        self.codex_logout_btn.setObjectName("SecondaryBtn")
        self.codex_logout_btn.setIcon(Icons.power("#EF4444", 16))
        self.codex_logout_btn.setCursor(Qt.PointingHandCursor)
        self.codex_logout_btn.setFixedHeight(40)
        self.codex_logout_btn.setMinimumWidth(120)
        self.codex_logout_btn.clicked.connect(self._logout_codex)
        self.codex_logout_btn.setVisible(False)
        status_row.addWidget(self.codex_logout_btn)

        codex_layout.addLayout(status_row)
        self.codex_status_icon = status_icon

        codex_layout.addSpacing(4)

        self.codex_hint = QLabel("")
        self.codex_hint.setStyleSheet("font-size: 12px; color: #94A3B8;")
        self.codex_hint.setWordWrap(True)
        codex_layout.addWidget(self.codex_hint)

        self.runtime_missing_box = QFrame()
        self.runtime_missing_box.setStyleSheet(
            "QFrame { background: #F8FAFC; border: none; border-radius: 12px; }"
        )
        runtime_box_layout = QVBoxLayout(self.runtime_missing_box)
        runtime_box_layout.setContentsMargins(12, 10, 12, 10)
        runtime_box_layout.setSpacing(8)
        self.runtime_missing_title = QLabel("Thiếu môi trường cho AI hoạt động")
        self.runtime_missing_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        runtime_box_layout.addWidget(self.runtime_missing_title)
        self.runtime_missing_list_layout = QVBoxLayout()
        self.runtime_missing_list_layout.setSpacing(6)
        runtime_box_layout.addLayout(self.runtime_missing_list_layout)
        self.runtime_missing_box.setVisible(False)
        codex_layout.addWidget(self.runtime_missing_box)

        self.runtime_installer_label = QLabel("")
        self.runtime_installer_label.setStyleSheet("font-size: 12px; color: #64748B;")
        self.runtime_installer_label.setWordWrap(True)
        self.runtime_installer_label.setVisible(False)
        codex_layout.addWidget(self.runtime_installer_label)

        self.codex_progress = QProgressBar()
        self.codex_progress.setRange(0, 100)
        self.codex_progress.setValue(0)
        self.codex_progress.setVisible(False)
        self.codex_progress.setFixedHeight(18)
        codex_layout.addWidget(self.codex_progress)

        self.codex_progress_text = QLabel("")
        self.codex_progress_text.setStyleSheet("font-size: 12px; color: #64748B;")
        self.codex_progress_text.setWordWrap(True)
        self.codex_progress_text.setVisible(False)
        codex_layout.addWidget(self.codex_progress_text)

        layout.addWidget(codex_card)

        # ── OmniMind CLI Config Card ──
        codex_cfg_card = self._create_card("Cấu hình OmniMind")
        codex_cfg_layout = codex_cfg_card.layout()

        codex_cfg_layout.addWidget(self._create_field_label("Model"))
        self.codex_model_combo = QComboBox()
        self.codex_model_combo.setObjectName("FormCombo")
        self.codex_model_combo.setEditable(False)
        self.codex_model_combo.setInsertPolicy(QComboBox.NoInsert)
        self.codex_model_combo.setMaxVisibleItems(8)
        self.codex_model_combo.addItem("gpt-5.3-codex", "gpt-5.3-codex")
        self.codex_model_combo.addItem("gpt-5-codex", "gpt-5-codex")
        self.codex_model_combo.addItem("gpt-5.2-codex", "gpt-5.2-codex")
        self.codex_model_combo.setFixedHeight(44)
        codex_cfg_layout.addWidget(self.codex_model_combo)

        codex_cfg_layout.addSpacing(4)
        codex_cfg_layout.addWidget(self._create_field_label("Sandbox mode"))
        self.codex_sandbox_combo = QComboBox()
        self.codex_sandbox_combo.setObjectName("FormCombo")
        self.codex_sandbox_combo.setIconSize(QSize(16, 16))
        self.codex_sandbox_combo.addItem(
            Icons.lock("#0EA5E9", 16),
            "read-only (chỉ đọc, an toàn cao)",
            "read-only",
        )
        self.codex_sandbox_combo.addItem(
            Icons.edit("#3B82F6", 16),
            "workspace-write (đọc/ghi trong workspace)",
            "workspace-write",
        )
        self.codex_sandbox_combo.addItem(
            Icons.alert("#EF4444", 16),
            "danger-full-access (toàn quyền, rủi ro cao)",
            "danger-full-access",
        )
        self.codex_sandbox_combo.setFixedHeight(44)
        self.codex_sandbox_combo.currentIndexChanged.connect(self._update_codex_policy_warning)
        codex_cfg_layout.addWidget(self.codex_sandbox_combo)

        codex_cfg_layout.addSpacing(4)
        codex_cfg_layout.addWidget(self._create_field_label("Approval policy"))
        self.codex_approval_combo = QComboBox()
        self.codex_approval_combo.setObjectName("FormCombo")
        self.codex_approval_combo.setIconSize(QSize(16, 16))
        self.codex_approval_combo.addItem(
            Icons.shield("#64748B", 16),
            "untrusted (lệnh lạ phải xin phép)",
            "untrusted",
        )
        self.codex_approval_combo.addItem(
            Icons.check_circle("#10B981", 16),
            "on-request (đề xuất khi cần)",
            "on-request",
        )
        self.codex_approval_combo.addItem(
            Icons.alert("#DC2626", 16),
            "never (không hỏi lại)",
            "never",
        )
        self.codex_approval_combo.addItem(
            Icons.refresh("#F59E0B", 16),
            "on-failure (legacy)",
            "on-failure",
        )
        self.codex_approval_combo.setFixedHeight(44)
        self.codex_approval_combo.currentIndexChanged.connect(self._update_codex_policy_warning)
        codex_cfg_layout.addWidget(self.codex_approval_combo)

        self.codex_policy_warning = QLabel("")
        self.codex_policy_warning.setStyleSheet("font-size: 12px; color: #EF4444;")
        self.codex_policy_warning.setWordWrap(True)
        codex_cfg_layout.addWidget(self.codex_policy_warning)

        self.codex_cfg_hint = QLabel("Cấu hình sẽ lưu vào ~/.codex/config.toml và SQLite cục bộ.")
        self.codex_cfg_hint.setStyleSheet("font-size: 12px; color: #64748B;")
        self.codex_cfg_hint.setWordWrap(True)
        codex_cfg_layout.addWidget(self.codex_cfg_hint)

        layout.addWidget(codex_cfg_card)

        # Auto-check khi khởi động
        self._check_codex_installed()
        self._check_openzca_runtime()
        self.zalo_monitor.start()
        QTimer.singleShot(0, self._refresh_zalo_auth_status)
        self._zalo_status_timer = QTimer(self)
        self._zalo_status_timer.setInterval(3000)
        self._zalo_status_timer.timeout.connect(self._tick_zalo_status)
        self._zalo_status_timer.start()
        self._sync_zalo_status_display()

        # ── Security & Preferences Card ──
        sec_card = self._create_card("🛡  Bảo mật & Tuỳ chọn")
        sec_layout = sec_card.layout()

        # Auto-start
        self.auto_start_check = QCheckBox("  Tự khởi động cùng hệ điều hành (System Startup)")
        self.auto_start_check.setObjectName("FormCheck")
        self.auto_start_check.setStyleSheet("font-size: 14px; color: #334155; padding: 8px 0;")
        sec_layout.addWidget(self.auto_start_check)

        sec_layout.addSpacing(8)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E2E8F0;")
        sec_layout.addWidget(sep)

        sec_layout.addSpacing(4)

        # Permissions section
        sec_layout.addWidget(self._create_field_label("Yêu cầu Quyền Hệ Thống"))

        perm_hint = QLabel("Cho phép AI thao tác với các tính năng hệ thống. "
                           "Khi bật, ứng dụng sẽ yêu cầu cấp quyền trên hệ điều hành.")
        perm_hint.setStyleSheet("font-size: 12px; color: #94A3B8; margin-bottom: 4px;")
        perm_hint.setWordWrap(True)
        sec_layout.addWidget(perm_hint)

        self.perm_accessibility = QCheckBox("  ⚡ Quyền Accessibility (AppleScript, phím tắt, điều khiển ứng dụng)")
        self.perm_accessibility.setStyleSheet("font-size: 14px; color: #334155; padding: 6px 0;")
        self.perm_accessibility.toggled.connect(lambda checked: self._request_permission("accessibility", checked))
        sec_layout.addWidget(self.perm_accessibility)

        self.perm_screenshot = QCheckBox("  📸 Quyền chụp màn hình (Screen Capture)")
        self.perm_screenshot.setStyleSheet("font-size: 14px; color: #334155; padding: 6px 0;")
        self.perm_screenshot.toggled.connect(lambda checked: self._request_permission("screenshot", checked))
        sec_layout.addWidget(self.perm_screenshot)

        self.perm_camera = QCheckBox("  📷 Quyền truy cập Camera")
        self.perm_camera.setStyleSheet("font-size: 14px; color: #334155; padding: 6px 0;")
        self.perm_camera.toggled.connect(lambda checked: self._request_permission("camera", checked))
        sec_layout.addWidget(self.perm_camera)

        layout.addWidget(sec_card)

        layout.addSpacing(20)

        scroll.setWidget(scroll_content)
        wrapper.addWidget(scroll)

    def _update_codex_policy_warning(self):
        sandbox_mode = self.codex_sandbox_combo.currentData() or "workspace-write"
        approval_policy = self.codex_approval_combo.currentData() or "on-request"
        if sandbox_mode == "danger-full-access" or approval_policy == "never":
            self.codex_policy_warning.setText(
                "Cảnh báo: cấu hình hiện tại cho quyền rất cao. Chỉ dùng khi bạn kiểm soát hoàn toàn lệnh chạy."
            )
        else:
            self.codex_policy_warning.setText("")

    def _set_codex_combo_value(self, combo: QComboBox, value: str):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
            return
        text = str(value or "").strip()
        if not text:
            return
        combo.addItem(text, text)
        combo.setCurrentIndex(combo.count() - 1)

    @staticmethod
    def _legacy_sandbox_label(mode: str) -> str:
        mapping = {
            "read-only": "🔒 Read-only (Chỉ đọc, an toàn tuyệt đối)",
            "workspace-write": "⚡ Safe (Đọc + Ghi file an toàn)",
            "danger-full-access": "🔓 Full Danger (Toàn quyền, không hạn chế)",
        }
        return mapping.get(mode, mapping["workspace-write"])

    def _load_codex_cli_preferences(self):
        prefs = {
            "model": ConfigManager.get_codex_model(),
            "sandbox_mode": ConfigManager.get_sandbox_mode(),
            "approval_policy": ConfigManager.get_codex_approval_policy(),
            "source": "sqlite",
            "config_path": "",
        }
        if self.env_manager:
            try:
                prefs = self.env_manager.read_codex_cli_preferences()
            except Exception as e:
                logger.warning(f"Cannot load codex config from file: {e}")

        model = str(prefs.get("model", "gpt-5.3-codex")).strip() or "gpt-5.3-codex"
        sandbox_mode = str(prefs.get("sandbox_mode", "workspace-write")).strip()
        approval_policy = str(prefs.get("approval_policy", "on-request")).strip()
        supported_models = {"gpt-5.3-codex", "gpt-5-codex", "gpt-5.2-codex"}
        if model not in supported_models:
            model = "gpt-5.3-codex"

        if sandbox_mode not in {"read-only", "workspace-write", "danger-full-access"}:
            sandbox_mode = "workspace-write"
        if approval_policy not in {"untrusted", "on-request", "never", "on-failure"}:
            approval_policy = "on-request"

        self._set_codex_combo_value(self.codex_model_combo, model)
        self._set_codex_combo_value(self.codex_sandbox_combo, sandbox_mode)
        self._set_codex_combo_value(self.codex_approval_combo, approval_policy)
        self._update_codex_policy_warning()

        # Đồng bộ SQLite để các module khác luôn đọc được cấu hình mới nhất.
        ConfigManager.set_codex_model(model)
        ConfigManager.set_sandbox_mode(sandbox_mode)
        ConfigManager.set_codex_approval_policy(approval_policy)
        ConfigManager.set("sandbox_permission", self._legacy_sandbox_label(sandbox_mode))

        src = prefs.get("source", "sqlite")
        cfg_path = prefs.get("config_path", "")
        if cfg_path:
            self.codex_cfg_hint.setText(
                f"Cấu hình hiện tại sẽ được lưu vào bộ nhớ AI."
            )
        else:
            self.codex_cfg_hint.setText("Cấu hình hiện tại đọc từ SQLite. Khi lưu sẽ ghi cả config.toml.")

    def _create_card(self, title_text):
        card = QFrame()
        card.setObjectName("Card")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 12))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 28)
        card_layout.setSpacing(10)
        t = QLabel(title_text)
        t.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        card_layout.addWidget(t)
        return card

    def _create_field_label(self, text):
        lbl = QLabel(text)
        lbl.setFixedHeight(20)
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #64748B;")
        return lbl

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)

    def _runtime_display_name(self, key: str) -> str:
        mapping = {
            "python": "Python",
            "node": "Node.js",
            "npm": "npm",
        }
        return mapping.get(key, key)

    def _set_progress(self, visible: bool, value: int = 0, message: str = ""):
        self.codex_progress.setVisible(visible)
        self.codex_progress_text.setVisible(visible)
        if visible:
            self.codex_progress.setValue(max(0, min(100, int(value))))
            self.codex_progress_text.setText(message)
        else:
            self.codex_progress.setValue(0)
            self.codex_progress_text.setText("")

    def _set_zalo_runtime_progress(self, visible: bool, message: str = "", busy: bool = False):
        self.zalo_runtime_progress.setVisible(visible)
        self.zalo_runtime_progress_text.setVisible(visible)
        if visible:
            if busy:
                self.zalo_runtime_progress.setRange(0, 0)
            else:
                self.zalo_runtime_progress.setRange(0, 100)
                self.zalo_runtime_progress.setValue(100)
            self.zalo_runtime_progress_text.setText(message)
        else:
            self.zalo_runtime_progress.setRange(0, 100)
            self.zalo_runtime_progress.setValue(0)
            self.zalo_runtime_progress_text.setText("")

    def _set_openzca_actions_enabled(self, enabled: bool):
        self.zalo_check_btn.setEnabled(enabled)
        self.zalo_install_btn.setEnabled(enabled)
        self.zalo_repair_btn.setEnabled(enabled)

    def _set_openzca_auth_actions_enabled(self, enabled: bool):
        self.zalo_refresh_auth_btn.setEnabled(enabled)
        self.zalo_login_btn.setEnabled(enabled)
        self.zalo_relogin_btn.setEnabled(enabled)
        self.zalo_logout_btn.setEnabled(enabled)

    def _has_active_zalo_worker(self) -> bool:
        workers = (
            self._openzca_worker,
            self._openzca_auth_worker,
            self._zalo_status_worker,
        )
        return any(worker and worker.isRunning() for worker in workers)

    def _sync_zalo_button_states(self):
        status = self.zalo_monitor.get_status() if self.zalo_monitor else ConfigManager.get_zalo_connection_status()
        state = str(status.get("login_state") or "not_logged_in")
        runtime_ready = str(status.get("install_status") or "").strip().lower() == "ready"
        busy = self._has_active_zalo_worker()

        self.zalo_check_btn.setEnabled(not busy)
        self.zalo_install_btn.setEnabled(not busy)
        self.zalo_repair_btn.setEnabled(not busy)

        self.zalo_login_btn.setVisible(runtime_ready and state in {"not_logged_in", "re_auth_required"})
        self.zalo_relogin_btn.setVisible(runtime_ready and state in {"connected", "re_auth_required"})
        self.zalo_logout_btn.setVisible(runtime_ready and state == "connected")

        self.zalo_refresh_auth_btn.setEnabled(not busy)
        self.zalo_login_btn.setEnabled(not busy and self.zalo_login_btn.isVisible())
        self.zalo_relogin_btn.setEnabled(not busy and self.zalo_relogin_btn.isVisible())
        self.zalo_logout_btn.setEnabled(not busy and self.zalo_logout_btn.isVisible())

    def _tick_zalo_status(self):
        self._sync_zalo_status_display()
        status = self.zalo_monitor.get_status() if self.zalo_monitor else ConfigManager.get_zalo_connection_status()
        if str(status.get("login_state") or "not_logged_in") != "qr_required":
            return
        if self._has_active_zalo_worker():
            return
        now_ts = time.time()
        if now_ts - self._last_zalo_auto_refresh_ts < 3.0:
            return
        self._last_zalo_auto_refresh_ts = now_ts
        self._run_zalo_status_worker()

    def _run_openzca_worker(self, operation: str):
        if self._has_active_zalo_worker():
            return
        op = str(operation or "inspect").strip().lower()
        status_map = {
            "inspect": ("Đang kiểm tra môi trường Zalo...", "Đang kiểm tra môi trường kết nối Zalo..."),
            "install": ("Đang cài môi trường Zalo...", "Đang chuẩn bị môi trường kết nối Zalo..."),
            "repair": ("Đang khắc phục môi trường Zalo...", "Đang làm sạch và cài lại môi trường kết nối Zalo..."),
        }
        title, progress = status_map.get(op, status_map["inspect"])
        self._set_openzca_actions_enabled(False)
        self._set_openzca_auth_actions_enabled(False)
        self.zalo_runtime_status_icon.setText("🟡")
        self.zalo_runtime_status_label.setText(title)
        self.zalo_runtime_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3B82F6;")
        self._set_zalo_runtime_progress(True, progress, busy=True)
        self._openzca_worker = OpenZcaRuntimeWorker(self.openzca_manager, op, self)
        self._openzca_worker.finished.connect(self._on_openzca_worker_finished)
        self._openzca_worker.start()

    def _check_openzca_runtime(self):
        self._run_openzca_worker("inspect")

    def _install_openzca_runtime(self):
        self._run_openzca_worker("install")

    def _repair_openzca_runtime(self):
        self._run_openzca_worker("repair")

    def _run_openzca_auth_worker(self, operation: str):
        if self._has_active_zalo_worker():
            return
        op = str(operation or "status").strip().lower()
        self._pending_openzca_auth_op = op
        label_map = {
            "status": "Đang refresh trạng thái Zalo...",
            "login": "Đang khởi tạo login Zalo...",
            "logout": "Đang đăng xuất Zalo...",
        }
        self._set_openzca_actions_enabled(False)
        self._set_openzca_auth_actions_enabled(False)
        self.zalo_auth_hint.setText(label_map.get(op, "Đang xử lý Zalo..."))
        self._openzca_auth_worker = OpenZcaAuthWorker(self.openzca_manager, op, self)
        self._openzca_auth_worker.finished.connect(self._on_openzca_auth_finished)
        self._openzca_auth_worker.start()

    def _run_zalo_status_worker(self):
        if self._has_active_zalo_worker():
            return
        self._set_openzca_actions_enabled(False)
        self._set_openzca_auth_actions_enabled(False)
        self.zalo_auth_hint.setText("Đang cập nhật trạng thái kết nối Zalo...")
        self._zalo_status_worker = ZaloStatusWorker(self.zalo_monitor, self)
        self._zalo_status_worker.finished.connect(self._on_zalo_status_worker_finished)
        self._zalo_status_worker.start()

    def _refresh_zalo_auth_status(self):
        self._run_zalo_status_worker()

    def _login_zalo(self):
        runtime = ConfigManager.get_zalo_runtime_config()
        if str(runtime.get("install_status") or "").strip().lower() != "ready":
            QMessageBox.warning(
                self,
                "Zalo chưa sẵn sàng",
                "Môi trường Zalo chưa sẵn sàng. Vui lòng kiểm tra hoặc cài môi trường trước khi đăng nhập.",
            )
            return
        self.zalo_monitor.mark_qr_required()
        self._sync_zalo_status_display()
        self._run_openzca_auth_worker("login")

    def _logout_zalo(self):
        self._run_openzca_auth_worker("logout")

    def _relogin_zalo(self):
        runtime = ConfigManager.get_zalo_runtime_config()
        if str(runtime.get("install_status") or "").strip().lower() != "ready":
            QMessageBox.warning(
                self,
                "Zalo chưa sẵn sàng",
                "Môi trường Zalo chưa sẵn sàng. Vui lòng kiểm tra hoặc cài môi trường trước khi đăng nhập.",
            )
            return
        self.zalo_monitor.mark_qr_required()
        self._sync_zalo_status_display()
        self._run_openzca_auth_worker("login")

    def _apply_openzca_runtime_status(self, result: dict):
        status = str(result.get("install_status") or "").strip().lower()
        success = bool(result.get("success"))
        ready = bool(result.get("openzca_ready"))

        if ready:
            icon = "🟢"
            color = "#10B981"
            message = "Zalo đã sẵn sàng."
        elif status in {"installing"}:
            icon = "🟡"
            color = "#3B82F6"
            message = "Đang chuẩn bị môi trường Zalo..."
        elif status == "missing_node":
            icon = "🔴"
            color = "#EF4444"
            message = "Thiếu Node.js để kết nối Zalo."
        elif status == "missing_npm":
            icon = "🔴"
            color = "#EF4444"
            message = "Thiếu npm để kết nối Zalo."
        elif status in {"error", "broken"} or not success:
            icon = "🔴"
            color = "#EF4444"
            message = "Môi trường Zalo đang gặp lỗi."
        else:
            icon = "⚪"
            color = "#94A3B8"
            message = "Zalo chưa sẵn sàng."

        self.zalo_runtime_status_icon.setText(icon)
        self.zalo_runtime_status_label.setText(message)
        self.zalo_runtime_status_label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {color};")

        node_text = f"Node.js: {result.get('node_version') or ('OK' if result.get('node_ok') else 'Thiếu')}"
        npm_text = f"npm: {result.get('npm_version') or ('OK' if result.get('npm_ok') else 'Thiếu')}"
        self.zalo_runtime_meta.setText(f"{node_text} | {npm_text}")
        self.zalo_runtime_paths.clear()

        install_status = str(result.get("install_status") or "").strip().lower()
        self.zalo_install_btn.setVisible(install_status != "ready")
        self.zalo_repair_btn.setVisible(install_status in {"ready", "broken", "error"})

    def _on_openzca_worker_finished(self, result: dict):
        self._openzca_worker = None
        self._set_zalo_runtime_progress(False)
        self._apply_openzca_runtime_status(result or {})
        self._sync_zalo_status_display()
        self._sync_zalo_button_states()

    @staticmethod
    def _zalo_login_state_display(state: str) -> tuple[str, str]:
        mapping = {
            "not_logged_in": ("Not logged in", "#64748B"),
            "qr_required": ("QR required", "#F59E0B"),
            "connected": ("Connected", "#10B981"),
            "re_auth_required": ("Re-auth required", "#EF4444"),
        }
        return mapping.get(state, ("Not logged in", "#64748B"))

    @staticmethod
    def _sanitize_zalo_message(message: str, fallback: str = "") -> str:
        text = str(message or "").strip()
        if not text:
            return fallback
        replacements = {
            "OpenZCA": "môi trường Zalo",
            "openzca": "môi trường Zalo",
            "runtime OpenZCA": "môi trường Zalo",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def _sync_zalo_status_display(self):
        status = self.zalo_monitor.get_status() if self.zalo_monitor else ConfigManager.get_zalo_connection_status()
        state = str(status.get("login_state") or "not_logged_in")
        state_text, state_color = self._zalo_login_state_display(state)
        self.zalo_auth_status_label.setText(f"Trạng thái đăng nhập: {state_text}")
        self.zalo_auth_status_label.setStyleSheet(
            f"font-size: 14px; font-weight: 600; color: {state_color};"
        )

        hint_map = {
            "not_logged_in": "Chưa có session Zalo usable. Nhấn Login Zalo để bắt đầu.",
            "qr_required": "Đang chờ quét mã QR. Ứng dụng sẽ mở mã QR hoặc lưu ảnh QR để bạn quét.",
            "connected": "Session Zalo đang hoạt động và monitor đang theo dõi định kỳ.",
            "re_auth_required": "Session Zalo không còn hợp lệ. Hãy dùng Re-login Zalo để đăng nhập lại.",
        }
        self.zalo_auth_hint.setText(hint_map.get(state, hint_map["not_logged_in"]))

        meta_lines = [
            f"Self user ID: {status.get('self_user_id') or '-'}",
            f"Last connected: {status.get('last_connected_at') or '-'}",
            f"Last auth ok: {status.get('last_auth_ok_at') or '-'}",
            f"Last heartbeat: {status.get('last_heartbeat_at') or '-'}",
        ]
        qr_path = str(status.get("qr_path") or "").strip()
        if qr_path:
            meta_lines.append(f"QR path: {qr_path}")
        last_error = str(status.get("last_monitor_error") or "").strip()
        if last_error:
            meta_lines.append(f"Monitor error: {self._sanitize_zalo_message(last_error)}")
        self.zalo_auth_meta.setText("\n".join(meta_lines))
        self._sync_zalo_button_states()

    def _on_openzca_auth_finished(self, result: dict):
        op = self._pending_openzca_auth_op
        self._pending_openzca_auth_op = ""
        self._openzca_auth_worker = None
        op_msg = self._sanitize_zalo_message(result.get("message"))

        if result.get("success"):
            if op == "logout":
                ConfigManager.set("zalo_login_state", "not_logged_in")
                ConfigManager.set("zalo_self_user_id", "")
                ConfigManager.set("zalo_last_connected_at", "")
                ConfigManager.set("zalo_last_auth_ok_at", "")
                ConfigManager.set("zalo_last_heartbeat_at", "")
                ConfigManager.set("zalo_last_monitor_error", "")
                ConfigManager.set("zalo_qr_path", "")
                ConfigManager.set("zalo_qr_requested_at", "")
                self.zalo_auth_hint.setText(op_msg or "Đã đăng xuất Zalo.")
            else:
                if result.get("self_user_id") is not None:
                    ConfigManager.set("zalo_self_user_id", str(result.get("self_user_id") or "").strip())
                ConfigManager.set("zalo_qr_path", str(result.get("qr_path") or "").strip())
                self.zalo_auth_hint.setText(op_msg or "Thao tác Zalo thành công.")
        else:
            if op == "logout":
                self.zalo_auth_hint.setText(op_msg or "Đăng xuất Zalo thất bại.")
            else:
                ConfigManager.set("zalo_self_user_id", str(result.get("self_user_id") or "").strip())
                qr_path = str(result.get("qr_path") or "").strip()
                if qr_path:
                    ConfigManager.set("zalo_qr_path", qr_path)
                    self.zalo_auth_hint.setText("Đang chờ bạn quét mã QR Zalo.")
                else:
                    self.zalo_auth_hint.setText(op_msg or "Thao tác Zalo thất bại.")

        self._sync_zalo_status_display()
        if op == "logout" or result.get("success"):
            self._run_zalo_status_worker()
        else:
            self._sync_zalo_button_states()

    def _on_zalo_status_worker_finished(self, result: dict):
        self._zalo_status_worker = None
        if not result.get("success") and result.get("message"):
            self.zalo_auth_hint.setText(self._sanitize_zalo_message(result.get("message")))
        self._sync_zalo_status_display()
        self._sync_zalo_button_states()

    def _refresh_runtime_installer_status(self, runtime_missing: list):
        self._runtime_installer_info = {}
        self._runtime_installer_ready = False

        if not self.env_manager:
            self.runtime_installer_label.setVisible(False)
            return

        info = self.env_manager.get_runtime_installer_status()
        self._runtime_installer_info = info
        self._runtime_installer_ready = bool(info.get("ready"))

        if not runtime_missing:
            # Không cần runtime installer nếu không còn runtime thiếu.
            self.runtime_installer_label.setVisible(False)
            return

        display = info.get("display_name", "Installer")
        msg = info.get("message", "")
        hint = info.get("manual_hint", "")
        if self._runtime_installer_ready:
            text = f"✅ Công cụ cài môi trường cho AI hoạt động tự động: {display} · {msg}"
            color = "#10B981"
        else:
            text = f"❌ Công cụ cài môi trường cho AI hoạt động tự động: {display} · {msg}"
            if hint:
                text += f" Gợi ý: {hint}"
            color = "#EF4444"

        self.runtime_installer_label.setText(text)
        self.runtime_installer_label.setStyleSheet(f"font-size: 12px; color: {color};")
        self.runtime_installer_label.setVisible(True)

    def _show_missing_runtime_actions(self, missing_runtime: list):
        self._missing_runtime = list(missing_runtime or [])
        self._clear_layout(self.runtime_missing_list_layout)
        self._refresh_runtime_installer_status(self._missing_runtime)

        if not self._missing_runtime:
            self.runtime_missing_box.setVisible(False)
            return

        for runtime in self._missing_runtime:
            row = QHBoxLayout()
            row.setSpacing(8)

            left = QLabel(f"- {self._runtime_display_name(runtime)}")
            left.setStyleSheet("font-size: 13px; color: #334155;")
            left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row.addWidget(left)
            row.addStretch()

            btn = QPushButton("Cài đặt")
            btn.setObjectName("SecondaryBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setMinimumWidth(120)
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btn.clicked.connect(lambda _=False, dep=runtime: self._request_runtime_install(dep))
            if self._runtime_installing or self._codex_installing:
                btn.setEnabled(False)
            if not self._runtime_installer_ready:
                btn.setToolTip("Thiếu công cụ cài tự động theo HĐH. Xem hướng dẫn bên dưới.")
            row.addWidget(btn)
            self.runtime_missing_list_layout.addLayout(row)

        self.runtime_missing_box.setVisible(True)

    def _confirm_privileged_action(self, title: str, reason: str) -> bool:
        answer = QMessageBox.question(
            self,
            title,
            reason,
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )
        return answer == QMessageBox.Ok

    def _request_runtime_install(self, component: str):
        if not self.env_manager or self._runtime_installing or self._codex_installing:
            return

        if not self._runtime_installer_ready:
            info = self._runtime_installer_info or {}
            title = info.get("display_name", "Installer")
            hint = info.get("manual_hint", "Vui lòng cài runtime thủ công.")
            QMessageBox.warning(
                self,
                "Không thể cài tự động",
                (
                    f"Thiếu công cụ cài đặt tự động ({title}).\n\n"
                    f"{info.get('message', '')}\n"
                    f"Gợi ý: {hint}"
                ),
            )
            return

        friendly = self._runtime_display_name(component)
        ok = self._confirm_privileged_action(
            f"Cài đặt {friendly}",
            (
                f"Hệ thống cần cài {friendly} để OmniMind hoạt động.\n\n"
                "Tiến trình có thể yêu cầu quyền quản trị (Admin/UAC/Sudo).\n"
                "Nhấn OK để tiếp tục, hoặc Cancel để huỷ."
            ),
        )
        if not ok:
            return

        release_manifest = self.env_manager.fetch_codex_release_manifest()
        install_policy = release_manifest.get("install_policy", {})
        self._auto_install_codex_after_runtime = False
        self._pending_codex_manifest = None
        self._start_runtime_install(
            [component],
            install_policy,
            f"Đang cài đặt {friendly}...",
            f"Khởi tạo cài đặt {friendly}...",
        )

    def _start_runtime_install(self, components: list, install_policy: dict, status_text: str, progress_text: str):
        if not components:
            return
        self._runtime_installing = True
        self.codex_download_btn.setEnabled(False)
        self.codex_verify_btn.setEnabled(False)
        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText(status_text)
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3B82F6;")
        self._set_progress(True, 5, progress_text)
        self._show_missing_runtime_actions(self._missing_runtime)

        self._runtime_worker = RuntimeInstallWorker(self.env_manager, components, install_policy, self)
        self._runtime_worker.progress.connect(self._on_runtime_progress)
        self._runtime_worker.finished.connect(self._on_runtime_finished)
        self._runtime_worker.start()

    def _start_codex_install(self, release_manifest: dict, runtime_missing: list):
        if not self.env_manager or self._codex_installing:
            return
        self._codex_installing = True
        self.codex_download_btn.setEnabled(False)
        self.codex_download_btn.setText("  Đang tải...")
        self.codex_verify_btn.setEnabled(False)
        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText("Đang tải và cài đặt OmniMind...")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3B82F6;")
        self.codex_hint.setText("Đang xử lý. Bạn có thể theo dõi tiến trình bên dưới.")
        self._set_progress(True, 5, "Khởi tạo cài đặt OmniMind...")
        self._show_missing_runtime_actions(runtime_missing)

        self._codex_install_worker = CodexInstallWorker(self.env_manager, release_manifest, self)
        self._codex_install_worker.progress.connect(self._on_codex_install_progress)
        self._codex_install_worker.finished.connect(self._on_codex_install_finished)
        self._codex_install_worker.start()

    def _on_runtime_progress(self, percent: int, message: str):
        self._set_progress(True, percent, message)

    def _on_runtime_finished(self, result: dict):
        self._runtime_installing = False
        self._runtime_worker = None
        self.codex_download_btn.setEnabled(True)
        self.codex_verify_btn.setEnabled(True)

        env_status = result.get("status") or (self.env_manager.check_prerequisites() if self.env_manager else {})
        missing_runtime = [k for k in ("python", "node", "npm") if env_status.get(k) == "MISSING"]
        self._show_missing_runtime_actions(missing_runtime)

        if result.get("success"):
            self.codex_status_icon.setText("🟡")
            self.codex_status_label.setText(result.get("message", "Cài đặt môi trường thành công."))
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
            if self._auto_install_codex_after_runtime and not missing_runtime:
                self._auto_install_codex_after_runtime = False
                codex_ready = env_status.get("codex_ready", env_status.get("codex") == "OK")
                if codex_ready:
                    self._set_progress(True, 100, "Runtime đã đầy đủ. OmniMind đã được cài.")
                    self._pending_codex_manifest = None
                    self._check_codex_installed()
                    return
                manifest = self._pending_codex_manifest or self.env_manager.fetch_codex_release_manifest()
                self._pending_codex_manifest = None
                self._start_codex_install(manifest, missing_runtime)
                return
            self._set_progress(True, 100, "Đã hoàn tất. Bạn có thể tiếp tục tải OmniMind.")
        else:
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText(result.get("message", "Cài đặt môi trường thất bại."))
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self._set_progress(True, 100, "Tiến trình dừng do lỗi. Vui lòng thử lại.")
            self._auto_install_codex_after_runtime = False
            self._pending_codex_manifest = None

        self._check_codex_installed()

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn Workspace")
        if folder:
            self.workspace_input.setText(folder)

    def _detect_system_permission_states(self) -> dict:
        if self.permission_manager:
            return self.permission_manager.get_status()
        return {"accessibility": None, "screenshot": None, "camera": None}

    def _load_settings(self):
        """Load cấu hình từ Database lên UI."""
        token = ConfigManager.get("telegram_token", "")
        chat_id = ConfigManager.get("telegram_chat_id", "")
        workspace = ConfigManager.get("workspace_path", "")
        
        # Load Checkboxes
        auto_start = ConfigManager.get("auto_start", "False") == "True"
        perm_acc = ConfigManager.get("perm_accessibility", "False") == "True"
        perm_scr = ConfigManager.get("perm_screenshot", "False") == "True"
        perm_cam = ConfigManager.get("perm_camera", "False") == "True"

        # Đồng bộ theo trạng thái thực tế từ hệ điều hành khi có thể.
        os_perm = self._detect_system_permission_states()
        if os_perm.get("accessibility") is not None:
            perm_acc = bool(os_perm["accessibility"])
        if os_perm.get("screenshot") is not None:
            perm_scr = bool(os_perm["screenshot"])
        if os_perm.get("camera") is not None:
            perm_cam = bool(os_perm["camera"])

        self.token_input.setText(token)
        self.user_id_input.setText(chat_id)
        self.workspace_input.setText(workspace)
        self._load_codex_cli_preferences()
            
        self.auto_start_check.setChecked(auto_start)
        # Tạm tắt signal để không trigger việc yêu cầu quyền khi vừa mở UI
        self.perm_accessibility.blockSignals(True)
        self.perm_screenshot.blockSignals(True)
        self.perm_camera.blockSignals(True)
        
        self.perm_accessibility.setChecked(perm_acc)
        self.perm_screenshot.setChecked(perm_scr)
        self.perm_camera.setChecked(perm_cam)
        
        self.perm_accessibility.blockSignals(False)
        self.perm_screenshot.blockSignals(False)
        self.perm_camera.blockSignals(False)

        # Persist lại trạng thái quyền sau khi sync từ OS để các màn hình khác đọc nhất quán.
        ConfigManager.set("perm_accessibility", str(self.perm_accessibility.isChecked()))
        ConfigManager.set("perm_screenshot", str(self.perm_screenshot.isChecked()))
        ConfigManager.set("perm_camera", str(self.perm_camera.isChecked()))

    def _save_settings(self):
        """Lưu cấu hình từ UI xuống Database."""
        token = self.token_input.text().strip()
        chat_id = self.user_id_input.text().strip()
        workspace = self.workspace_input.text().strip()
        model = self.codex_model_combo.currentText().strip() or "gpt-5.3-codex"
        sandbox_mode = self.codex_sandbox_combo.currentData() or "workspace-write"
        approval_policy = self.codex_approval_combo.currentData() or "on-request"

        auto_start = str(self.auto_start_check.isChecked())
        perm_acc = str(self.perm_accessibility.isChecked())
        perm_scr = str(self.perm_screenshot.isChecked())
        perm_cam = str(self.perm_camera.isChecked())

        ConfigManager.set("telegram_token", token)
        ConfigManager.set("telegram_chat_id", chat_id)
        ConfigManager.set("workspace_path", workspace)
        ConfigManager.set_codex_model(model)
        ConfigManager.set_sandbox_mode(sandbox_mode)
        ConfigManager.set_codex_approval_policy(approval_policy)
        # Legacy key để tránh ảnh hưởng các phiên bản runtime cũ.
        ConfigManager.set("sandbox_permission", self._legacy_sandbox_label(sandbox_mode))
        ConfigManager.set("auto_start", auto_start)
        ConfigManager.set("perm_accessibility", perm_acc)
        ConfigManager.set("perm_screenshot", perm_scr)
        ConfigManager.set("perm_camera", perm_cam)

        if self.env_manager:
            write_result = self.env_manager.write_codex_cli_preferences(
                model=model,
                sandbox_mode=sandbox_mode,
                approval_policy=approval_policy,
            )
            if write_result.get("success"):
                self.codex_cfg_hint.setStyleSheet("font-size: 12px; color: #10B981;")
                self.codex_cfg_hint.setText(
                    f"Đã lưu cấu hình OmniMind: {write_result.get('config_path', '~/.codex/config.toml')}"
                )
            else:
                self.codex_cfg_hint.setStyleSheet("font-size: 12px; color: #EF4444;")
                self.codex_cfg_hint.setText(write_result.get("message", "Không thể ghi config.toml"))
                QMessageBox.warning(
                    self,
                    "Lưu cấu hình OmniMind",
                    write_result.get("message", "Không thể ghi ~/.codex/config.toml"),
                )

        # Trigger hệ thống Auto Start
        self._toggle_auto_start(self.auto_start_check.isChecked())

        logger.info("Settings saved successfully.")

        # Hiệu ứng lưu thành công trên nút
        self.save_btn.setText("  Đã Lưu ✅")
        self.save_btn.setEnabled(False)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(2000, self._reset_save_btn)

    def _reset_save_btn(self):
        """Reset nút Save về trạng thái ban đầu."""
        self.save_btn.setText("  Lưu Cấu Hình")
        self.save_btn.setEnabled(True)

    def _check_codex_installed(self):
        """Tự động kiểm tra môi trường và OmniMind khi khởi động."""
        if self.env_manager is None:
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText("Lỗi khởi tạo Environment Manager")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_hint.setText("Không thể kiểm tra môi trường. Vui lòng khởi động lại ứng dụng.")
            self._show_missing_runtime_actions([])
            return
        try:
            env_status = self.env_manager.check_prerequisites()
        except Exception as e:
            logger.error(f"check_prerequisites failed: {e}")
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText("Lỗi kiểm tra môi trường")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_hint.setText(f"Chi tiết lỗi: {str(e)[:60]}")
            self._show_missing_runtime_actions([])
            return

        codex_ready = env_status.get("codex_ready", env_status.get("codex") == "OK")
        runtime_missing = [k for k in ("python", "node", "npm") if env_status.get(k) == "MISSING"]
        self._show_missing_runtime_actions(runtime_missing)

        if codex_ready:
            # Kiểm tra xem trước đó đã xác thực chưa
            auth_status = ConfigManager.get("codex_auth_status", "unverified")
            runtime_warn = ""
            if runtime_missing:
                runtime_warn = (
                    f" Thiếu môi trường cho AI hoạt động: {', '.join(runtime_missing)}."
                    " Một số tính năng Bot có thể không hoạt động cho tới khi cài bổ sung."
                )
            
            if auth_status == "verified":
                self.codex_status_icon.setText("🟢")
                self.codex_status_label.setText("Đã kết nối") # Sẽ cập nhật version khi live check hoàn tất
                self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #10B981;")
                self.codex_verify_btn.setText("  Đã xác thực")
                self.codex_verify_btn.setObjectName("InstalledBtn")
                self.codex_verify_btn.setIcon(Icons.check_circle("#10B981", 16))
                self.codex_verify_btn.setVisible(True)
                self.codex_logout_btn.setVisible(True)
                self.codex_download_btn.setVisible(False)
                self.codex_hint.setText(f"Hệ thống đã sẵn sàng sử dụng.{runtime_warn}")
                # Chạy Live Check ngầm để lấy version thực tế
                self._verify_codex()
            else:
                self.codex_status_icon.setText("🟡")
                self.codex_status_label.setText("Đã cài đặt · Chưa xác thực")
                self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
                self.codex_verify_btn.setVisible(True)
                self.codex_download_btn.setVisible(False)
                self.codex_hint.setText(
                    "OmniMind đã sẵn sàng. Nhấn xác thực để kiểm tra tài khoản."
                    f"{runtime_warn}"
                )
        else:
            # Thiếu → hiện nút Tải
            self.codex_status_icon.setText("🔴")
            missing = [k for k in ("python", "node", "npm", "codex") if env_status.get(k) == "MISSING"]
            if missing:
                name_map = {"python": "Python", "node": "Node.js", "npm": "npm", "codex": "OmniMind CLI"}
                pretty_missing = ", ".join(name_map.get(x, x) for x in missing)
                self.codex_status_label.setText(f"Thiếu môi trường: {pretty_missing}")
            else:
                self.codex_status_label.setText("Chưa cài đặt OmniMind")
                
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_download_btn.setVisible(True)
            self.codex_verify_btn.setVisible(False)

            if runtime_missing:
                hint_txt = (
                    "Nhấn \"Tải bộ não AI\" để hệ thống tự động cài môi trường còn thiếu (Python/Node/npm),"
                    " sau đó tải OmniMind."
                )
            else:
                hint_txt = (
                    "Môi trường cho AI hoạt động đã đủ. Nhấn \"Tải bộ não AI\" để bắt đầu tải và cài OmniMind."
                )
            self.codex_hint.setText(hint_txt)

        if not self._runtime_installing and not self._codex_installing:
            self._set_progress(False)

    def _download_codex(self):
        """Ưu tiên cài OmniMind trước; runtime thiếu được coi là thành phần bổ sung."""
        if not self.env_manager or self._runtime_installing or self._codex_installing:
            return

        try:
            env_status = self.env_manager.check_prerequisites()
        except Exception as e:
            self._on_download_failed(f"Lỗi kiểm tra môi trường: {str(e)[:80]}")
            return

        runtime_missing = [k for k in ("python", "node", "npm") if env_status.get(k) == "MISSING"]
        codex_ready = env_status.get("codex_ready", env_status.get("codex") == "OK")
        self._show_missing_runtime_actions(runtime_missing)

        if runtime_missing:
            missing_text = ", ".join(self._runtime_display_name(k) for k in runtime_missing)
            self.codex_hint.setText(
                f"Đang thiếu môi trường cho AI hoạt động: {missing_text}. OmniMind vẫn sẽ được cài trước; bạn có thể cài bổ sung sau."
            )

        if codex_ready:
            self.codex_status_icon.setText("🟢")
            self.codex_status_label.setText("OmniMind đã được cài đặt")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #10B981;")
            if runtime_missing:
                missing_text = ", ".join(self._runtime_display_name(k) for k in runtime_missing)
                self.codex_hint.setText(
                    f"OmniMind đã có sẵn. Môi trường bổ sung còn thiếu: {missing_text}. "
                    "Bạn có thể cài sau bằng các nút bên dưới."
                )
            else:
                self.codex_hint.setText("OmniMind đã có sẵn. Bạn có thể nhấn xác thực tài khoản.")
            self.codex_download_btn.setVisible(False)
            self.codex_verify_btn.setVisible(True)
            self._set_progress(False)
            return

        ok = self._confirm_privileged_action(
            "Tải bộ não AI (OmniMind)",
            (
                "Ứng dụng sẽ tải và cài OmniMind vào máy.\n\n"
                "OmniMind được ưu tiên cài trước. Cần phần mềm bổ sung sẽ cài sau nếu cần.\n"
                "Tiến trình có thể yêu cầu quyền hệ thống trên một số môi trường.\n"
                "Nhấn OK để tiếp tục hoặc Cancel để dừng."
            ),
        )
        if not ok:
            return

        release_manifest = self.env_manager.fetch_codex_release_manifest()
        self._start_codex_install(release_manifest, runtime_missing)

    def _on_codex_install_progress(self, percent: int, message: str):
        self._set_progress(True, percent, message)

    def _on_codex_install_finished(self, result: dict):
        self._codex_installing = False
        self._codex_install_worker = None
        if result.get("success"):
            self._on_download_complete()
        else:
            self._on_download_failed(result.get("message", "Không tải/cài được OmniMind."))

    def _on_download_complete(self):
        """Callback sau khi tải OmniMind xong."""
        try:
            env_status = self.env_manager.check_prerequisites() if self.env_manager else {}
        except Exception:
            env_status = {}
        runtime_missing = [k for k in ("python", "node", "npm") if env_status.get(k) == "MISSING"]
        self._show_missing_runtime_actions(runtime_missing)

        self._set_progress(True, 100, "Cài đặt OmniMind hoàn tất.")
        self.codex_download_btn.setEnabled(True)
        self.codex_download_btn.setText("  Tải bộ não AI")
        self.codex_download_btn.setVisible(False)
        self.codex_verify_btn.setEnabled(True)
        self.codex_verify_btn.setVisible(True)
        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText("Đã cài đặt · Chưa xác thực")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
        if runtime_missing:
            missing_text = ", ".join(self._runtime_display_name(k) for k in runtime_missing)
            self.codex_hint.setText(
                f"Cài đặt OmniMind thành công. Môi trường bổ sung còn thiếu: {missing_text}. "
                "Bạn có thể cài sau bằng các nút bên dưới."
            )
        else:
            self.codex_hint.setText("Cài đặt thành công! Nhấn xác thực để đăng nhập tài khoản OmniMind.")

    def _on_download_failed(self, msg: str):
        """Reset UI đúng trạng thái khi tải/cài OmniMind lỗi."""
        self._set_progress(True, 100, "Tiến trình dừng do lỗi.")
        self.codex_download_btn.setEnabled(True)
        self.codex_download_btn.setText("  Tải bộ não AI")
        self.codex_verify_btn.setEnabled(True)
        self.codex_status_icon.setText("🔴")
        self.codex_status_label.setText(msg)
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
        self.codex_hint.setText("Không thể hoàn tất cài đặt OmniMind. Vui lòng kiểm tra mạng/quyền hệ thống và thử lại.")

        try:
            env_status = self.env_manager.check_prerequisites() if self.env_manager else {}
        except Exception:
            env_status = {}

        runtime_missing = [k for k in ("python", "node", "npm") if env_status.get(k) == "MISSING"]
        self._show_missing_runtime_actions(runtime_missing)
        codex_ready = env_status.get("codex_ready", env_status.get("codex") == "OK")
        self.codex_download_btn.setVisible(not codex_ready)
        self.codex_verify_btn.setVisible(codex_ready)

    def _verify_codex(self):
        """Kiểm tra xác thực OmniMind sử dụng EnvironmentManager."""
        if self.env_manager is None:
            logger.error("AuthPage: env_manager is None during _verify_codex")
            self._set_codex_error("Cấu trúc môi trường lỗi")
            return
        if self._verify_worker and self._verify_worker.isRunning():
            return

        logger.info("Starting OmniMind verification...")
        self.codex_verify_btn.setEnabled(False)
        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText("Đang xác thực tài khoản OmniMind...")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3B82F6;")
        self.codex_hint.setText("Đang kiểm tra trạng thái đăng nhập, vui lòng chờ.")

        self._verify_worker = CodexVerifyWorker(self.env_manager, self)
        self._verify_worker.finished.connect(self._on_verify_finished)
        self._verify_worker.start()

    def _on_verify_finished(self, result: dict):
        logger.info(f"OmniMind verify result: {result}")
        self.codex_verify_btn.setEnabled(True)
        self._verify_worker = None

        if result.get("success"):
            self._on_verify_success(result.get("version", "v1.0.0"))
        else:
            self._set_codex_error(result.get("message", "Xác thực thất bại"))

    def _on_verify_success(self, version):
        """Callback khi xác thực thành công."""
        self.codex_status_icon.setText("🟢")
        self.codex_status_label.setText(f"Đã kết nối · {version}")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #10B981;")
        
        self.codex_verify_btn.setText("  Đã xác thực")
        self.codex_verify_btn.setObjectName("InstalledBtn")
        self.codex_verify_btn.setIcon(Icons.check_circle("#10B981", 16))
        self.codex_verify_btn.style().unpolish(self.codex_verify_btn)
        self.codex_verify_btn.style().polish(self.codex_verify_btn)
        
        self.codex_verify_btn.setVisible(True)
        self.codex_logout_btn.setVisible(True)
        self.codex_hint.setText("OmniMind đã xác thực thành công. Sẵn sàng sử dụng.")
        
        # Lưu trạng thái vào Database
        ConfigManager.set("codex_auth_status", "verified")

    def _set_codex_error(self, msg):
        msg = self._friendly_codex_auth_error(msg)
        self.codex_status_icon.setText("🔴")
        self.codex_status_label.setText(msg)
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
        self.codex_verify_btn.setText("  Xác thực tài khoản")
        self.codex_verify_btn.setObjectName("PrimaryBtn")
        self.codex_verify_btn.setIcon(Icons.check_circle("#FFFFFF", 16))
        self.codex_verify_btn.style().unpolish(self.codex_verify_btn)
        self.codex_verify_btn.style().polish(self.codex_verify_btn)
        self.codex_logout_btn.setVisible(False)
        self.codex_hint.setText("Chưa đăng nhập hoặc phiên đăng nhập đã hết hạn. Vui lòng xác thực lại.")
        try:
            env_status = self.env_manager.check_prerequisites() if self.env_manager else {}
        except Exception:
            env_status = {}
        runtime_missing = [k for k in ("python", "node", "npm") if env_status.get(k) == "MISSING"]
        self._show_missing_runtime_actions(runtime_missing)
        codex_ready = env_status.get("codex_ready", env_status.get("codex") == "OK")
        self.codex_verify_btn.setVisible(codex_ready)
        self.codex_download_btn.setVisible(not codex_ready)
        self.codex_download_btn.setEnabled(True)
        self.codex_download_btn.setText("  Tải bộ não AI")
        ConfigManager.set("codex_auth_status", "unverified")

    def _friendly_codex_auth_error(self, msg: str) -> str:
        """
        Chuẩn hóa lỗi auth hiển thị trên UI để tránh lộ log kỹ thuật dài.
        """
        text = str(msg or "").strip()
        if not text:
            return "Xác thực không thành công. Vui lòng thử lại."

        lower = text.lower()
        noisy_tokens = (
            "oauth/authorize",
            "starting local login server",
            "if your browser did not open",
            "on a remote or headless machine",
            "http://localhost",
        )
        if any(token in lower for token in noisy_tokens):
            return (
                "Xác thực không thành công hoặc đã bị hủy. "
                "Vui lòng nhấn xác thực lại và hoàn tất đăng nhập trên trình duyệt."
            )

        if len(text) > 160:
            return "Xác thực không thành công. Vui lòng thử lại."
        return text

    def _logout_codex(self):
        """Xóa trạng thái xác thực trong CLI và Database."""
        if not self.env_manager:
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText("Lỗi môi trường, không thể đăng xuất")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_logout_btn.setVisible(True)
            return

        result = self.env_manager.logout_codex()
        if not result.get("success"):
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText(result.get("message", "Đăng xuất thất bại"))
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_logout_btn.setVisible(True)
            self.codex_hint.setText("Không thể đăng xuất OmniMind. Vui lòng thử lại.")
            return

        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText("Đã cài đặt · Chưa xác thực")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
        
        self.codex_verify_btn.setText("  Xác thực tài khoản")
        self.codex_verify_btn.setObjectName("PrimaryBtn")
        self.codex_verify_btn.setIcon(Icons.check_circle("#FFFFFF", 16))
        self.codex_verify_btn.style().unpolish(self.codex_verify_btn)
        self.codex_verify_btn.style().polish(self.codex_verify_btn)
        
        self.codex_logout_btn.setVisible(False)
        self.codex_hint.setText("Đã đăng xuất. Nhấn xác thực để đăng nhập lại bằng tài khoản khác.")
        
        # Xóa trạng thái trong Database
        ConfigManager.set("codex_auth_status", "unverified")

    def _request_permission(self, perm_type, checked):
        """Yêu cầu quyền hệ thống tuỳ theo OS (macOS / Windows)."""
        if not checked:
            return  # Bỏ check thì không cần request

        import platform
        sys_name = platform.system()
        app_display_name = (
            self.permission_manager.get_app_display_name()
            if self.permission_manager
            else "OmniMind"
        )

        identity_note = (
            f"Lưu ý: macOS sẽ hiển thị ứng dụng dưới tên \"{app_display_name}\" trong danh sách quyền.\n"
            "Sau khi cấp quyền, hãy tắt/mở lại ứng dụng."
        )

        reason_map = {
            "accessibility": (
                "Quyền Accessibility cho phép AI điều khiển bàn phím/chuột và thao tác ứng dụng khi được yêu cầu."
            ),
            "screenshot": (
                "Quyền chụp màn hình cho phép AI đọc nội dung màn hình để phân tích và hỗ trợ xử lý lỗi."
            ),
            "camera": (
                "Quyền Camera cho phép AI truy cập webcam khi bạn bật các tác vụ cần hình ảnh trực tiếp."
            ),
        }
        reason = reason_map.get(perm_type, "Ứng dụng cần quyền hệ thống để thực hiện tính năng này.")
        approved = self._confirm_privileged_action(
            "Yêu cầu quyền hệ thống",
            f"{reason}\n\nNhấn OK để mở màn hình cấp quyền, hoặc Cancel để huỷ.",
        )
        if not approved:
            widget_map = {
                "accessibility": self.perm_accessibility,
                "screenshot": self.perm_screenshot,
                "camera": self.perm_camera,
            }
            w = widget_map.get(perm_type)
            if w:
                w.blockSignals(True)
                w.setChecked(False)
                w.blockSignals(False)
            return

        req_result = (
            self.permission_manager.request(perm_type)
            if self.permission_manager
            else {"success": False, "open_mode": "failed"}
        )
        open_mode = req_result.get("open_mode", "failed")
        prompted = bool(req_result.get("prompted", False))

        if sys_name == "Darwin":  # macOS
            if open_mode == "anchor":
                QMessageBox.information(
                    self,
                    "Mở màn hình cấp quyền",
                    (
                        "Đã mở màn hình quyền hệ thống.\n"
                        f"Hãy bật quyền cho \"{app_display_name}\" rồi quay lại ứng dụng.\n\n"
                        f"{identity_note}"
                        + (
                            "\n\nLưu ý: macOS chỉ hiển thị app trong danh sách sau khi app đã gọi prompt native thành công."
                            if not prompted
                            else ""
                        )
                    ),
                )
            elif open_mode == "settings":
                QMessageBox.information(
                    self,
                    "Mở System Settings",
                    (
                        "Đã mở System Settings, nhưng không nhảy đúng trang quyền tự động.\n"
                        "Vui lòng tự vào đúng mục quyền tương ứng để bật cho ứng dụng.\n\n"
                        f"{identity_note}"
                        + (
                            "\n\nNếu chưa thấy tên app, hãy dùng bản build mới và nhấn yêu cầu quyền lại."
                            if not prompted
                            else ""
                        )
                    ),
                )
            else:
                QMessageBox.warning(
                    self,
                    "Không thể mở màn hình quyền",
                    (
                        "Không thể mở màn hình cấp quyền tự động. Vui lòng mở System Settings thủ công.\n\n"
                        f"{identity_note}"
                    ),
                )

        elif sys_name == "Windows":
            if open_mode != "failed":
                QMessageBox.information(
                    self,
                    "Mở màn hình cấp quyền",
                    (
                        "Đã mở phần Settings tương ứng.\n"
                        "Trên Windows, ứng dụng desktop thường không hiện danh sách theo từng app như macOS.\n"
                        "Bạn cần bật quyền camera/microphone cho Desktop Apps (nếu có), rồi mở lại OmniMind."
                    ),
                )
            else:
                QMessageBox.warning(
                    self,
                    "Không thể mở Settings",
                    "Không thể mở màn hình quyền tự động. Vui lòng mở Settings thủ công.",
                )
        else:
            QMessageBox.information(
                self, "Quyền Hệ Thống",
                f"Hệ điều hành {sys_name} chưa được hỗ trợ cấp quyền tự động.\n"
                "Vui lòng cấu hình thủ công.",
            )

        # Đồng bộ lại checkbox theo trạng thái thật của OS (nếu probe được),
        # tránh trạng thái UI "đã cấp" nhưng hệ thống chưa cấp quyền.
        self._sync_permission_checkbox_after_request(perm_type, open_mode)

    def _sync_permission_checkbox_after_request(self, perm_type: str, open_mode: str):
        if not self.permission_manager:
            return
        widget_map = {
            "accessibility": self.perm_accessibility,
            "screenshot": self.perm_screenshot,
            "camera": self.perm_camera,
        }
        cfg_key_map = {
            "accessibility": "perm_accessibility",
            "screenshot": "perm_screenshot",
            "camera": "perm_camera",
        }
        w = widget_map.get(perm_type)
        cfg_key = cfg_key_map.get(perm_type)
        if not w or not cfg_key:
            return

        state = self.permission_manager.get_permission_state(perm_type)
        # Probe được granted -> giữ checked.
        if state is True:
            w.blockSignals(True)
            w.setChecked(True)
            w.blockSignals(False)
            ConfigManager.set(cfg_key, "True")
            return

        # Chỉ rollback checkbox khi mở settings thất bại, hoặc state đã xác định là denied.
        if open_mode == "failed" or state is False:
            w.blockSignals(True)
            w.setChecked(False)
            w.blockSignals(False)
            ConfigManager.set(cfg_key, "False")

    def _toggle_auto_start(self, is_enabled: bool):
        """Xử lý Logic tự khởi động cùng OS"""
        import platform, os
        sys_name = platform.system()
        
        if sys_name == "Darwin":
            import textwrap
            from pathlib import Path
            plist_path = Path(os.path.expanduser("~/Library/LaunchAgents/com.antigravity.omnimind.plist"))
            
            if is_enabled:
                # Tạo LaunchAgent
                app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../main.py"))
                # Note: Nếu pack qua PyInstaller, chỗ này cần trỏ tới file executable
                plist_content = textwrap.dedent(f"""\
                    <?xml version="1.0" encoding="UTF-8"?>
                    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
                    <plist version="1.0">
                    <dict>
                        <key>Label</key>
                        <string>com.antigravity.omnimind</string>
                        <key>ProgramArguments</key>
                        <array>
                            <string>/usr/bin/env</string>
                            <string>python3</string>
                            <string>{app_path}</string>
                            <string>--minimized</string>
                        </array>
                        <key>RunAtLoad</key>
                        <true/>
                        <key>KeepAlive</key>
                        <false/>
                    </dict>
                    </plist>
                """)
                try:
                    plist_path.write_text(plist_content)
                    import subprocess
                    # Unload trước để tránh duplicate entry khi update.
                    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
                    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
                    if result.returncode != 0:
                        logger.error(f"launchctl load failed: {result.stderr.strip()}")
                        QMessageBox.warning(
                            self,
                            "Auto-start macOS",
                            "Không bật được tự khởi động trên macOS. Vui lòng kiểm tra quyền LaunchAgents.",
                        )
                        return
                    logger.info("Auto-start enabled for macOS via LaunchAgent.")
                except Exception as e:
                    logger.error(f"Failed to enable auto-start on macOS: {e}")
                    QMessageBox.warning(
                        self,
                        "Auto-start macOS",
                        f"Lỗi bật tự khởi động: {str(e)[:120]}",
                    )
            else:
                if plist_path.exists():
                    try:
                        import subprocess
                        result = subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True, text=True)
                        if result.returncode != 0:
                            logger.warning(f"launchctl unload warning: {result.stderr.strip()}")
                        plist_path.unlink()
                        logger.info("Auto-start disabled for macOS.")
                    except Exception as e:
                        logger.error(f"Failed to disable auto-start on macOS: {e}")
                        QMessageBox.warning(
                            self,
                            "Auto-start macOS",
                            f"Lỗi tắt tự khởi động: {str(e)[:120]}",
                        )
                        
        elif sys_name == "Windows":
            # Ghi registry để auto start trên Windows
            import winreg, sys
            from pathlib import Path
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                if is_enabled:
                    # Nếu chạy binary đóng gói: dùng chính executable.
                    # Nếu chạy source: lưu command đầy đủ gồm Python + main.py.
                    if getattr(sys, "frozen", False):
                        cmd = f'"{sys.executable}" --minimized'
                    else:
                        main_py = Path(__file__).resolve().parents[2] / "main.py"
                        cmd = f'"{sys.executable}" "{main_py}" --minimized'
                    winreg.SetValueEx(key, "OmniMind", 0, winreg.REG_SZ, cmd)
                    logger.info("Auto-start enabled for Windows via Registry.")
                else:
                    try:
                        winreg.DeleteValue(key, "OmniMind")
                    except FileNotFoundError:
                        pass
                    logger.info("Auto-start disabled for Windows.")
                winreg.CloseKey(key)
            except Exception as e:
                logger.error(f"Failed to toggle auto-start on Windows: {e}")
                QMessageBox.warning(
                    self,
                    "Auto-start Windows",
                    f"Lỗi cập nhật Registry: {str(e)[:120]}",
                )
