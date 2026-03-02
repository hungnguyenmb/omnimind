# Ghi Chú Tính Năng Phát Triển Tiếp Theo

Ngày tạo: `2026-03-01`

## 1) Tích hợp thanh toán SePay

Mục tiêu:
- Cho phép tạo giao dịch và xác nhận thanh toán qua SePay để mua license/skill.

Các ý chính cần triển khai:
- Tạo endpoint backend khởi tạo giao dịch (amount, nội dung chuyển khoản, mã giao dịch).
- Tạo webhook nhận trạng thái thanh toán từ SePay.
- Map giao dịch thành quyền sử dụng (kích hoạt license hoặc cấp quyền skill).
- Lưu lịch sử giao dịch để tra soát trong CMS.

## 2) Gửi ảnh từ Telegram cho Codex xử lý

Mục tiêu:
- User gửi ảnh qua Telegram, agent nhận file ảnh và chuyển cho Codex xử lý theo prompt.

Các ý chính cần triển khai:
- Bổ sung luồng nhận `photo/document image` từ Telegram Bot API.
- Tải ảnh về local và truyền đường dẫn ảnh vào phiên xử lý của Codex.
- Trả kết quả phân tích/tóm tắt từ Codex về Telegram.
- Giới hạn dung lượng ảnh + kiểm soát timeout.

## 3) Tạo thư mục mặc định để lưu file tải từ Telegram

Mục tiêu:
- Chuẩn hóa nơi lưu file Telegram để dễ quản lý và tái sử dụng.

Các ý chính cần triển khai:
- Định nghĩa thư mục mặc định theo OS:
  - macOS: `~/Library/Application Support/OmniMind/telegram_downloads`
  - Windows: `%LOCALAPPDATA%\\OmniMind\\telegram_downloads`
- Tự tạo thư mục nếu chưa tồn tại.
- Tách cấu trúc con theo ngày hoặc theo chat id (tùy chọn).
- Lưu metadata file tải (name, size, source message id).

## 4) Gửi lại tài liệu do Codex tạo ra vào Telegram

Mục tiêu:
- Khi Codex tạo file (docx/pdf/xlsx/txt...), bot có thể gửi file ngược lại cho user trên Telegram.

Các ý chính cần triển khai:
- Chuẩn hóa output artifacts của Codex (đường dẫn, loại file, tên file).
- Bổ sung hàm gửi file Telegram (`sendDocument`) từ local path.
- Nếu file lớn vượt giới hạn Telegram, tự nén/chia nhỏ hoặc trả link tải nội bộ.
- Gửi kèm caption tóm tắt nội dung file.

## Gợi ý thứ tự ưu tiên

1. Thư mục mặc định lưu file Telegram.
2. Nhận ảnh Telegram -> chuyển Codex xử lý.
3. Gửi lại file tài liệu do Codex tạo.
4. SePay payment + webhook + cấp quyền.

---

## Roadmap Sprint

### Sprint 1 (Đã hoàn tất)
- Chuẩn hoá download Codex theo `platform + arch` từ backend/CMS.
- Thêm API + CMS quản lý Codex release matrix.
- Client cài Codex theo release matrix và verify checksum.

### Sprint 2 (Đang triển khai)
- Xây nền trợ lý stateful trên SQLite:
  - `assistant_profile`
  - `conversation_messages`
  - `memory_summaries`
  - `memory_facts`
- Tối ưu truy vấn memory context bằng index + retention policy.
- Chuẩn bị sẵn manager cho luồng Telegram/Codex lấy context.

### Sprint 3 (Đang triển khai)
- Luồng Telegram thực chiến:
  - Hoàn tất lớp transport stream Telegram (`sendMessage` + `editMessageText`, chunking, throttle).
  - Hoàn tất Telegram long-polling service và nối vào nút Bật/Tắt Bot ở Dashboard.
  - Kết nối memory context + runtime interaction log cho tin nhắn Telegram.
  - Nối Telegram service với Codex CLI runtime (`codex exec`) và stream stdout realtime về Telegram.
  - Nhận ảnh/tài liệu từ Telegram, lưu thư mục chuẩn theo OS và bơm local path vào prompt Codex.
  - Gửi lại artifact local (nếu Codex trả về đường dẫn file hợp lệ) qua `sendDocument`.
- Việc còn lại:
  - Tăng độ chính xác parser artifact path (hiện đang theo regex heuristic).
  - Bổ sung policy allowlist path trước khi gửi file ngược Telegram.
  - Chuẩn hóa luồng multimodal nếu muốn phân tích ảnh native theo model vision.
