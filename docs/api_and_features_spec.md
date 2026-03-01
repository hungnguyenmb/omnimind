# Tài Liệu Đặc Tả Tính Năng & Yêu Cầu API - OmniMind

Tài liệu này đóng vai trò là "Cầu nối" giữa Giao diện (UI) đã hoàn thiện và quy trình phát triển Backend/API. Tài liệu liệt kê từng tính năng có trên màn hình, cách thức xử lý (máy chủ cục bộ hay cần gọi API), và chức năng của các Quyền Hệ Thống.

> [!CAUTION]
> **YÊU CẦU BẮT BUỘC VỀ CROSS-PLATFORM (Windows & macOS):**
> OmniMind được thiết kế để chạy trên cả 2 hệ điều hành Windows và macOS. Bất kỳ Agent nào khi code logic Backend (nhất là các đoạn script cài đặt, xử lý file path, subprocess, hay permission request) **ĐỀU PHẢI TÍNH TOÁN VÀ VIẾT LOGIC RẼ NHÁNH CHO CẢ 2 HỆ ĐIỀU HÀNH**. Tuyệt đối không hardcode đường dẫn hay bash script chỉ chạy được trên Linux/Mac. Sử dụng `os`, `pathlib` và `platform.system()` để xử lý nội bộ.

> [!IMPORTANT]
> **BẢN ĐỒ DỰ ÁN (Project Map) - Dành cho các Agent:**
> - **Client App (Desktop)**: `projects/omnimind/` — PyQt5, SQLite.
> - **Backend API Server**: `projects/license-server/` — Node.js (Express), PostgreSQL. Domain production: `https://license.vinhyenit.com`
> - **CMS Dashboard (Admin UI)**: `projects/license-dashboard/` — Vite + JS.
> - **Biến môi trường Client**: `OMNIMIND_API_URL` (Mặc định `http://localhost:8050`, Production: `https://license.vinhyenit.com`)

---

## 1. Yêu Cầu Quyền Hệ Thống (System Permissions)
OmniMind không phải là một app tĩnh, mà là một **AI Agent** chạy ngầm. Để AI có thể "Nhìn", "Điều khiển" và "Giám sát" hệ thống như một con người, App yêu cầu 3 quyền cốt lõi. *Lưu ý: Logic xin quyền gọi mở thẳng System Preferences (macOS) hoặc Settings (Windows).*

### 1.1 Quyền Trợ Năng (Accessibility / UIAutomation)
- **Mục đích**: Cho phép AI (thông qua Codex CLI / Python PyAutoGUI / AppleScript) mô phỏng thao tác gõ phím, di chuyển chuột, nhấp chuột và đọc cấu trúc Cây giao diện (DOM/Accessibility Tree) của các ứng dụng khác.
- **Tại sao cần?**: Nếu User nhắn Telegram: *"Vào thư mục X và xoá file Y"*, AI cần quyền này để tự động mở Finder/Explorer và thực hiện thao tác nếu không sử dụng bash script.

### 1.2 Quyền Ghi Màn Hình (Screen Capture)
- **Mục đích**: Chụp ảnh màn hình hiện tại của thiết bị mà không cần người dùng xác nhận mỗi lần chụp.
- **Tại sao cần?**: Tính năng Computer Vision. User nhắn: *"Màn hình tôi đang bị lỗi gì vậy?"*. AI sẽ ngầm chụp lại màn hình, phân tích qua OpenAI Vision và gửi câu trả lời về Telegram. Không có quyền này, AI bị "Mù".

### 1.3 Quyền Camera
- **Mục đích**: Cho phép AI truy cập luồng video từ Webcam.
- **Tại sao cần?**: Dành cho các tính năng giám sát không gian thực tế hoặc nhận diện khuôn mặt người dùng (Face ID/Security).

---

## 2. Đặc Tả Tính Năng Theo Module (Tabs)

### Màn Hình 0: License Gatekeeper (Màn hình Chặn)
- **Mô tả**: Hiển thị đầu tiên nếu chưa có/sai License. Có ô nhập Key và nút Kích hoạt. Sau đó là các nút thanh toán để Mua/Gia hạn.
- **Logic Local**: 
  - Khởi tạo HWID (Hardware ID) từ thông số CPU/Mainboard.
  - Mã hoá Key trước khi lưu SQLite.
- **API Required**: 
  - `POST /api/v1/licenses/verify`: Gửi Key + HWID lên Server kiểm tra. Trả về JWT hoặc tín hiệu True/False.
  - `POST /api/v1/payments/create`: (Nếu mua mới) Lấy Link Stripe/Tạo mã QR cho gói cước.

### Màn Hình 1: Dashboard (Luồng Auto-Update & Mã Hóa Mã Nguồn)
- **Tính năng**: Xem tổng quan (Version, License Type), Xem Changelog, Bật/Tắt Bot System và **Cập nhật Ứng dụng tự động**.
- **Logic Local**: 
  - Start/Stop Background Thread của Telegram Bot Engine.
  - Detect OS (`platform.system()`) để hiển thị logo Mac/Win.
  - **Luồng Auto-Update App (Cơ chế Hot-Update giữ Quyền Hệ thống)**:
    - *Vấn đề*: Việc tải file nhị phân (`.exe` / `.app`) mới rồi xoá file cũ đi sẽ làm Hệ điều hành hiểu đây là ứng dụng mới hoàn toàn, buộc người dùng phải gỡ đi và cấp lại quyền Accessibility/Screen Recording rất phiền phức.
    - *Giải pháp Kiến trúc Vỏ bọc (Launcher & Payload)*: Ứng dụng gốc người dùng chạy là một **Launcher tĩnh** (Được biên dịch bằng C/Rust hoặc PyInstaller tĩnh). Toàn bộ tính năng, UI, và Engine (gọi chung là **Payload**) được biên dịch dạng thư viện động hoặc kịch bản được nén thành `.zip` nằm trong thư mục dữ liệu cục bộ (`AppData/Local/OmniMind` trên Win, `~/Library/Application Support/OmniMind` trên Mac).
    - *Tính Tương Thích Với Mã Hoá (Obfuscation)*:
      - **Mã hoá độc lập**: Payload (code thực thi UI/Logic) sẽ được mã hoá bằng **PyArmor** (hoặc Nuitka) *trước* khi đóng gói thành file `.zip` để đẩy lên giao diện Update trên Server CMS.
      - **Launcher giải mã runtime**: File tĩnh Launcher gốc có tích hợp sẵn Bootloader của lớp mã hoá để có thể "kéo" và chạy các tệp `.pye` / `.so` / `.pyd` mã hoá từ trong thư mục Payload cục bộ một cách trơn tru.
      - Việc cập nhật hoàn toàn **KHÔNG ẢNH HƯỞNG** đến độ phân giải của mã hóa. Khi giải nén đè bản Update (.zip) mới xuống Payload cục bộ, Launcher vẫn chỉ cần load và chạy các tệp đã được mã hoá đó của phiên bản mới.
    - *Luồng thực thi*:
      1. Check version API: So sánh version Payload hiện tại và mới nhất.
      2. Nếu có bản mới: Tải file nén `.zip` của Payload mới (Tất cả tệp Python đã bị obfucscated) về thư mục tạm.
      3. Giải nén và thay thế đè lên thư mục Payload cũ tại bộ nhớ dữ liệu (không hề đụng tới file tệp thực thi Launcher tĩnh).
      4. Tải xong: Thông báo "Cập nhật thành công. Khởi động lại ứng dụng". Launcher chỉ việc khởi chạy lại chính nó và load đoạn mã bị obfuscate mới lên. Do Launcher chưa từng bị sửa đổi nội dung tệp nhị phân nên System **giữ nguyên 100% các quyền Trợ năng/Webcam đã cấp**.
- **API Required**: 
  - `GET /api/v1/app/version`: Lấy version mới nhất, danh sách Changelog, và **URL download tệp ZIP Payload (đã obfuscate)** từ Server CMS.

### Màn Hình 2: Authentication & Cấu Hình (Luồng Cài đặt Môi trường)
- **Tính năng**: Nhập Telegram Token, Chat ID, Workspace Path. Đặc biệt: **Codex CLI Auth & Environment Auto-Setup**.
- **Logic Local**:
  - Save/Load từ DB bảng `app_configs`.
  - `shutil.which("codex")` để nhận diện CLI đã cài chưa.
  - **Luồng Kiểm tra & Cài đặt Môi trường Bắt buộc (Cross-Platform)**:
    1. Lấy link tải Codex CLI từ CMS (chia rõ link cho Mac/Win).
    2. **Check Prerequisites**: Trước khi tải Codex, dùng subprocess kiểm tra hệ thống có `python`/`python3` và `node`/`npm` chưa.
    3. **Auto-Install Env**: Nếu thiếu môi trường nào, báo cáo UI cảnh báo và yêu cầu người dùng cấp Quyền Quản Trị (Admin/Sudo). Sau đó chạy script tải tự động Python/NodeJS silent install tương ứng với Hệ điều hành (Sử dụng PowerShell cho Win, bash/brew thủ công cho Mac).
    4. **Download & Install Codex**: Sau khi môi trường đã đủ, tải Codex CLI từ Github (được phân phối qua CMS) về cài đặt. 
- **API Required**: 
  - `GET /api/v1/codex/releases`: Lấy cấu trúc phát hành Codex (URL file nhị phân Github, hướng dẫn cài, yêu cầu môi trường đối chiếu) do CMS quy định.

### Màn Hình 3: Trí Nhớ (Memory / Rules)
- **Tính năng**: Quản lý các prompt gốc (Ví dụ: "Luôn luôn code bằng Python", "Giao tiếp bằng tiếng Việt"). Cung cấp CRUD (Thêm, Sửa, Xoá) và Bật/Tắt (Toggle).
- **Logic Local**: 
  - Đọc/Ghi 100% vào bảng `memory_rules` cục bộ.
  - Giao diện Table tự re-render khi DB thay đổi.
  - Core AI Engine sẽ `SELECT * WHERE is_active = 1` để nhồi vào prompt mỗi khi nhận tin nhắn Telegram.
- **API Required**: 
  - Không cần API Server. 

### Màn Hình 4: Kho Tài Nguyên Hạt Nhân (Vault)
- **Tính năng**: Nơi lưu trữ thông tin nhạy cảm định dạng động (SSH ID, Email, API Key hệ thống, OS Account) phục vụ cho Agent.
- **Logic Local**:
  - Ghi vào bảng `vault_resources` cục bộ.
  - **MÃ HOÁ (Encryption)**: Master Key cục bộ sẽ encrypt trường `credentials` trước khi UPDATE/INSERT và decrypt khi Coren AI Engine cần dùng.
  - Giao diện hỗ trợ Form động (`_rebuild_fields`) dọn Layout tự động dựa trên combo `Type`.
- **API Required**: 
  - Không cần API Server. (Chỉ dùng nội bộ cho Agent).

### Màn Hình 5: Skill Marketplace
- **Tính năng**: Cửa hàng tính năng bổ sung (như AppStore). Chia làm 2 tab: Store (Khám phá) và My Skills (Đã cài).
- **Logic Local**:
  - Đọc bảng `installed_skills` để đối chiếu với Store -> Check trạng thái (Đã cài/Cần mua).
  - Tải file ZIP từ Manifest, Verify Hash, và giải nén vào đúng thư mục `[app_data]/skills/[id]/`.
- **API Required**: 
  - `GET /api/v1/skills`: Lấy danh sách kỹ năng mới nhất (Catalog).
  - `GET /api/v1/skills/{id}/manifest`: Lấy Manifest chi tiết (các file cần tải, code python) cho một kỹ năng.
  - `POST /api/v1/skills/purchase`: Tạo Transaction báo cáo về máy chủ khi người dùng nhấn "Tải/Mua" để Server ghi nhận `purchased_skills`.

---

## 3. Tổng Hợp Danh Sách API Backend Server Cần Phát Triển
Để hệ thống Client hoạt động như thiết kế, Đội ngũ Server cần chuẩn bị sẵn các Endpoint RESTful (JSON) sau:

| Endpoint | Method | Chức Năng | Ghi Chú |
| :--- | :---: | :--- | :--- |
| `/api/v1/licenses/verify` | POST | Xác minh Key + Gắn HWID | Rất quan trọng (Anti-crack) |
| `/api/v1/payments/create` | POST | Khởi tạo giao dịch (License/Skill) | Trả về URL Stripe / QR Code |
| `/api/v1/app/version` | GET | Check update & list Changelogs | |
| `/api/v1/skills` | GET | Liệt kê Market Catalog | Hỗ trợ phân trang, lọc VIP/Free |
| `/api/v1/skills/{id}/manifest` | GET | Trả về cấu trúc File của 1 Skill | JSON chứa Hash file logic |
| `/api/v1/skills/purchase` | POST | Báo cáo giao dịch Mua Skill | Server xác thực và cấp biên lai |

Tài liệu này là cơ sở để Agent/Lập trình viên backend tiến hành code API và setup Database Manager tương ứng trên App Client.
