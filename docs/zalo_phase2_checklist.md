# OmniMind Zalo Phase 2 Checklist

Ngày tạo: `2026-03-11`

Tài liệu này dùng để triển khai và theo dõi tiến độ `Phase 2 - Login UX và Connection Monitor` cho tích hợp Zalo trong `projects/omnimind`.

Tham chiếu gốc:
- [zalo_openzca_master_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_openzca_master_plan.md)
- [zalo_phase1_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_phase1_checklist.md)

## Mục tiêu Phase 2

Kết thúc Phase 2, OmniMind phải:
- Cho phép user `Login`, `Logout`, `Re-login` Zalo từ UI.
- Theo dõi được trạng thái auth và kết nối của Zalo theo state machine rõ ràng.
- Hiển thị được các trạng thái:
  - `Not logged in`
  - `QR required`
  - `Connected`
  - `Re-auth required`
- Có monitor định kỳ để kiểm tra `auth status`.
- Có cơ chế theo dõi health cơ bản của listener/connection lifecycle.
- Có thể gửi cảnh báo về Telegram khi Zalo mất auth hoặc cần đăng nhập lại.

Phase 2 chưa bao gồm:
- Lắng nghe tin nhắn để trả lời AI
- DM auto-reply
- Group mention reply
- Prompt Zalo
- Scope nhóm
- Memory integration cho Zalo chat

## Exit Criteria

Chỉ được xem là hoàn tất Phase 2 khi thỏa cả các điều kiện:
- User có thể login Zalo từ UI mà không cần chạy `openzca auth login` thủ công ngoài app.
- App hiển thị đúng 4 trạng thái login/connection đã chốt.
- Session invalid hoặc logout được phát hiện và chuyển sang `Re-auth required` hoặc `Not logged in`.
- Có polling `auth status` định kỳ.
- Có cảnh báo Telegram khi auth Zalo hỏng, có cooldown chống spam.
- Chưa có bot reply vẫn không sao, miễn login state và monitor đáng tin cậy.

## 1) Chuẩn bị phạm vi

- [x] Xác nhận Phase 1 đã xong ở mức runtime local `openzca`
- [x] Xác nhận chưa triển khai listener trả lời tin nhắn trong phase này
- [x] Xác nhận `1 profile cố định = omnimind`
- [ ] Xác nhận đổi tài khoản mới sẽ overwrite session cũ
- [x] Xác nhận Telegram alert chỉ là notification vận hành, không phải bot logic Zalo

## 2) Chốt state machine

Các trạng thái chuẩn:
- [x] `Not logged in`
- [x] `QR required`
- [x] `Connected`
- [x] `Re-auth required`

Checklist chi tiết:
- [x] Định nghĩa rõ điều kiện vào `Not logged in`
- [x] Định nghĩa rõ điều kiện vào `QR required`
- [x] Định nghĩa rõ điều kiện vào `Connected`
- [x] Định nghĩa rõ điều kiện vào `Re-auth required`
- [x] Định nghĩa rõ transition giữa các state
- [x] Định nghĩa rõ state nào là blocking cho phase sau

Gợi ý mapping:
- [x] `Not logged in`: chưa có session usable
- [x] `QR required`: user vừa bấm login, đang chờ scan QR
- [x] `Connected`: `auth status` OK và health monitor ổn
- [x] `Re-auth required`: từng connected nhưng auth/session không còn hợp lệ

## 3) Tạo `zalo_connection_monitor.py`

File:
- [x] Tạo [zalo_connection_monitor.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_connection_monitor.py)

### 3.1 Core responsibilities

- [x] Poll `openzca auth status`
- [x] Tính toán state machine
- [ ] Lưu timestamps:
  - [x] `last_connected_at`
  - [x] `last_auth_ok_at`
  - [x] `last_heartbeat_at`
- [x] Publish state cho UI đọc được
- [x] Trigger Telegram alert khi state xấu

### 3.2 Public APIs

- [x] Implement `start()`
- [x] Implement `stop()`
- [x] Implement `is_running()`
- [x] Implement `get_status()`
- [x] Implement `refresh_once()`
- [x] Implement `mark_qr_required()`
- [x] Implement `mark_reauth_required(reason)`

### 3.3 Background loop

- [x] Chạy polling loop nền bằng thread
- [x] Có interval cấu hình được hoặc hardcode hợp lý cho phase này
- [x] Không block UI thread
- [x] Có stop event rõ ràng

## 4) Mở rộng `openzca_manager.py` cho auth commands

File:
- [x] Sửa [openzca_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/openzca_manager.py)

### 4.1 Auth commands

- [x] Implement `run_auth_status()`
- [x] Implement `run_auth_login()`
- [x] Implement `run_auth_logout()`

### 4.2 Command behavior

- [x] Luôn dùng absolute path local binary
- [x] Luôn inject `OPENZCA_HOME`
- [x] Luôn dùng profile `omnimind`
- [x] Parse output đủ để xác định success/failure/message

### 4.3 QR handling

- [x] Xác định cách lấy tín hiệu `QR required`
- [x] Xác định output nào từ `openzca auth login` có thể hiển thị cho user
- [x] Nếu login command trả về QR qua terminal text, cần render được hoặc ít nhất show hướng dẫn rõ
- [ ] Nếu có khả năng mở QR/image, chuẩn hóa cách làm cho macOS và Windows

## 5) Tích hợp config cho auth state

File:
- [x] Sửa [config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)

### 5.1 Config keys

- [x] Thêm `zalo_login_state`
- [x] Thêm `zalo_self_user_id`
- [x] Thêm `zalo_last_connected_at`
- [x] Thêm `zalo_last_auth_ok_at`
- [x] Thêm `zalo_last_heartbeat_at`
- [x] Thêm `zalo_last_reauth_alert_at`
- [x] Thêm `zalo_last_monitor_error`

### 5.2 Helpers

- [x] Thêm helper `get_zalo_login_state()`
- [x] Thêm helper `set_zalo_login_state(...)`
- [x] Thêm helper `get_zalo_connection_status()`
- [ ] Thêm helper update timestamps an toàn

### 5.3 Defaults

- [x] Default `zalo_login_state = not_logged_in`
- [x] Default timestamps rỗng

## 6) Auth UI trong `auth_page.py`

File:
- [x] Sửa [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

### 6.1 Login controls

- [x] Thêm nút `Login Zalo`
- [x] Thêm nút `Logout Zalo`
- [x] Thêm nút `Re-login Zalo`

### 6.2 Auth status display

- [x] Hiển thị state hiện tại
- [x] Hiển thị mô tả ngắn cho state
- [x] Hiển thị account/session metadata cơ bản nếu đọc được
- [x] Hiển thị `last auth ok`
- [x] Hiển thị `last connected`

### 6.3 UX copy

- [x] Text rõ cho `Not logged in`
- [x] Text rõ cho `QR required`
- [x] Text rõ cho `Connected`
- [x] Text rõ cho `Re-auth required`

### 6.4 Async workers

- [x] Login chạy ở thread nền
- [x] Logout chạy ở thread nền
- [x] Refresh auth status chạy ở thread nền
- [x] Monitor update UI an toàn qua signal/callback

## 7) Dashboard integration

Files:
- [x] Sửa [dashboard_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/dashboard_manager.py)
- [ ] Sửa [dashboard_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/dashboard_page.py)

Checklist:
- [x] Expose `get_zalo_connection_status()`
- [ ] Nếu cần, thêm card Zalo read-only trong Dashboard
- [ ] Hiển thị state hiện tại
- [ ] Hiển thị cảnh báo nếu `Re-auth required`
- [x] Không thêm nút start/stop bot listener ở Phase 2 nếu chưa cần

## 8) Telegram alert integration

Mục tiêu:
- Khi Zalo mất auth hoặc cần login lại, gửi alert về Telegram nếu Telegram đang dùng được

Checklist:
- [x] Xác định API/gateway gửi alert Telegram sẽ tái dùng
- [x] Implement helper gửi cảnh báo đơn giản
- [ ] Trigger alert khi:
  - [x] `Connected -> Re-auth required`
  - [ ] monitor gặp lỗi auth lặp lại
  - [x] session biến mất sau khi trước đó từng connected
- [x] Thêm cooldown chống spam
- [x] Persist `zalo_last_reauth_alert_at`

Phase 2 chưa cần:
- [ ] Alert cho mọi lỗi nhỏ lẻ không ảnh hưởng auth

## 9) Polling và timing policy

- [x] Chốt polling interval `auth status`
- [x] Chốt timeout cho mỗi lần gọi `openzca auth status`
- [ ] Chốt số lần retry trước khi chuyển `Re-auth required`
- [x] Chốt cooldown gửi Telegram alert
- [ ] Chốt thời gian stale để coi health không còn hợp lệ

Gợi ý vận hành:
- [x] Poll mỗi `60-300s`
- [x] Cooldown alert `30 phút`

## 10) Logout / Re-login semantics

- [x] `Logout`: clear session hiện tại trong profile `omnimind`
- [x] `Re-login`: ép flow login mới trên cùng profile `omnimind`
- [x] Không tạo profile mới khi re-login
- [x] Sau `Logout`, state về `Not logged in`
- [x] Sau session invalid, state về `Re-auth required`

## 11) Error handling checklist

- [ ] Login bị user hủy
- [ ] QR scan timeout
- [ ] `auth status` trả lỗi không parse được
- [ ] `auth logout` thất bại
- [x] Runtime `openzca` tồn tại nhưng auth command lỗi
- [x] Telegram alert gửi thất bại
- [x] Monitor thread chết bất ngờ

## 12) Logging checklist

- [ ] Log state transition của Zalo auth
- [ ] Log login attempt
- [ ] Log logout attempt
- [x] Log monitor polling error
- [x] Log Telegram alert send attempt/result
- [x] Persist `last_monitor_error`

Phase 2 chưa bắt buộc:
- [ ] Structured JSONL đầy đủ cho inbound/outbound tin nhắn

## 13) Manual verification checklist

### Login flow

- [ ] User bấm `Login Zalo`
- [ ] UI chuyển sang `QR required`
- [ ] User scan QR thành công
- [ ] UI chuyển sang `Connected`

### Logout flow

- [ ] User bấm `Logout Zalo`
- [ ] Session bị clear
- [ ] UI về `Not logged in`

### Re-login flow

- [ ] User đang connected
- [ ] Bấm `Re-login`
- [ ] Session cũ bị thay thế trên cùng profile
- [ ] UI cuối cùng về `Connected`

### Session invalid flow

- [ ] Giả lập session hết hạn hoặc logout ngoài app
- [ ] Polling phát hiện lỗi
- [ ] UI chuyển `Re-auth required`
- [ ] Telegram nhận cảnh báo

## 14) Negative test checklist

- [ ] Thiếu `openzca` runtime nhưng user bấm login
- [ ] Runtime hỏng nhưng user bấm refresh auth
- [ ] Login output không parse được
- [ ] `auth status` bị timeout
- [ ] Monitor chạy song song 2 lần bị chặn đúng
- [x] Telegram config thiếu, alert không làm crash monitor

## 15) Definition of Done theo file

### `src/engine/openzca_manager.py`

- [x] Có `run_auth_status()`
- [x] Có `run_auth_login()`
- [x] Có `run_auth_logout()`
- [x] Parse result đủ dùng cho state machine

### `src/engine/zalo_connection_monitor.py`

- [x] Có background polling loop
- [x] Có state machine
- [x] Có publish status
- [x] Có Telegram alert cooldown

### `src/engine/config_manager.py`

- [x] Có auth/connection config keys
- [x] Có helper read/write state

### `src/ui/pages/auth_page.py`

- [x] Có login/logout/re-login buttons
- [x] Có auth state display
- [x] Có refresh action
- [x] Không block UI

### `src/engine/dashboard_manager.py`

- [x] Expose được connection status cho UI khác đọc

## 16) Ghi chú triển khai

- [x] Không lấn sang listener nhận tin nhắn ở Phase 2
- [x] Không xử lý bot reply trong Phase 2
- [x] Không tạo multi-account
- [x] Không tạo multi-profile
- [x] Không để env ngoài app override profile `omnimind`
- [x] Luôn coi `Re-auth required` là state vận hành quan trọng cần hiển thị rõ
