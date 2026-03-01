"""
OmniMind - Tab 2: Auth & Core Settings Page
Form Token Telegram, Workspace Path, Sandbox Permission, Auto-start.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QCheckBox, QFileDialog, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from ui.icons import Icons
from engine.config_manager import ConfigManager
from engine.environment_manager import EnvironmentManager
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


class AuthPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._verify_worker = None
        try:
            self.env_manager = EnvironmentManager()
        except Exception as e:
            logger.error(f"EnvironmentManager init failed: {e}")
            self.env_manager = None
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
        desc = QLabel("Cấu hình kết nối Telegram Bot, thư mục Workspace, và quyền hạn Sandbox cho AI.")
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

        ws_layout.addWidget(self._create_field_label("Đường dẫn Workspace"))
        ws_row = QHBoxLayout()
        ws_row.setSpacing(10)
        self.workspace_input = QLineEdit()
        self.workspace_input.setObjectName("FormInput")
        self.workspace_input.setPlaceholderText("/Users/.../your-workspace")
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

        # ── Codex CLI Authentication Card ──
        codex_card = self._create_card("🧠  Xác thực Codex CLI")
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

        # Nút "Tải bộ não AI" (ẩn mặc định, hiện khi chưa cài Codex)
        self.codex_download_btn = QPushButton("  Tải bộ não AI")
        self.codex_download_btn.setObjectName("PrimaryBtn")
        self.codex_download_btn.setIcon(Icons.download("#FFFFFF", 16))
        self.codex_download_btn.setCursor(Qt.PointingHandCursor)
        self.codex_download_btn.setFixedHeight(40)
        self.codex_download_btn.setMinimumWidth(180)
        self.codex_download_btn.clicked.connect(self._download_codex)
        self.codex_download_btn.setVisible(False)
        status_row.addWidget(self.codex_download_btn)

        # Nút "Xác thực tài khoản" (ẩn mặc định, hiện khi đã cài Codex)
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

        layout.addWidget(codex_card)

        # Auto-check khi khởi động
        self._check_codex_installed()

        # ── Security & Preferences Card ──
        sec_card = self._create_card("🛡  Bảo mật & Tuỳ chọn")
        sec_layout = sec_card.layout()

        # Sandbox Permission
        sec_layout.addWidget(self._create_field_label("Quyền Sandbox"))
        self.sandbox_combo = QComboBox()
        self.sandbox_combo.setObjectName("FormCombo")
        self.sandbox_combo.addItems([
            "🔒 Read-only (Chỉ đọc, an toàn tuyệt đối)",
            "⚡ Safe (Đọc + Ghi file an toàn)",
            "🔓 Full Danger (Toàn quyền, không hạn chế)"
        ])
        self.sandbox_combo.setFixedHeight(44)
        sec_layout.addWidget(self.sandbox_combo)

        sec_layout.addSpacing(4)

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

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn Workspace")
        if folder:
            self.workspace_input.setText(folder)

    def _load_settings(self):
        """Load cấu hình từ Database lên UI."""
        token = ConfigManager.get("telegram_token", "")
        chat_id = ConfigManager.get("telegram_chat_id", "")
        workspace = ConfigManager.get("workspace_path", "")
        sandbox = ConfigManager.get("sandbox_permission", "🔒 Read-only (Chỉ đọc, an toàn tuyệt đối)")
        
        # Load Checkboxes
        auto_start = ConfigManager.get("auto_start", "False") == "True"
        perm_acc = ConfigManager.get("perm_accessibility", "False") == "True"
        perm_scr = ConfigManager.get("perm_screenshot", "False") == "True"
        perm_cam = ConfigManager.get("perm_camera", "False") == "True"

        self.token_input.setText(token)
        self.user_id_input.setText(chat_id)
        self.workspace_input.setText(workspace)

        idx = self.sandbox_combo.findText(sandbox)
        if idx >= 0:
            self.sandbox_combo.setCurrentIndex(idx)
            
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

    def _save_settings(self):
        """Lưu cấu hình từ UI xuống Database."""
        token = self.token_input.text().strip()
        chat_id = self.user_id_input.text().strip()
        workspace = self.workspace_input.text().strip()
        sandbox = self.sandbox_combo.currentText()
        
        auto_start = str(self.auto_start_check.isChecked())
        perm_acc = str(self.perm_accessibility.isChecked())
        perm_scr = str(self.perm_screenshot.isChecked())
        perm_cam = str(self.perm_camera.isChecked())

        ConfigManager.set("telegram_token", token)
        ConfigManager.set("telegram_chat_id", chat_id)
        ConfigManager.set("workspace_path", workspace)
        ConfigManager.set("sandbox_permission", sandbox)
        ConfigManager.set("auto_start", auto_start)
        ConfigManager.set("perm_accessibility", perm_acc)
        ConfigManager.set("perm_screenshot", perm_scr)
        ConfigManager.set("perm_camera", perm_cam)
        
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
        """Tự động kiểm tra môi trường và Codex CLI khi khởi động."""
        if self.env_manager is None:
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText("Lỗi khởi tạo Environment Manager")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_hint.setText("Không thể kiểm tra môi trường. Vui lòng khởi động lại ứng dụng.")
            return
        try:
            env_status = self.env_manager.check_prerequisites()
        except Exception as e:
            logger.error(f"check_prerequisites failed: {e}")
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText("Lỗi kiểm tra môi trường")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_hint.setText(f"Chi tiết lỗi: {str(e)[:60]}")
            return
        
        if env_status["is_ready"]:
            # Kiểm tra xem trước đó đã xác thực chưa
            auth_status = ConfigManager.get("codex_auth_status", "unverified")
            
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
                self.codex_hint.setText("Hệ thống đã sẵn sàng sử dụng.")
                # Chạy Live Check ngầm để lấy version thực tế
                self._verify_codex()
            else:
                self.codex_status_icon.setText("🟡")
                self.codex_status_label.setText("Đã cài đặt · Chưa xác thực")
                self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
                self.codex_verify_btn.setVisible(True)
                self.codex_download_btn.setVisible(False)
                self.codex_hint.setText("Môi trường Python, Node, và Codex CLI đã sẵn sàng. Nhấn xác thực để kiểm tra tài khoản.")
        else:
            # Thiếu → hiện nút Tải
            self.codex_status_icon.setText("🔴")
            
            missing = [k for k, v in env_status.items() if v == "MISSING" and k != "is_ready"]
            if missing:
                self.codex_status_label.setText(f"Thiếu môi trường: {', '.join(missing)}")
            else:
                self.codex_status_label.setText("Chưa cài đặt Codex CLI")
                
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_download_btn.setVisible(True)
            self.codex_verify_btn.setVisible(False)
            
            hint_txt = "Thiết bị thiếu các thành phần bắt buộc. Nhấn \"Tải bộ não AI\" để cài đặt tự động (Cần cấp quyền Admin)."
            self.codex_hint.setText(hint_txt)

    def _download_codex(self):
        """Tải và cài đặt Môi trường (nếu thiếu) sau đó tải Codex CLI."""
        from PyQt5.QtWidgets import QMessageBox
        
        self.codex_download_btn.setEnabled(False)
        self.codex_download_btn.setText("  Đang cài đặt...")
        self.codex_status_label.setText("Đang cài đặt môi trường và Codex...")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3B82F6;")
        self.codex_hint.setText("Việc này có thể mất vài phút. Vui lòng chờ và cấp quyền Admin/Sudo nếu được yêu cầu.")

        # Chạy logic cài đặt trong Bg Worker (Thread) để không treo UI
        import threading
        def install_worker():
            try:
                env_status = self.env_manager.check_prerequisites()
                missing = [k for k, v in env_status.items() if v == "MISSING" and k not in ["is_ready", "codex"]]
                
                # 1. Cài đặt Python/Node nếu thiếu
                if missing:
                    self.env_manager.install_missing_env(missing)
                
                # 2. Tải và cài đặt Codex từ API Server
                import requests
                api_url = f"{ConfigManager.get('OMNIMIND_API_URL', 'http://localhost:8050')}/api/v1/omnimind/codex/releases"
                resp = requests.get(api_url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    platform_key = "darwin" if self.env_manager.os_name == "Darwin" else "win32"
                    if platform_key in data.get("platforms", {}):
                        dl_url = data["platforms"][platform_key]["url"]
                        success = self.env_manager.download_and_install_codex(dl_url)
                        if success:
                            # Chạy UI update từ Main Thread
                            from PyQt5.QtCore import QTimer
                            QTimer.singleShot(0, self._on_download_complete)
                        else:
                            raise Exception("Không giải nén được Codex.")
                    else:
                        raise Exception("HĐH không được hỗ trợ Codex.")
                else:
                    raise Exception("Không thể gọi API lấy link tải Codex.")
            except Exception as e:
                logger.error(f"Install worker error: {e}")
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._set_codex_error(f"Lỗi: {str(e)[:40]}"))

        threading.Thread(target=install_worker, daemon=True).start()

    def _on_download_complete(self):
        """Callback sau khi tải Codex xong."""
        self.codex_download_btn.setEnabled(True)
        self.codex_download_btn.setText("  Tải bộ não AI")
        self.codex_download_btn.setVisible(False)
        self.codex_verify_btn.setVisible(True)
        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText("Đã cài đặt · Chưa xác thực")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
        self.codex_hint.setText("Cài đặt thành công! Nhấn xác thực để đăng nhập tài khoản Codex.")

    def _verify_codex(self):
        """Kiểm tra xác thực Codex CLI sử dụng EnvironmentManager."""
        if self.env_manager is None:
            logger.error("AuthPage: env_manager is None during _verify_codex")
            self._set_codex_error("Cấu trúc môi trường lỗi")
            return
        if self._verify_worker and self._verify_worker.isRunning():
            return

        logger.info("Starting Codex verification...")
        self.codex_verify_btn.setEnabled(False)
        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText("Đang xác thực tài khoản Codex...")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3B82F6;")
        self.codex_hint.setText("Đang kiểm tra trạng thái đăng nhập, vui lòng chờ.")

        self._verify_worker = CodexVerifyWorker(self.env_manager, self)
        self._verify_worker.finished.connect(self._on_verify_finished)
        self._verify_worker.start()

    def _on_verify_finished(self, result: dict):
        logger.info(f"Codex verify result: {result}")
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
        self.codex_hint.setText("Codex CLI đã xác thực thành công. Sẵn sàng sử dụng.")
        
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
        self.codex_verify_btn.setVisible(True)
        self.codex_logout_btn.setVisible(False)
        self.codex_hint.setText("Chưa đăng nhập hoặc phiên đăng nhập đã hết hạn. Vui lòng xác thực lại.")
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
            self.codex_hint.setText("Không thể đăng xuất Codex CLI. Vui lòng thử lại.")
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

        import platform, subprocess
        sys_name = platform.system()

        if sys_name == "Darwin":  # macOS
            if perm_type == "accessibility":
                # Mở Security & Privacy -> Accessibility
                subprocess.Popen([
                    "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
                ])
            elif perm_type == "screenshot":
                # Mở Security & Privacy -> Screen Recording
                subprocess.Popen([
                    "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
                ])
            elif perm_type == "camera":
                # Mở Security & Privacy -> Camera
                subprocess.Popen([
                    "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"
                ])

        elif sys_name == "Windows":
            if perm_type == "accessibility":
                # Windows: mở Ease of Access
                subprocess.Popen(["start", "ms-settings:easeofaccess-keyboard"], shell=True)
            elif perm_type == "screenshot":
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.information(
                    self, "Screen Capture",
                    "Trên Windows, quyền chụp màn hình đã được cấp mặc định.",
                )
            elif perm_type == "camera":
                subprocess.Popen(["start", "ms-settings:privacy-webcam"], shell=True)
        else:
            from PyQt5.QtWidgets import QMessageBox
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
                    subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True)
                    logger.info("Auto-start enabled for macOS via LaunchAgent.")
                except Exception as e:
                    logger.error(f"Failed to enable auto-start on macOS: {e}")
            else:
                if plist_path.exists():
                    try:
                        import subprocess
                        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
                        plist_path.unlink()
                        logger.info("Auto-start disabled for macOS.")
                    except Exception as e:
                        logger.error(f"Failed to disable auto-start on macOS: {e}")
                        
        elif sys_name == "Windows":
            # Ghi registry để auto start trên Windows
            import winreg, sys
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
                if is_enabled:
                    # Truyền sys.argv[0] hoặc file exe nếu đã compiled
                    winreg.SetValueEx(key, "OmniMind", 0, winreg.REG_SZ, f'"{sys.argv[0]}"')
                    logger.info("Auto-start enabled for Windows via Registry.")
                else:
                    winreg.DeleteValue(key, "OmniMind")
                    logger.info("Auto-start disabled for Windows.")
                winreg.CloseKey(key)
            except Exception as e:
                logger.error(f"Failed to toggle auto-start on Windows: {e}")
