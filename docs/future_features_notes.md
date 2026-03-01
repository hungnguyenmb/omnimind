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

