"""
OmniMind - Tab 2: Auth & Core Settings Page
Form Token Telegram, Workspace Path, OmniMind Config, Auto-start.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QCheckBox, QFileDialog, QScrollArea, QMessageBox, QProgressBar
)
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from ui.icons import Icons
from engine.config_manager import ConfigManager
from engine.environment_manager import EnvironmentManager
from engine.permission_manager import PermissionManager
import logging

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
                        "HĐH/kiến trúc máy chưa có gói OmniMind phù hợp "
                        f"({release_data.get('platform', 'unknown')}/{release_data.get('arch', 'unknown')})."
                    ),
                })
                return

            ok = self.env_manager.download_and_install_codex(
                dl_url,
                expected_checksum=(release_data.get("checksum") or ""),
                progress_callback=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit({
                "success": bool(ok),
                "message": "Cài đặt OmniMind thành công." if ok else "Không tải/cài được OmniMind.",
            })
        except Exception as e:
            logger.exception("Codex install worker failed")
            self.finished.emit({"success": False, "message": f"Lỗi cài OmniMind: {str(e)[:80]}"})


class AuthPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._verify_worker = None
        self._runtime_worker = None
        self._codex_install_worker = None
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
            "QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; }"
        )
        runtime_box_layout = QVBoxLayout(self.runtime_missing_box)
        runtime_box_layout.setContentsMargins(12, 10, 12, 10)
        runtime_box_layout.setSpacing(8)
        self.runtime_missing_title = QLabel("Thiếu môi trường runtime")
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
        self.codex_model_combo.addItem("o4-mini", "o4-mini")
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
                f"Cấu hình hiện tại đọc từ {src}: {cfg_path}. Khi lưu sẽ đồng bộ cả SQLite."
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
            text = f"✅ Công cụ cài runtime tự động: {display} · {msg}"
            color = "#10B981"
        else:
            text = f"❌ Công cụ cài runtime tự động: {display} · {msg}"
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
            row.addWidget(left)
            row.addStretch()

            btn = QPushButton("Cài đặt")
            btn.setObjectName("SecondaryBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(30)
            btn.setMinimumWidth(100)
            btn.clicked.connect(lambda _=False, dep=runtime: self._request_runtime_install(dep))
            if self._runtime_installing or self._codex_installing or not self._runtime_installer_ready:
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
                    f" Thiếu runtime: {', '.join(runtime_missing)}."
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
                    "Nhấn \"Tải bộ não AI\" để hệ thống tự động cài runtime còn thiếu (Python/Node/npm),"
                    " sau đó tải OmniMind."
                )
            else:
                hint_txt = (
                    "Runtime đã đủ. Nhấn \"Tải bộ não AI\" để bắt đầu tải và cài OmniMind."
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
                f"Đang thiếu runtime: {missing_text}. OmniMind vẫn sẽ được cài trước; runtime có thể cài bổ sung sau."
            )

        if codex_ready:
            self.codex_status_icon.setText("🟢")
            self.codex_status_label.setText("OmniMind đã được cài đặt")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #10B981;")
            if runtime_missing:
                missing_text = ", ".join(self._runtime_display_name(k) for k in runtime_missing)
                self.codex_hint.setText(
                    f"OmniMind đã có sẵn. Runtime bổ sung còn thiếu: {missing_text}. "
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
                f"Cài đặt OmniMind thành công. Runtime bổ sung còn thiếu: {missing_text}. "
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

        if sys_name == "Darwin":  # macOS
            if open_mode == "anchor":
                QMessageBox.information(
                    self,
                    "Mở màn hình cấp quyền",
                    (
                        "Đã mở màn hình quyền hệ thống.\n"
                        f"Hãy bật quyền cho \"{app_display_name}\" rồi quay lại ứng dụng.\n\n"
                        f"{identity_note}"
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
                        "Đã mở phần Settings tương ứng. Hãy cấp quyền rồi quay lại ứng dụng.\n"
                        "Sau khi cấp quyền, nên khởi động lại ứng dụng."
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
