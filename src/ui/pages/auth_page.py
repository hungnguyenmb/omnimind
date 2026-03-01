"""
OmniMind - Tab 2: Auth & Core Settings Page
Form Token Telegram, Workspace Path, Sandbox Permission, Auto-start.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QGraphicsDropShadowEffect,
    QCheckBox, QFileDialog, QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from ui.icons import Icons


class AuthPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

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

    def _check_codex_installed(self):
        """Tự động kiểm tra Codex CLI đã cài chưa khi khởi động."""
        import subprocess, shutil
        codex_path = shutil.which("codex")
        if codex_path:
            # Đã cài → hiện nút Xác thực
            self.codex_status_icon.setText("🟡")
            self.codex_status_label.setText("Đã cài đặt · Chưa xác thực")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
            self.codex_verify_btn.setVisible(True)
            self.codex_download_btn.setVisible(False)
            self.codex_hint.setText("Codex CLI đã được cài đặt. Nhấn xác thực để kiểm tra kết nối tài khoản.")
        else:
            # Chưa cài → hiện nút Tải
            self.codex_status_icon.setText("🔴")
            self.codex_status_label.setText("Chưa cài đặt Codex CLI")
            self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
            self.codex_download_btn.setVisible(True)
            self.codex_verify_btn.setVisible(False)
            self.codex_hint.setText("Codex CLI chưa được cài đặt trên thiết bị. "
                                    "Nhấn \"Tải bộ não AI\" để tải và cài đặt tự động.")

    def _download_codex(self):
        """Tải và cài đặt Codex CLI. (Logic tải sẽ triển khai sau)"""
        self.codex_download_btn.setEnabled(False)
        self.codex_download_btn.setText("  Đang tải...")
        self.codex_status_label.setText("Đang tải Codex CLI...")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #3B82F6;")
        self.codex_hint.setText("Đang tải và cài đặt Codex CLI... Vui lòng chờ.")

        # TODO: Triển khai logic tải và cài đặt Codex CLI
        # import subprocess
        # Bước 1: Kiểm tra npm/node đã cài chưa
        # Bước 2: Chạy npm install -g @openai/codex hoặc tải binary
        # Bước 3: Verify cài đặt thành công
        # Bước 4: Gọi self._on_download_complete()

        # Tạm thời simulate hoàn tất sau 2 giây (demo UI)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(2000, self._on_download_complete)

    def _on_download_complete(self):
        """Callback sau khi tải Codex xong."""
        self.codex_download_btn.setVisible(False)
        self.codex_verify_btn.setVisible(True)
        self.codex_status_icon.setText("🟡")
        self.codex_status_label.setText("Đã cài đặt · Chưa xác thực")
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #F59E0B;")
        self.codex_hint.setText("Cài đặt thành công! Nhấn xác thực để đăng nhập tài khoản Codex.")

    def _verify_codex(self):
        """Kiểm tra xác thực Codex CLI."""
        import subprocess
        try:
            result = subprocess.run(
                ["codex", "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                self.codex_status_icon.setText("🟢")
                self.codex_status_label.setText(f"Đã kết nối · {version}")
                self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #10B981;")
                self.codex_verify_btn.setText("  Đã xác thực")
                self.codex_verify_btn.setObjectName("InstalledBtn")
                self.codex_verify_btn.setIcon(Icons.check_circle("#10B981", 16))
                self.codex_verify_btn.style().unpolish(self.codex_verify_btn)
                self.codex_verify_btn.style().polish(self.codex_verify_btn)
                self.codex_logout_btn.setVisible(True)
                self.codex_hint.setText("Codex CLI đã xác thực thành công. Sẵn sàng sử dụng.")
            else:
                self._set_codex_error("Codex chưa đăng nhập")
        except FileNotFoundError:
            self._set_codex_error("Codex CLI chưa được cài đặt")
        except subprocess.TimeoutExpired:
            self._set_codex_error("Timeout khi kết nối")
        except Exception as e:
            self._set_codex_error(f"Lỗi: {str(e)[:40]}")

    def _set_codex_error(self, msg):
        self.codex_status_icon.setText("🔴")
        self.codex_status_label.setText(msg)
        self.codex_status_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #EF4444;")
        self.codex_logout_btn.setVisible(False)

    def _logout_codex(self):
        """Reset trạng thái về đã cài nhưng chưa xác thực."""
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

    def _request_permission(self, perm_type, checked):
        """Yêu cầu quyền hệ thống tuỳ theo OS (macOS / Windows)."""
        if not checked:
            return  # Bỏ check thì không cần request

        import platform, subprocess
        sys_name = platform.system()

        if sys_name == "Darwin":  # macOS
            if perm_type == "accessibility":
                # Mở Security & Privacy → Accessibility
                subprocess.Popen([
                    "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
                ])
            elif perm_type == "screenshot":
                # Mở Security & Privacy → Screen Recording
                subprocess.Popen([
                    "open", "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
                ])
            elif perm_type == "camera":
                # Mở Security & Privacy → Camera
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
