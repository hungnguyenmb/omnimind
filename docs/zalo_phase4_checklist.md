# OmniMind Zalo Phase 4 Checklist

Ngày tạo: `2026-03-11`

Tài liệu này dùng để triển khai và theo dõi tiến độ `Phase 4 - Reliability Hardening + Thread Memory` cho tích hợp Zalo trong `projects/omnimind`.

Tham chiếu gốc:
- [zalo_openzca_master_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_openzca_master_plan.md)
- [zalo_phase3_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_phase3_checklist.md)

## Mục tiêu Phase 4

Kết thúc Phase 4, OmniMind phải:
- Có memory riêng theo từng `thread_id` Zalo, không chỉ dùng memory chung của assistant.
- Có thể bootstrap context lần đầu bằng `openzca msg recent`.
- Có cơ chế gom nhiều tin nhắn gần nhau trong cùng thread để tránh trả lời rời rạc.
- Có summary theo thread để bot hiểu ngữ cảnh nhiều ngày mà không phải query full raw history.
- Có retention policy:
  - raw messages có ngưỡng `3 ngày`, nhưng chỉ xóa khi thread đã có summary usable
  - thread summaries giữ `30 ngày`
- Có index để query nhanh trên SQLite.
- Có prompt architecture rõ ràng, trong đó khối `Nguyên tắc trả lời Zalo` là một phần chính thức của prompt builder.

Phase 4 chưa bao gồm:
- media/file nâng cao
- voice/sticker
- analytics UI nâng cao
- multi-account Zalo

## Exit Criteria

Chỉ được xem là hoàn tất Phase 4 khi thỏa cả các điều kiện:
- Thread mới chưa có dữ liệu local vẫn bootstrap được context bằng `msg recent` hoặc fallback sạch nếu API lỗi.
- Khi user gửi nhiều tin liên tiếp, bot không bỏ sót ý và không spawn nhiều request Codex chồng nhau cho cùng thread.
- Query context cho thread cũ vẫn nhanh, không scan toàn bảng raw messages.
- Raw message cũ hơn `3 ngày` chỉ bị dọn khi thread đã có summary usable.
- Summary cũ hơn `30 ngày` được dọn tự động.
- `zalo_threads` vẫn giữ `thread_id` và metadata sống lâu, không bị xóa cùng retention raw.
- Prompt runtime luôn có thứ tự ưu tiên hợp lý:
  - assistant identity
  - global rules
  - `Nguyên tắc trả lời Zalo`
  - thread summary
  - thread facts
  - recent turns
  - current bundled messages

## 1) Chốt phạm vi

- [ ] Xác nhận Phase 4 tập trung vào reliability + thread memory
- [ ] Xác nhận không refactor lớn AI core ngoài phần cần thiết cho Zalo
- [ ] Xác nhận retention policy:
  - [x] raw messages có ngưỡng `3 ngày`
  - [x] raw chỉ bị xóa khi thread đã có summary usable
  - [x] summaries = `30 ngày`
- [x] Xác nhận facts/preferences giữ lâu hơn raw
- [x] Xác nhận `msg recent` chỉ là bootstrap/fallback, không dùng làm nguồn query chính cho mọi lượt chat

## 2) Nghiên cứu `openzca msg recent`

Checklist:
- [ ] Xác nhận cú pháp thực tế:
  - [ ] DM: `openzca msg recent <threadId> -n <N> --json`
  - [ ] Group: `openzca msg recent <threadId> --group -n <N> --json`
- [ ] Xác nhận format JSON trả về trên máy thật
- [ ] Xác nhận field tối thiểu cần map:
  - [ ] `message_id`
  - [ ] `sender_id`
  - [ ] `content`
  - [ ] `timestamp`
  - [ ] chiều inbound/outbound nếu có thể suy luận
- [ ] Xác nhận timeout hợp lý cho bootstrap history
- [ ] Xác nhận fallback behavior khi CLI trả `fetch failed`
- [ ] Xác nhận có cần cấu hình thêm:
  - [ ] `OPENZCA_RECENT_USER_MAX_PAGES`
  - [ ] `OPENZCA_RECENT_GROUP_MAX_PAGES`

## 3) Thiết kế DB riêng cho Zalo

File:
- [ ] Sửa [db_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/database/db_manager.py)

### 3.1 Bảng `zalo_threads`

- [ ] Tạo bảng `zalo_threads`
- [x] Tạo bảng `zalo_threads`
- [x] `zalo_threads` là metadata sống lâu, không xóa theo retention raw
- [ ] Có các cột tối thiểu:
  - [ ] `thread_id`
  - [ ] `chat_type`
  - [ ] `display_name`
  - [ ] `participant_hint`
  - [ ] `last_message_at`
  - [ ] `last_bootstrap_at`
  - [ ] `bootstrap_done`
  - [ ] `created_at`
  - [ ] `updated_at`

### 3.2 Bảng `zalo_messages`

- [ ] Tạo bảng `zalo_messages`
- [x] Tạo bảng `zalo_messages`
- [ ] Có các cột tối thiểu:
  - [ ] `id`
  - [ ] `thread_id`
  - [ ] `chat_type`
  - [ ] `sender_id`
  - [ ] `message_id`
  - [ ] `direction`
  - [ ] `content`
  - [ ] `mentions_json`
  - [ ] `raw_json`
  - [ ] `timestamp`
  - [ ] `created_at`

### 3.3 Bảng `zalo_thread_summaries`

- [ ] Tạo bảng `zalo_thread_summaries`
- [x] Tạo bảng `zalo_thread_summaries`
- [ ] Có các cột tối thiểu:
  - [ ] `id`
  - [ ] `thread_id`
  - [ ] `summary_text`
  - [ ] `from_ts`
  - [ ] `to_ts`
  - [ ] `message_count`
  - [ ] `source`
  - [ ] `updated_at`

### 3.4 Bảng `zalo_thread_facts`

- [ ] Tạo bảng `zalo_thread_facts`
- [x] Tạo bảng `zalo_thread_facts`
- [ ] Có các cột tối thiểu:
  - [ ] `id`
  - [ ] `thread_id`
  - [ ] `fact`
  - [ ] `confidence`
  - [ ] `hit_count`
  - [ ] `last_seen_at`
  - [ ] `created_at`
  - [ ] `updated_at`

## 4) Indexing để query nhanh

- [x] Tạo index `zalo_messages(thread_id, timestamp DESC)`
- [x] Tạo index `zalo_messages(thread_id, message_id)`
- [x] Tạo index `zalo_messages(thread_id, sender_id, timestamp DESC)`
- [x] Tạo index `zalo_threads(last_message_at DESC)`
- [x] Tạo index `zalo_thread_summaries(thread_id, updated_at DESC)`
- [x] Nếu cần, tạo unique constraint cho `(thread_id, message_id)`

## 5) Tạo lớp memory manager riêng cho Zalo

File:
- [ ] Tạo [zalo_memory_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_memory_manager.py)
- [x] Tạo [zalo_memory_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_memory_manager.py)

Checklist:
- [x] Có helper upsert `zalo_threads`
- [x] Có helper append `zalo_messages`
- [x] Có helper get recent raw messages theo `thread_id`
- [x] Có helper get latest summary theo `thread_id`
- [x] Có helper get summaries trong `30 ngày`
- [x] Có helper get/update thread facts
- [x] Có helper build thread context:
  - [x] recent turns
  - [x] summary
  - [x] facts
- [x] Không query full history nếu không cần

## 6) Bootstrap history lần đầu bằng `msg recent`

File:
- [ ] Sửa [openzca_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/openzca_manager.py)
- [ ] Sửa [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)

Checklist:
- [x] Thêm helper `get_recent_messages(thread_id, is_group, count)`
- [x] Hỗ trợ `--json`
- [x] Có timeout riêng cho history bootstrap
- [ ] Nếu thread local chưa có dữ liệu:
  - [x] gọi `msg recent`
  - [x] map về schema local
  - [x] lưu vào `zalo_messages`
  - [x] đánh dấu `bootstrap_done`
- [ ] Nếu `msg recent` fail:
  - [x] log warning
  - [x] không fail luôn luồng trả lời
  - [x] vẫn trả lời bằng message hiện tại

## 7) Burst aggregation theo thread

File:
- [ ] Sửa [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)

Checklist:
- [x] Thiết kế buffer theo `thread_id`
- [x] Có debounce window, ví dụ `1.5-3 giây`
- [ ] Nếu user gửi nhiều tin gần nhau:
  - [x] gom vào một bundle
  - [x] chỉ gọi Codex một lần
- [x] Có metadata để biết bundle gồm bao nhiêu message
- [ ] Khi bot đang xử lý một thread:
  - [x] tin mới của đúng thread đi vào pending buffer
  - [x] không spawn request Codex mới chồng lên

## 8) Single-flight per thread

Checklist:
- [x] Mỗi `thread_id` chỉ có tối đa `1` request Codex active
- [x] Có lock hoặc state map theo thread
- [ ] Sau khi request hiện tại xong:
  - [x] nếu buffer thread còn message mới thì chạy vòng tiếp theo
- [ ] Thread A không chặn Thread B hoàn toàn nếu muốn giữ concurrency tối thiểu

## 9) Rolling summary theo thread

Checklist:
- [ ] Chốt policy sinh summary:
  - [ ] theo số lượng tin mới
  - [ ] hoặc theo char budget / time window
- [x] Summary phải gắn `thread_id`
- [x] Summary phải có `from_ts` và `to_ts`
- [x] Summary không được ghi đè mất hoàn toàn summary cũ
- [x] Có helper lấy `latest summary`
- [ ] Có helper lấy `1-2 summaries gần nhất`

## 10) Prompt architecture cho Zalo

File:
- [ ] Tạo [zalo_prompt_builder.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_prompt_builder.py)
- [ ] Hoặc refactor sạch trong [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [x] Tạo [zalo_prompt_builder.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_prompt_builder.py)
- [x] Hoặc refactor sạch trong [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)

Checklist:
- [x] Có block `Assistant identity`
- [x] Có block `Global working rules`
- [x] Có block `Nguyên tắc trả lời Zalo`
- [x] Có block `Thread summary`
- [x] Có block `Thread facts`
- [x] Có block `Recent conversation turns`
- [x] Có block `Current bundled messages`
- [x] Thứ tự ưu tiên được giữ ổn định
- [x] Không nhét toàn bộ raw history vào prompt

## 11) Retention và cleanup jobs

Checklist:
- [x] Tạo cleanup job cho `zalo_messages`
- [x] Chỉ xét xóa raw cũ hơn `3 ngày`
- [x] Tạo cleanup job cho `zalo_thread_summaries`
- [x] Xóa summary cũ hơn `30 ngày`
- [ ] Trước khi xóa raw:
  - [x] đảm bảo thread đã có summary usable
  - [x] không xóa raw của thread chưa từng được summarize
  - [x] không xóa `zalo_threads`
- [x] Cleanup job chạy định kỳ, không block UI
- [x] Ghi rõ trong code/doc: manual cleanup button không làm ở Phase 4, để sang Phase 5

## 12) Logging và dead-letter

Checklist:
- [ ] Ghi log inbound/outbound JSONL cho Zalo
- [ ] Ghi dead-letter cho:
  - [ ] parse lỗi
  - [ ] bootstrap history lỗi
  - [ ] send message lỗi
- [ ] Có enough metadata để replay/debug theo `thread_id`

## 13) Config cần bổ sung

File:
- [ ] Sửa [config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)

Checklist:
- [x] Thêm retention config nếu cần:
  - [x] `zalo_raw_retention_days = 3`
  - [x] `zalo_summary_retention_days = 30`
- [x] Nếu cần, thêm cờ policy:
  - [x] `zalo_delete_raw_only_when_summarized = true`
- [x] Thêm config debounce nếu cần:
  - [x] `zalo_thread_debounce_ms`
- [x] Thêm config bootstrap recent count nếu cần:
  - [x] `zalo_recent_bootstrap_count`

## 14) Verification Plan

### 14.1 Manual tests

- [ ] Thread mới hoàn toàn:
  - [ ] bot bootstrap được context gần nhất bằng `msg recent`
  - [ ] nếu `msg recent` lỗi, bot vẫn trả lời được
- [ ] User gửi 3-5 tin liên tục:
  - [ ] bot gom ý đúng
  - [ ] không trả lời từng mảnh rời rạc
- [ ] Thread đã có lịch sử vài ngày:
  - [ ] bot vẫn hiểu ngữ cảnh nhanh
  - [ ] không bị chậm rõ rệt
- [ ] Sau hơn `3 ngày`:
  - [ ] raw cũ chỉ bị dọn nếu thread đã có summary usable
  - [ ] summary vẫn còn
  - [ ] bot vẫn có continuity cơ bản
- [ ] `Nguyên tắc trả lời Zalo` được phản ánh rõ trong câu trả lời

### 14.2 Negative tests

- [ ] `msg recent` trả lỗi `fetch failed`
- [ ] raw history có message trùng
- [ ] summary job bị lỗi giữa chừng
- [ ] DB lớn lên nhiều thread nhưng query recent turns vẫn nhanh

## 15) Definition of Done

- [ ] Có DB schema riêng cho Zalo thread memory
- [ ] Có index phù hợp
- [ ] Có bootstrap history lần đầu
- [ ] Có burst aggregation theo thread
- [ ] Có single-flight per thread
- [ ] Có rolling summaries
- [ ] Có retention `3 ngày raw có điều kiện / 30 ngày summaries`
- [ ] Prompt builder chính thức có block `Nguyên tắc trả lời Zalo`
- [ ] Manual test pass cho DM và group mention với thread mới và thread cũ
