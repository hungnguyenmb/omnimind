# OmniMind Zalo Phase 3 Checklist

Ngày tạo: `2026-03-11`

Tài liệu này dùng để triển khai và theo dõi tiến độ `Phase 3 - Zalo Bot MVP Text-only` cho tích hợp Zalo trong `projects/omnimind`.

Tham chiếu gốc:
- [zalo_openzca_master_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_openzca_master_plan.md)
- [zalo_phase2_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_phase2_checklist.md)

## Mục tiêu Phase 3

Kết thúc Phase 3, OmniMind phải:
- Lắng nghe được tin nhắn Zalo bằng `openzca listen --supervised --raw --keep-alive`.
- Tự trả lời tin nhắn trực tiếp bằng core Codex hiện tại.
- Tự trả lời tin nhắn nhóm khi bot bị `@mention`.
- Có công tắc bật/tắt auto-reply riêng cho Zalo.
- Có cấu hình scope nhóm: `all_groups` hoặc `selected_groups`.
- Có thể lấy danh sách group từ Zalo để người dùng chọn cho `selected_groups`.
- Có prompt nguyên tắc trả lời riêng cho Zalo.
- Gửi `typing` trước khi trả lời nếu command hỗ trợ hoạt động ổn định.
- Có lifecycle control tối thiểu cho listener: `start`, `stop`, `restart`, `running/stopped`.
- Chạy song song với Telegram mà không ảnh hưởng logic AI core hiện tại.

Phase 3 chưa bao gồm:
- Media/file/image nâng cao
- Voice/sticker
- Permission-confirm flow qua Zalo
- Dashboard analytics nâng cao
- Multi-account Zalo
- Refactor lớn `TelegramBotService`

## Exit Criteria

Chỉ được xem là hoàn tất Phase 3 khi thỏa cả các điều kiện:
- `ZaloBotService` có thể start/stop ổn định từ app.
- Tin nhắn DM hợp lệ được chuyển vào `CodexRuntimeBridge` và có phản hồi gửi lại Zalo.
- Tin nhắn group chỉ được trả lời khi có `@mention` và thỏa scope nhóm.
- Có dedupe để không xử lý trùng message khi reconnect.
- Có lock để không chạy chồng nhiều listener cùng profile `omnimind`.
- Có on/off auto-reply Zalo từ UI/config.
- Có trạng thái listener tối thiểu để biết bot đang chạy hay đã dừng.
- Khi OmniMind auto-start sau reboot, listener có thể tự start lại nếu config cho phép.
- Có prompt nguyên tắc Zalo và được ghép vào luồng trả lời.
- Chưa hỗ trợ media vẫn không sao, miễn text bot flow ổn định.

## 1) Chuẩn bị phạm vi

- [ ] Xác nhận Phase 1 và Phase 2 đã ổn định
- [ ] Xác nhận Phase 3 chỉ làm bot text-only
- [ ] Xác nhận chưa làm media/file nâng cao ở phase này
- [ ] Xác nhận vẫn chỉ dùng `1 profile = omnimind`
- [ ] Xác nhận vẫn chỉ dùng `1 tài khoản Zalo tại 1 thời điểm`
- [ ] Xác nhận không refactor lớn AI core hiện tại

## 2) Chốt behavior của bot Zalo

### 2.1 Luật nhận tin nhắn

- [ ] Direct message:
  - [ ] Nếu `zalo_enabled = true` và `zalo_auto_reply = true` thì trả lời
- [ ] Group chat:
  - [ ] Chỉ trả lời khi có `@mention`
  - [ ] Chỉ trả lời nếu group nằm trong scope cho phép
- [ ] Không xử lý tin nhắn do chính tài khoản Zalo của bot gửi ra
- [ ] Không xử lý event không phải message text ở MVP

### 2.2 Scope nhóm

- [x] Hỗ trợ `all_groups`
- [x] Hỗ trợ `selected_groups`
- [x] Allowlist lưu theo `threadId`
- [x] Có flow lấy danh sách nhóm từ `openzca group list`
- [x] Map được tối thiểu `threadId + tên nhóm` để hiển thị cho user chọn
- [x] Có nút `Làm mới danh sách nhóm`
- [x] Có fallback nhập tay `threadId` nếu không load được danh sách
- [x] Nếu scope là `selected_groups`, group không nằm trong allowlist phải bị bỏ qua

### 2.3 Luật trả lời

- [ ] Ưu tiên gửi `typing` trước khi chạy Codex
- [ ] Sau khi có kết quả AI, gửi `1` tin nhắn hoàn chỉnh hoặc vài chunk nhỏ
- [ ] Không cố giả lập `edit message` như Telegram
- [ ] Có throttle nếu phải split chunk

## 3) Tạo `zalo_models.py`

File:
- [x] Tạo [zalo_models.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_models.py)

Checklist:
- [ ] Định nghĩa schema nội bộ cho inbound event
- [ ] Có các field tối thiểu:
  - [ ] `thread_id`
  - [ ] `sender_id`
  - [ ] `chat_type`
  - [ ] `content`
  - [ ] `mentions`
  - [ ] `timestamp`
  - [ ] `message_id`
  - [ ] `raw_payload`
- [ ] Có helper normalize raw JSON từ `openzca`
- [ ] Có helper xác định DM hay group
- [ ] Có helper xác định mention bot

## 4) Tạo `zalo_bot_service.py`

File:
- [x] Tạo [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)

### 4.1 Core responsibilities

- [x] Start listener `openzca`
- [x] Stop listener `openzca`
- [ ] Đọc stream JSON raw từng dòng
- [ ] Parse event về schema nội bộ
- [ ] Lọc event hợp lệ cho bot
- [ ] Gọi `CodexRuntimeBridge`
- [ ] Gửi phản hồi text về Zalo
- [x] Quản lý watchdog/restart cơ bản

### 4.2 Public APIs

- [x] Implement `start()`
- [x] Implement `stop()`
- [x] Implement `is_running()`
- [x] Implement `get_status()`
- [x] Implement `restart()`

### 4.2.1 Listener runtime status

- [x] Tách `listener_state` khỏi `login_state`
- [ ] Có các state tối thiểu:
  - [x] `stopped`
  - [x] `starting`
  - [x] `running`
  - [x] `restarting`
  - [x] `crashed`
- [x] Có `last_started_at`
- [x] Có `last_stopped_at`
- [x] Có `last_error`
- [x] Có `restart_count`

### 4.3 Listener process

- [ ] Dùng command:
  - [x] `openzca listen --supervised --raw --keep-alive --profile omnimind`
- [x] Dùng absolute path binary local
- [x] Inject `OPENZCA_HOME`
- [x] Chạy nền không block UI
- [x] Capture stdout/stderr
- [x] Có kill/cleanup rõ khi stop app
- [x] Có thể start lại listener khi app khởi động lại nếu config bật bot

### 4.4 Single-listener lock

- [x] Không cho chạy chồng nhiều listener cùng profile
- [x] Có in-memory lock hoặc state guard
- [x] Nếu đã chạy thì `start()` không spawn thêm process mới

### 4.5 Watchdog tối thiểu cho Phase 3

- [x] Nếu listener chết bất thường thì cập nhật `listener_state`
- [x] Có thể `restart()` listener bằng tay từ UI/app
- [ ] Không restart loop vô hạn trong Phase 3
- [ ] Không tự restart nếu `login_state` không còn usable
- [ ] Ghi rõ trong code: watchdog/backoff nâng cao để Phase 4

## 5) Parse raw event và routing

Checklist:
- [ ] Xác định dạng JSON thực tế từ `openzca listen --raw`
- [ ] Parse an toàn từng dòng, bỏ qua line không hợp lệ
- [ ] Lọc chỉ lấy event loại message hỗ trợ ở MVP
- [ ] Map đúng `threadId`
- [ ] Map đúng `senderId`
- [ ] Map đúng `chatType`
- [ ] Map đúng `content`
- [ ] Map đúng `mentions`
- [ ] Map đúng `timestamp`
- [ ] Cố gắng map `message_id` nếu raw payload có field tương ứng
- [ ] Lưu `raw_payload` cho debug

## 6) Dedupe và anti-loop

Checklist:
- [ ] Thiết kế idempotency key tối thiểu:
  - [ ] `thread_id`
  - [ ] `message_id` nếu có
  - [ ] fallback `sender_id + timestamp + content`
- [ ] Có TTL cache cho dedupe
- [ ] Reconnect không làm xử lý lại message cũ
- [ ] Bot không reply vào tin nhắn của chính nó
- [ ] Nếu parse thiếu `message_id`, vẫn có fallback đủ dùng cho MVP

## 7) Tích hợp với AI core hiện tại

Checklist:
- [ ] Rà soát cách `TelegramBotService` gọi `CodexRuntimeBridge`
- [ ] Tái sử dụng `CodexRuntimeBridge`
- [ ] Tái sử dụng `MemoryManager`
- [ ] Tái sử dụng `SkillManager` nếu luồng Telegram đang dùng
- [ ] Không copy/paste logic AI lớn nếu có thể gọi qua bridge sẵn có
- [ ] Xác định cách ghép prompt Zalo vào prompt nền

### 7.1 Prompt nguyên tắc Zalo

- [ ] Thêm cấu hình `zalo_prompt_principles`
- [ ] Ghép prompt này vào luồng trả lời Zalo
- [ ] Không ảnh hưởng prompt Telegram
- [ ] Có default rỗng hoặc prompt nhẹ nhàng

## 8) Gửi phản hồi Zalo

Checklist:
- [ ] Implement helper gửi text:
  - [ ] DM
  - [ ] Group
- [ ] Implement helper gửi `typing`
- [ ] Xác định rõ cờ group khi gửi command
- [ ] Nếu text dài, split chunk hợp lý
- [ ] Có throttle cơ bản giữa các chunk
- [ ] Nếu gửi lỗi, log rõ nguyên nhân

### 8.1 Command checklist

- [ ] `typing` trước khi gọi Codex
- [ ] `msg send` sau khi có kết quả
- [ ] Không gửi `typing` lặp vô hạn
- [ ] Nếu `typing` thất bại, vẫn cho phép gửi text bình thường

## 9) Config cần bổ sung

File:
- [ ] Sửa [config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)

### 9.1 Config keys

- [x] Thêm `zalo_enabled`
- [x] Thêm `zalo_auto_reply`
- [x] Thêm `zalo_group_scope`
- [x] Thêm `zalo_group_allowlist`
- [x] Thêm `zalo_listener_state`
- [x] Thêm `zalo_listener_last_error`
- [x] Thêm `zalo_listener_last_started_at`
- [x] Thêm `zalo_listener_last_stopped_at`
- [x] Thêm `zalo_listener_restart_count`
- [x] Thêm `zalo_prompt_principles`
- [x] Thêm `zalo_reply_mode`

### 9.2 Defaults

- [ ] Default `zalo_enabled = false`
- [ ] Default `zalo_auto_reply = true`
- [ ] Default `zalo_group_scope = all`
- [ ] Default `zalo_group_allowlist = []`
- [ ] Default `zalo_reply_mode = dm_and_mention`
- [ ] Default `zalo_prompt_principles = ""`

### 9.3 Helpers

- [x] Thêm helper `get_zalo_bot_config()`
- [x] Thêm helper save/load allowlist nhóm
- [x] Parse JSON allowlist an toàn
- [x] Thêm helper get/set listener status

## 10) UI cấu hình trong `auth_page.py`

File:
- [ ] Sửa [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

### 10.1 Bot controls

- [ ] Thêm công tắc `Bật bot Zalo`
- [x] Thêm công tắc `Tự động trả lời`
- [x] Thêm trạng thái bot `Đang chạy / Đã dừng`
- [x] Thêm nút `Khởi động lại` listener nếu cần

### 10.2 Group scope controls

- [x] Thêm lựa chọn `Tất cả nhóm`
- [x] Thêm lựa chọn `Nhóm được chọn`
- [x] Thêm UI list nhóm load từ Zalo để chọn
- [x] Có fallback nhập tay `threadId` hoặc edit danh sách thô

### 10.3 Prompt config

- [x] Thêm vùng text `Nguyên tắc trả lời Zalo`
- [x] Có save/load từ config
- [x] Không ảnh hưởng cấu hình Telegram

### 10.4 UX rules

- [ ] Nếu chưa `Connected`, disable start bot
- [ ] Nếu bot đang chạy, không cho bấm start lần nữa
- [x] Nếu đang start/stop bot, không block UI thread
- [x] Hiển thị riêng `Đăng nhập Zalo` và `Bộ lắng nghe Zalo`

## 11) Dashboard integration

Files:
- [ ] Sửa [dashboard_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/dashboard_manager.py)
- [ ] Sửa [dashboard_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/dashboard_page.py)

Checklist:
- [ ] Expose bot runtime status
- [ ] Expose listener running state
- [ ] Expose `listener_state`
- [ ] Expose last error nếu có
- [ ] Thêm card Zalo bot read-only hoặc control tối thiểu
- [ ] Thêm nút `Start/Stop` nếu dashboard là nơi điều khiển chính

## 12) Tích hợp app lifecycle

File:
- [ ] Sửa [main.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/main.py)

Checklist:
- [x] Khởi tạo `ZaloBotService`
- [ ] Restore trạng thái theo config khi app start
- [ ] Nếu `zalo_enabled=false`, không auto start listener
- [x] Nếu `zalo_enabled=true` và `login_state=connected`, auto start listener khi app mở lại
- [ ] Khi app đóng, stop listener sạch sẽ
- [ ] Không làm ảnh hưởng lifecycle Telegram hiện có

## 13) Error handling checklist

- [ ] Listener process chết bất ngờ
- [ ] Listener restart bằng tay khi đang ở `crashed/stopped`
- [ ] Raw JSON parse lỗi
- [ ] Message thiếu field quan trọng
- [ ] `typing` command lỗi
- [ ] `msg send` lỗi
- [ ] `CodexRuntimeBridge` trả lỗi
- [ ] Timeout khi AI trả lời quá lâu
- [ ] Dedupe cache lỗi hoặc miss
- [ ] Group event không có mention metadata rõ ràng

## 14) Logging checklist

- [ ] Log start/stop listener
- [ ] Log listener restart
- [ ] Log inbound message tối thiểu
- [ ] Log outbound response tối thiểu
- [ ] Log skipped message reason:
  - [ ] not connected
  - [ ] auto_reply off
  - [ ] group not allowed
  - [ ] no mention
  - [ ] self message
  - [ ] duplicate
- [ ] Có file log riêng hoặc prefix log rõ cho Zalo bot

Phase 3 chưa bắt buộc:
- [ ] JSONL dead-letter log hoàn chỉnh

## 15) Automated test checklist

- [ ] Unit test parse raw JSON event
- [ ] Unit test detect DM vs group
- [ ] Unit test detect mention
- [ ] Unit test dedupe key
- [ ] Unit test routing rule:
  - [ ] DM được trả lời
  - [ ] group không mention thì bỏ qua
  - [ ] group mention nhưng không thuộc allowlist thì bỏ qua
  - [ ] group mention thuộc allowlist thì được trả lời
- [ ] Unit test build command gửi message
- [ ] Unit test start guard không spawn nhiều listener

## 16) Manual verification checklist

### Direct message

- [ ] Login Zalo thành công
- [ ] Bật bot Zalo
- [ ] Gửi DM từ thiết bị khác
- [ ] Bot gửi `typing`
- [ ] Bot trả lời text thành công
- [ ] Tắt `auto reply`, DM không còn bị trả lời

### Group mention

- [ ] Thêm tài khoản Zalo bot vào group
- [ ] Với `all_groups`, mention bot thì bot trả lời
- [ ] Không mention bot thì bot không trả lời
- [ ] Với `selected_groups`, group ngoài allowlist không được trả lời
- [ ] Với `selected_groups`, group trong allowlist được trả lời

### Stability

- [ ] Restart app, bot restore trạng thái đúng
- [ ] Reboot máy, OmniMind auto-start thì listener cũng auto-start lại đúng theo config
- [ ] Reconnect listener không gây reply trùng
- [ ] Stop bot thì không còn nhận/trả lời message

## 17) Definition of Done theo file

### [zalo_models.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_models.py)

- [ ] Có schema event nội bộ rõ ràng
- [ ] Parse helper đủ dùng cho MVP

### [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)

- [ ] Start/stop/listen/send hoạt động
- [ ] Có dedupe
- [ ] Có watchdog cơ bản
- [ ] Có anti-self-reply

### [config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)

- [ ] Có đủ config keys và helper cho bot phase

### [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

- [ ] Có UI bật/tắt bot
- [ ] Có UI prompt Zalo
- [ ] Có UI scope nhóm
- [ ] Không block UI thread

### [main.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/main.py)

- [ ] Lifecycle bot tích hợp ổn

## 18) Ghi chú cho Phase 4

Không làm ở phase này, nhưng cần giữ khả năng mở rộng:
- [ ] Media/file inbound-outbound
- [ ] Permission-confirm flow qua Zalo
- [ ] Structured dead-letter JSONL
- [ ] Watchdog/restart policy mạnh hơn
- [ ] Restart backoff nhiều cấp
- [ ] Heartbeat timeout và stale detection rõ ràng
- [ ] Auto restart sau crash nhiều lần với cooldown
- [ ] Distinguish `degraded` / `crashed` / `restarting`
- [ ] Retry/rate-limit queue
