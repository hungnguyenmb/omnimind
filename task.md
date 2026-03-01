# OmniMind Project Tasks

Dưới đây là danh sách các hạng mục công việc cho dự án OmniMind (Desktop App + Backend).
Trạng thái: `[ ]` Chưa làm, `[/]` Đang làm, `[x]` Đã xong.

---

## 🛠 Project Map
- **Backend (API)**: `projects/license-server/` (Node.js/Express)
- **CMS (Admin)**: `projects/license-dashboard/` (Vite)
- **Client (App)**: `projects/omnimind/` (Python/PyQt5)
- **Domain**: `https://license.vinhyenit.com`

---

## ✅ Giai đoạn 1: Nền tảng & Bảo mật (Module 1) - [HOÀN TẤT]
- [x] Thiết lập Database SQLite cục bộ (`src/database/db_manager.py`)
- [x] Engine License Manager: Sinh HWID (SHA-256) & Gọi API Verify
- [x] UI License Gatekeeper: QThread bất đồng bộ, xử lý activation
- [x] Backend Integration: Mở rộng 12 API endpoints & 6 bảng PostgreSQL
- [x] Bugfix: Tăng VARCHAR limit cho OS Version trên Server

## ⚙️ Giai đoạn 2: Cấu hình & Môi trường AI (Module 2) - [ĐANG LÀM]
- [x] Thiết lập cấu hình API Base URL qua biến môi trường `OMNIMIND_API_URL`
- [ ] **Settings Page Logic**: 
    - [ ] Lưu/Load Telegram Token, Chat ID, Workspace Path vào `app_configs`
    - [ ] Cập nhật UI phản ánh trạng thái lưu thành công
- [ ] **Environment & Codex CLI Auto-Setup**:
    - [ ] **Check Prerequisites**: Logic kiểm tra `python3`, `node`, `npm` (Cross-platform)
    - [ ] **Auto-Install Env**: Script cài đặt tự động (PowerShell cho Win, Brew cho Mac) khi thiếu môi trường
    - [ ] **Admin/Sudo Request**: UI yêu cầu cấp quyền để thực hiện cài đặt
    - [ ] **Codex Install**: Tải binary từ CMS, giải nén và cấu hình PATH
    - [ ] **Verify**: Kiểm tra kết nối và account sau khi cài đặt
- [ ] **Sync Logic**: Logic CRUD đồng bộ Memory Rules và Vault Resources với SQLite

## 🧠 Giai đoạn 3: Động cơ AI & Bot Bridge (Module 3)
- [ ] **Context Engine**: Logic nạp Working Principles & Memory Rules vào câu lệnh AI
- [ ] **Subprocess Manager**: Quản lý việc chạy Codex CLI trong nền
- [ ] **Telegram Integration**: Nhận tin nhắn từ Bot -> Xử lý AI -> Trả lời Telegram
- [ ] **Trạng thái thực thi**: Hiển thị Log và Status (Running/Idle/Stopped) lên UI

## 🛒 Giai đoạn 4: Marketplace & Cập nhật (Module 4)
- [ ] **Marketplace UI**: Hiển thị danh sách Skills từ API
- [ ] **Hệ thống thanh toán**: Tích hợp luồng nạp tiền/mua Skill (QR Code/Link)
- [ ] **Auto-Update (Hot-update)**: Chiến lược Launcher & Payload để cập nhật không cần cài lại
- [ ] **Security**: Obfuscation code bằng PyArmor trước khi build

---

## 📝 Tài liệu tham chiếu
- [Database Schema](file:///Users/admin/.gemini/antigravity/brain/711dd37a-273d-478b-b1e3-02aba4f2c36d/database_schema.md)
- [API Documentation](file:///Users/admin/.gemini/antigravity/brain/711dd37a-273d-478b-b1e3-02aba4f2c36d/api_documentation.md)
- [Feature Spec](file:///Users/admin/.gemini/antigravity/brain/711dd37a-273d-478b-b1e3-02aba4f2c36d/api_and_features_spec.md)
