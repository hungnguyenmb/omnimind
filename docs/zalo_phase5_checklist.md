# OmniMind Zalo Phase 5 Checklist

Ngày tạo: `2026-03-11`

Tài liệu này dùng để triển khai và theo dõi tiến độ `Phase 5 - Observability + Operator Tools + Real-world Verification` cho tích hợp Zalo trong `projects/omnimind`.

Trạng thái hiện tại:
- Phase này đang được giữ như backlog tùy chọn.
- Chưa ưu tiên triển khai ngay.
- Hướng phát triển kế tiếp đã được chuyển sang `Media Support`.

Tham chiếu gốc:
- [zalo_openzca_master_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_openzca_master_plan.md)
- [zalo_phase4_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_phase4_checklist.md)

## Mục tiêu Phase 5

Kết thúc Phase 5, OmniMind phải:
- Có công cụ quan sát dữ liệu Zalo theo từng thread mà không cần mở DB thủ công.
- Có thể xem context thực tế đang được đưa vào Codex để debug chất lượng trả lời.
- Có thể resync lịch sử gần nhất của một thread khi context local bị thiếu hoặc bẩn.
- Có thể rebuild summary của một thread khi policy prompt/sanitize thay đổi.
- Có thể xem và chẩn đoán các lần gửi tin nhắn thất bại.
- Có thể retry lại phản hồi gần nhất bị fail sau khi nguyên nhân được xử lý.
- Có trạng thái listener/watchdog rõ hơn để phục vụ vận hành.
- Có checklist test thực chiến để xác nhận chất lượng DM/group trước khi coi tích hợp là ổn định.

Phase 5 không ưu tiên:
- thêm media/file/sticker
- thêm manual cleanup button như hạng mục chính
- nhiều tài khoản Zalo song song
- refactor lớn AI core

## Exit Criteria

Chỉ được xem là hoàn tất Phase 5 khi thỏa cả các điều kiện:
- Có UI hoặc màn debug để xem chi tiết một `thread_id` Zalo.
- Có thể xem:
  - recent raw messages
  - latest summary
  - facts
  - lần bootstrap cuối
  - lần reply cuối
- Có thể trigger `resync recent history` cho một thread cụ thể.
- Có thể trigger `rebuild summary` cho một thread cụ thể.
- Có thể xem ít nhất một bản preview context/prompt đang đưa vào Codex.
- Có thể xem log `failed send` và biết chính xác lỗi thực tế của `openzca msg send`.
- Có thể retry lại outbound thất bại theo cách an toàn.
- Có checklist test tay bao phủ DM, group mention, fail send, reconnect, bootstrap thiếu dữ liệu.

## 1) Chốt phạm vi Phase 5

- [ ] Xác nhận Phase 5 tập trung vào observability + operator tools + thực chiến
- [ ] Xác nhận manual cleanup không phải hạng mục chính của Phase 5
- [ ] Xác nhận vẫn giữ auto cleanup nền của Phase 4
- [ ] Xác nhận chưa làm media/file nâng cao trong phase này
- [ ] Xác nhận chưa làm multi-account Zalo

## 2) Thread Inspector

File dự kiến:
- [ ] Sửa [dashboard_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/dashboard_manager.py)
- [ ] Sửa [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)
- [ ] Nếu cần, thêm helper trong [zalo_memory_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_memory_manager.py)

Checklist:
- [ ] Có danh sách thread/group Zalo đã lưu local
- [ ] Có thể filter theo:
  - [ ] `group`
  - [ ] `dm`
  - [ ] `thread_id`
  - [ ] tên hiển thị
- [ ] Mỗi thread hiển thị tối thiểu:
  - [ ] `thread_id`
  - [ ] `chat_type`
  - [ ] `display_name`
  - [ ] `last_message_at`
  - [ ] `last_bootstrap_at`
  - [ ] `bootstrap_done`
  - [ ] số lượng raw messages local
  - [ ] số lượng summaries
  - [ ] số lượng facts

## 3) Thread Detail View

Checklist:
- [ ] Có panel xem chi tiết một thread
- [ ] Có recent messages của thread
- [ ] Có latest summary của thread
- [ ] Có recent summaries của thread
- [ ] Có facts/preferences của thread
- [ ] Có metadata:
  - [ ] `last_message_at`
  - [ ] `last_bootstrap_at`
  - [ ] `bootstrap_done`
  - [ ] `last_reply_at` nếu có
- [ ] Có hiển thị chiều `inbound/outbound`
- [ ] Không hiển thị raw JSON quá thô mặc định
- [ ] Có chế độ xem raw payload nếu cần debug sâu

## 4) Context / Prompt Preview

File dự kiến:
- [ ] Sửa [zalo_prompt_builder.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_prompt_builder.py)
- [ ] Sửa [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [ ] Sửa UI ở [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

Checklist:
- [ ] Có helper build preview context cho một thread
- [ ] Có thể xem riêng từng khối:
  - [ ] `Nguyên tắc trả lời Zalo`
  - [ ] latest summary
  - [ ] recent summaries
  - [ ] facts
  - [ ] recent turns
  - [ ] bundle text hiện tại hoặc sample input
- [ ] Có preview prompt cuối cùng trước khi gửi vào Codex
- [ ] Có hiển thị `context_char_used`
- [ ] Có cách copy prompt preview để debug ngoài app nếu cần
- [ ] Không đưa `owner_work_rules` hay `assistant_profile` vào preview Zalo

## 5) Resync Recent History

File dự kiến:
- [ ] Sửa [openzca_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/openzca_manager.py)
- [ ] Sửa [zalo_memory_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_memory_manager.py)
- [ ] Sửa UI ở [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

Checklist:
- [ ] Có action `Resync recent history` cho một thread
- [ ] Có action cho cả DM và group
- [ ] Có thể chọn số lượng history cần sync lại
- [ ] Khi resync:
  - [ ] gọi lại `openzca msg recent`
  - [ ] map sạch về schema local
  - [ ] dedupe dữ liệu cũ
  - [ ] cập nhật `last_bootstrap_at`
- [ ] Có status rõ:
  - [ ] đang sync
  - [ ] thành công
  - [ ] thất bại
- [ ] Có log rõ số message import được

## 6) Rebuild Summary

File dự kiến:
- [ ] Sửa [zalo_memory_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_memory_manager.py)
- [ ] Sửa UI ở [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

Checklist:
- [ ] Có action `Rebuild summary` cho một thread
- [ ] Có option rebuild:
  - [ ] chỉ summary mới nhất
  - [ ] hoặc rebuild toàn bộ summary gần đây của thread
- [ ] Khi rebuild:
  - [ ] dùng raw messages local hiện có
  - [ ] sanitize lại dữ liệu cũ bẩn
  - [ ] loại bỏ JSON rác
  - [ ] loại bỏ giọng bot cũ nếu còn
- [ ] Có log kết quả rebuild
- [ ] Summary mới không làm mất khả năng truy vết `from_ts/to_ts`

## 7) Failed Send Diagnostics

File dự kiến:
- [ ] Sửa [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [ ] Sửa [openzca_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/openzca_manager.py)
- [ ] Thêm UI viewer trong [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

Checklist:
- [ ] Có viewer cho `zalo_dead_letter.jsonl`
- [ ] Hiển thị các case:
  - [ ] `send_response_failed`
  - [ ] `bootstrap_history_failed`
  - [ ] `thread_bundle_failed`
- [ ] Mỗi failed send hiển thị tối thiểu:
  - [ ] `thread_id`
  - [ ] `chat_type`
  - [ ] `message_id`
  - [ ] `chunk_preview`
  - [ ] lỗi thực tế từ CLI
  - [ ] thời gian lỗi
- [ ] Nếu send fail do CLI parse/option:
  - [ ] log rõ command shape hoặc rule nhận diện
- [ ] Nếu send fail do auth/session:
  - [ ] trigger re-check auth state

## 8) Retry Last Failed Send

Checklist:
- [ ] Có thể retry lại failed send gần nhất
- [ ] Retry không tạo duplicate vô hạn
- [ ] Có idempotency guard cho retry
- [ ] Có cảnh báo nếu nội dung retry quá cũ hoặc thread đã đổi ngữ cảnh quá xa
- [ ] Retry thành công thì cập nhật log tương ứng
- [ ] Retry thất bại lần nữa thì giữ lại dấu vết lỗi mới

## 9) Listener / Watchdog Diagnostics

File dự kiến:
- [ ] Sửa [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [ ] Sửa [zalo_connection_monitor.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_connection_monitor.py)
- [ ] Sửa UI ở [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

Checklist:
- [ ] Hiển thị rõ:
  - [ ] `listener_state`
  - [ ] `restart_count`
  - [ ] `last_error`
  - [ ] `last_started_at`
  - [ ] `last_heartbeat_at`
- [ ] Có nút:
  - [ ] `Start listener`
  - [ ] `Stop listener`
  - [ ] `Restart listener`
- [ ] Nếu listener crash liên tục:
  - [ ] state chuyển `degraded` hoặc `crashed`
  - [ ] có log rõ lý do gần nhất
- [ ] Có thể xem lifecycle events gần đây từ listener

## 10) Group / Mention Diagnostics

Checklist:
- [ ] Có cách xem một inbound group message có:
  - [ ] đúng `thread_id`
  - [ ] đúng `sender_id`
  - [ ] có `mentions`
  - [ ] có match `self_user_id`
- [ ] Có thể thấy rõ vì sao một tin bị bỏ qua:
  - [ ] `no_mention`
  - [ ] `group_not_allowed`
  - [ ] `auto_reply_off`
  - [ ] `bot_disabled`
  - [ ] `self_message`
- [ ] Có log hoặc UI cho skip reason gần đây

## 11) Config Tunables cho vận hành

Checklist:
- [ ] Có UI hoặc config expose cho:
  - [ ] `bootstrap_count`
  - [ ] `thread_debounce_ms`
  - [ ] `typing_interval`
  - [ ] `group_scope`
  - [ ] `group_allowlist`
  - [ ] `zalo_model`
- [ ] Có validation để không cho nhập giá trị quá nguy hiểm
- [ ] Có nút restore default cho các tunables này

## 12) Logging / Diagnostics Hygiene

Checklist:
- [ ] Chuẩn hóa JSONL logs:
  - [ ] inbound
  - [ ] outbound
  - [ ] dead-letter
  - [ ] listener runtime
- [ ] Có timestamp rõ trong mỗi bản ghi
- [ ] Không log lộ dữ liệu nhạy cảm của máy local
- [ ] Không log prompt đầy đủ mặc định nếu không cần
- [ ] Nếu có prompt preview log, phải là opt-in hoặc debug mode

## 13) Test Thực Chiến

### 13.1 DM tests

- [ ] DM mới hoàn toàn, chưa có history local
- [ ] DM đã có history local
- [ ] DM gửi 3-4 tin liên tiếp
- [ ] DM có message bắt đầu bằng `-`
- [ ] DM bot trả lời dài thành nhiều chunk
- [ ] DM fail send và retry lại

### 13.2 Group tests

- [ ] Group không mention bot -> bot không trả lời
- [ ] Group có mention bot -> bot trả lời
- [ ] Group có context do chính tài khoản Zalo của chủ bot gửi trước đó
- [ ] Group có người khác xen giữa nhiều message
- [ ] Group có message quote/reply context
- [ ] Group response bắt đầu bằng `-` vẫn gửi thành công

### 13.3 Reliability tests

- [ ] Mất session auth -> state cập nhật đúng
- [ ] Listener restart sau khi stop/start
- [ ] Send fail được ghi dead-letter
- [ ] Retry failed send hoạt động
- [ ] Resync history giúp sửa context thiếu
- [ ] Rebuild summary giúp loại bỏ summary bẩn

## 14) Definition of Done

Phase 5 chỉ được coi là xong khi:
- [ ] Có thể debug một thread/group sai ngữ cảnh mà không cần mở SQLite thủ công
- [ ] Có thể biết chính xác bot đã lấy context gì trước khi trả lời
- [ ] Có thể resync hoặc rebuild dữ liệu thread ngay trong app
- [ ] Có thể biết chính xác send fail do đâu
- [ ] Có thể retry ít nhất một failed send theo cách an toàn
- [ ] Bộ checklist test tay DM/group đã chạy và ghi lại kết quả
