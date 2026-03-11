# OmniMind Zalo Integration Master Plan

Ngày tạo: `2026-03-11`

## 1) Mục tiêu

Tích hợp bot Zalo vào `projects/omnimind` theo hướng:
- Giữ thay đổi nhỏ nhất lên AI core hiện tại.
- Tái sử dụng tối đa `CodexRuntimeBridge`, `MemoryManager`, `SkillManager`, `ConversationOrchestrator`.
- Hỗ trợ cả `macOS` và `Windows`.
- Cho phép OmniMind tự cài `openzca` local, không phụ thuộc cài đặt global của người dùng.
- Chỉ dùng `1` tài khoản Zalo tại `1` thời điểm cho mỗi máy / mỗi bản OmniMind.

MVP cần đạt:
- Nhận tin nhắn trực tiếp Zalo và tự trả lời bằng Codex.
- Nhận tin nhắn nhóm khi bot bị `@mention`.
- Có cấu hình scope nhóm: `all_groups` hoặc `selected_groups`.
- Có công tắc bật/tắt auto-reply riêng cho Zalo.
- Có prompt nguyên tắc trả lời riêng cho Zalo.
- Có trạng thái login rõ ràng: `Not logged in`, `QR required`, `Connected`, `Re-auth required`.
- Có health check định kỳ và gửi cảnh báo qua Telegram khi Zalo mất kết nối hoặc cần đăng nhập lại.

## 2) Non-goals cho giai đoạn đầu

Chưa làm trong MVP:
- Không hỗ trợ nhiều tài khoản Zalo song song.
- Không stream edit cùng một tin nhắn như Telegram.
- Không ưu tiên media/file nâng cao ở pha đầu.
- Không refactor lớn `TelegramBotService` nếu chưa cần thiết.
- Không phụ thuộc reverse-engineering API Zalo riêng; chỉ đi qua `openzca`.

## 3) Kết luận kiến trúc

### 3.1 Hướng triển khai được chọn

Tạo transport/service mới cho Zalo thay vì sửa AI core:
- `openzca` lo phần kết nối, auth, listen, send message.
- `ZaloBotService` lo phần parse event, lọc điều kiện trả lời, dedupe, gọi runtime bridge.
- `CodexRuntimeBridge` tiếp tục là lớp sinh phản hồi AI.
- `MemoryManager` tiếp tục lưu lịch sử hội thoại.
- `Dashboard/UI` chỉ bổ sung cấu hình và trạng thái.

Lý do:
- Ít sửa logic hiện tại nhất.
- Giữ Telegram chạy độc lập.
- Dễ mở rộng sau này thành giao tiếp Codex qua Zalo hai chiều sâu hơn.

### 3.2 Quy ước session/profile

Chỉ dùng `1 profile` cố định:
- `profile_name = omnimind`

Nguyên tắc:
- `profile` là container session của app, không phải identity của từng tài khoản Zalo.
- Khi user login tài khoản Zalo mới, session cũ bị ghi đè trong cùng profile đó.
- Không sinh profile mới mỗi lần đổi tài khoản.

### 3.3 Cài đặt `openzca`

Không dùng `npm install -g openzca` làm mặc định.

Thay vào đó, OmniMind tự cài local:
- Runtime: `<app_data>/openzca-runtime`
- Session/home: `<app_data>/openzca-home`
- Profile: `omnimind`

Lý do:
- Không làm bẩn môi trường máy.
- Dễ khóa version.
- Dễ repair/reinstall.
- Không bị phụ thuộc `PATH` global.

## 4) Thiết kế cross-platform

### 4.1 App data path

macOS:
- App root: `~/Library/Application Support/OmniMind`
- `openzca-runtime`: `~/Library/Application Support/OmniMind/openzca-runtime`
- `openzca-home`: `~/Library/Application Support/OmniMind/openzca-home`
- log Zalo: `~/Library/Application Support/OmniMind/logs`

Windows:
- App root: `%LOCALAPPDATA%\\OmniMind`
- `openzca-runtime`: `%LOCALAPPDATA%\\OmniMind\\openzca-runtime`
- `openzca-home`: `%LOCALAPPDATA%\\OmniMind\\openzca-home`
- log Zalo: `%LOCALAPPDATA%\\OmniMind\\logs`

### 4.2 Runtime prerequisites

`openzca` yêu cầu:
- `Node.js 18+`
- `npm`

OmniMind cần:
- Kiểm tra `node` / `npm` trước khi cài `openzca`.
- Dùng absolute path để gọi binary local.
- Trên Windows, subprocess nền phải chạy ẩn cửa sổ console.
- Không đặt runtime `openzca` vào thư mục payload versioned của cơ chế update.

### 4.3 Update compatibility

`openzca-runtime` và `openzca-home` phải sống ở `app_data root`, không nằm trong:
- `updates/payloads/<version>`

Hệ quả:
- Update OmniMind không làm mất session Zalo.
- Update OmniMind không làm mất binary `openzca`.
- Bản OmniMind mới chỉ cần verify/install lại `openzca` nếu version mục tiêu đổi.

## 5) Hành vi bot Zalo

### 5.1 Luật nhận tin nhắn

Direct message:
- Nếu `zalo_enabled = true` và `zalo_auto_reply = true`, bot trả lời.

Group chat:
- Chỉ trả lời khi bot bị `@mention`.
- Chỉ trả lời nếu group nằm trong scope cho phép.

Scope nhóm:
- `all_groups`
- `selected_groups`

Allowlist:
- lưu theo `threadId`

### 5.2 Luật gửi phản hồi

MVP:
- Ưu tiên gửi `typing` trước khi gọi Codex.
- Sau khi Codex hoàn tất, gửi `1` hoặc vài chunk tin nhắn text.
- Không cố giả lập stream edit như Telegram.

Nguyên tắc gửi:
- DM: `openzca msg send <threadId> "<text>"`
- Group: thêm cờ group theo CLI của `openzca`
- Nếu phản hồi dài, split chunk với throttle

### 5.3 Trạng thái login / kết nối

Các state chuẩn:
- `Not logged in`
- `QR required`
- `Connected`
- `Re-auth required`

Nguồn xác định state:
- `openzca auth status`
- lifecycle event từ `openzca listen --supervised --raw --keep-alive`
- heartbeat / reconnect failures

### 5.4 Cảnh báo Telegram

Khi Zalo chuyển state xấu:
- `Connected -> Re-auth required`
- listener chết lặp lại nhiều lần
- mất heartbeat quá ngưỡng

OmniMind gửi cảnh báo về Telegram nếu Telegram bot/config đang sẵn sàng.

Phải có cooldown chống spam:
- ví dụ chỉ báo lại sau `30 phút` nếu cùng một lỗi chưa được xử lý.

## 6) Kiến trúc module đề xuất

### 6.1 Engine modules mới

`[NEW] src/engine/openzca_manager.py`
- Resolve app data paths cho `openzca`.
- Kiểm tra `node`, `npm`, local runtime.
- Cài / repair / upgrade `openzca` local.
- Expose helper:
  - `get_runtime_root()`
  - `get_openzca_home()`
  - `get_profile_name()`
  - `get_openzca_command()`
  - `ensure_openzca_installed()`
  - `run_auth_status()`
  - `run_auth_login()`
  - `run_auth_logout()`

`[NEW] src/engine/zalo_bot_service.py`
- Start/stop listener `openzca`.
- Parse raw JSON line.
- Filter DM / mention / group scope.
- Dedupe message.
- Gọi `CodexRuntimeBridge`.
- Gửi typing + text response.
- Quản lý watchdog restart.

`[NEW] src/engine/zalo_connection_monitor.py`
- Poll `auth status`.
- Theo dõi heartbeat / health state.
- Publish trạng thái cho UI.
- Trigger Telegram alert khi cần.

`[NEW] src/engine/zalo_models.py`
- Định nghĩa event schema nội bộ tối thiểu:
  - `thread_id`
  - `sender_id`
  - `chat_type`
  - `content`
  - `mentions`
  - `timestamp`
  - `message_id`
  - `raw_payload`

### 6.2 Modules hiện có cần sửa

`[MODIFY] src/engine/config_manager.py`
- Thêm config keys cho Zalo.
- Thêm helper get/set config.

`[MODIFY] src/engine/dashboard_manager.py`
- Start/stop/status cho Zalo bot.
- Expose login state và install state.

`[MODIFY] src/ui/pages/auth_page.py`
- Thêm khu vực cấu hình Zalo:
  - install/check `openzca`
  - login/logout/re-login
  - profile fixed `omnimind`
  - prompt nguyên tắc Zalo
  - group scope
  - allowlist nhóm
  - auto reply on/off

`[MODIFY] src/ui/pages/dashboard_page.py`
- Thêm card trạng thái Zalo.
- Nút bật/tắt Zalo bot.
- Hiển thị login state / health state.

`[MODIFY] src/main.py`
- Khởi tạo / restore state Zalo bot khi app start nếu config bật.

## 7) Cấu hình cần bổ sung

Các key đề xuất trong `app_configs`:
- `zalo_enabled`
- `zalo_auto_reply`
- `zalo_profile_name`
- `zalo_login_state`
- `zalo_group_scope`
- `zalo_group_allowlist`
- `zalo_prompt_principles`
- `zalo_reply_mode`
- `zalo_self_user_id`
- `zalo_last_connected_at`
- `zalo_last_heartbeat_at`
- `zalo_last_auth_ok_at`
- `zalo_last_reauth_alert_at`
- `zalo_openzca_version`
- `zalo_openzca_install_status`

Giá trị mặc định:
- `zalo_enabled = False`
- `zalo_auto_reply = True`
- `zalo_profile_name = omnimind`
- `zalo_group_scope = all`
- `zalo_group_allowlist = []`
- `zalo_reply_mode = dm_and_mention`

## 8) Logging và độ tin cậy

### 8.1 Structured logs

Tạo log riêng dạng JSONL:
- `zalo_inbound_events.jsonl`
- `zalo_outbound_events.jsonl`
- `zalo_listener_runtime.jsonl`
- `zalo_dead_letter.jsonl`

Mục tiêu:
- truy vết message bị mất
- debug reconnect
- điều tra duplicate

### 8.2 Idempotency / dedupe

Dedupe key ưu tiên:
- `(threadId, messageId)`

Fallback nếu thiếu `messageId`:
- `(threadId, senderId, timestamp, normalized_content_hash)`

Dedupe cache:
- lưu memory cache với TTL
- có thể persist ngắn hạn nếu cần sau này

### 8.3 Locking

Chỉ `1 listener` cho `1 profile`.

Khóa bằng file lock:
- tương tự pattern `telegram_poller.lock`
- ví dụ `zalo_listener_omnimind.lock`

### 8.4 Watchdog

Khi listener chết:
- thử restart với backoff
- nếu vượt ngưỡng, chuyển state `Re-auth required` hoặc `Disconnected`
- gửi alert Telegram theo cooldown

## 9) Các phase triển khai

## Phase 0 - Design Baseline và Branch

Mục tiêu:
- khóa kiến trúc, naming, config, path, state machine

Phạm vi:
- tạo branch `feature/zalo-codex-bot-v1`
- chốt file doc này
- xác nhận không ghi đè các thay đổi unrelated đang có trong worktree

Deliverables:
- tài liệu master plan
- branch riêng
- checklist scope MVP

Exit criteria:
- team/agent khác có thể bắt đầu code mà không phải quyết lại các quyết định nền tảng

## Phase 1 - OpenZCA Runtime Foundation

Mục tiêu:
- OmniMind tự quản lý `openzca` local trên macOS và Windows

Tính năng:
- detect `node` / `npm`
- install local `openzca`
- verify version
- repair/reinstall
- resolve `OPENZCA_HOME`
- lock fixed profile `omnimind`

File dự kiến:
- `[NEW] src/engine/openzca_manager.py`
- `[MODIFY] src/engine/environment_manager.py`
- `[MODIFY] src/engine/config_manager.py`
- `[MODIFY] src/ui/pages/auth_page.py`

Manual verification:
1. Máy có `node/npm`, bấm cài `openzca`, runtime local được tạo đúng thư mục.
2. Máy thiếu `node/npm`, UI báo rõ thiếu runtime.
3. Trên macOS và Windows đều resolve được binary local bằng absolute path.

Exit criteria:
- app cài được `openzca` local ổn định trên cả hai OS

## Phase 2 - Login UX và Connection Monitor

Mục tiêu:
- user đăng nhập Zalo được và nhìn thấy trạng thái rõ ràng

Tính năng:
- `Login Zalo`
- `Logout Zalo`
- `Re-login Zalo`
- poll `auth status`
- show state:
  - `Not logged in`
  - `QR required`
  - `Connected`
  - `Re-auth required`
- track heartbeat / last connected / last auth ok
- Telegram alert khi mất auth hoặc listener hỏng kéo dài

File dự kiến:
- `[NEW] src/engine/zalo_connection_monitor.py`
- `[MODIFY] src/engine/dashboard_manager.py`
- `[MODIFY] src/ui/pages/auth_page.py`
- `[MODIFY] src/ui/pages/dashboard_page.py`

Manual verification:
1. Login mới bằng QR thành công.
2. UI đổi sang `Connected`.
3. Logout hoặc session invalid thì UI chuyển `Re-auth required`.
4. Telegram nhận được cảnh báo khi mất auth.

Exit criteria:
- trạng thái kết nối có thể tin cậy để điều khiển runtime

## Phase 3 - MVP Text Bot

Mục tiêu:
- bot Zalo trả lời tin nhắn bằng Codex

Tính năng:
- listener `openzca listen --supervised --raw --keep-alive --profile omnimind`
- parse raw JSON thành schema nội bộ
- DM auto reply
- group reply chỉ khi `@mention`
- `all_groups` / `selected_groups`
- auto-reply on/off
- typing signal trước khi trả lời
- prompt nguyên tắc riêng cho Zalo
- memory integration
- gửi final text response

File dự kiến:
- `[NEW] src/engine/zalo_bot_service.py`
- `[NEW] src/engine/zalo_models.py`
- `[MODIFY] src/engine/config_manager.py`
- `[MODIFY] src/engine/dashboard_manager.py`
- `[MODIFY] src/ui/pages/auth_page.py`
- `[MODIFY] src/ui/pages/dashboard_page.py`
- `[MODIFY] src/main.py`

Manual verification:
1. Gửi DM từ thiết bị khác, bot trả lời.
2. Gửi group message không mention, bot bỏ qua.
3. Gửi group message có mention, bot trả lời.
4. Đổi `group_scope` sang `selected_groups`, bot chỉ trả lời đúng allowlist.
5. Tắt `auto_reply`, bot không phản hồi.

Exit criteria:
- Zalo bot text-only usable thực tế

## Phase 4 - Reliability Hardening

Mục tiêu:
- nâng chất lượng hội thoại Zalo theo thread, giảm duplicate, giảm chậm query, giữ context ổn định nhiều ngày mà không làm bot nặng lên

Tính năng:
- dedupe theo idempotency key
- dead-letter log cho parse/send lỗi
- restart backoff
- listener lock theo profile
- outbound queue + throttle
- structured runtime logs
- thread-scoped Zalo memory thay vì chỉ dùng memory global của assistant
- bootstrap context lần đầu bằng `openzca msg recent <threadId> [-g] -n <N> --json`
- fallback an toàn nếu `msg recent` lỗi hoặc timeout
- burst aggregation / debounce theo `thread_id` khi user gửi nhiều tin liên tiếp
- single-flight per thread để không spawn nhiều request Codex chồng nhau cho cùng một cuộc trò chuyện
- DB riêng cho Zalo:
  - `zalo_threads`
  - `zalo_messages`
  - `zalo_thread_summaries`
  - `zalo_thread_facts`
- index tối thiểu:
  - `zalo_messages(thread_id, timestamp DESC)`
  - `zalo_messages(thread_id, message_id)`
  - `zalo_messages(thread_id, sender_id, timestamp DESC)`
  - `zalo_threads(last_message_at DESC)`
  - `zalo_thread_summaries(thread_id, updated_at DESC)`
- retention policy:
  - raw messages có ngưỡng `3 ngày`, nhưng chỉ bị xóa khi thread đã có summary usable
  - thread summaries giữ `30 ngày`
  - facts/preferences giữ lâu hơn và prune theo confidence/hit_count nếu cần
- `zalo_threads` là metadata sống lâu, không bị xóa cùng retention raw
- rolling summary theo thread trước khi xóa raw cũ
- prompt architecture cho Zalo theo thứ tự:
  - assistant identity
  - global working rules
  - `Nguyên tắc trả lời Zalo`
  - thread summary
  - thread facts
  - recent turns
  - current bundled messages
- cleanup job định kỳ cho raw messages và summaries
- auto cleanup là bắt buộc ở phase này; manual cleanup button để Phase 5

File dự kiến:
- `[MODIFY] src/engine/zalo_bot_service.py`
- `[MODIFY] src/engine/zalo_connection_monitor.py`
- `[MODIFY] src/engine/process_lock.py` nếu cần helper tái sử dụng
- `[MODIFY] src/database/db_manager.py`
- `[NEW] src/engine/zalo_memory_manager.py`
- `[NEW] src/engine/zalo_prompt_builder.py`
- `[MODIFY] src/engine/config_manager.py`

Manual verification:
1. Kill listener process, watchdog restart lại.
2. Feed event trùng, bot không trả lời hai lần.
3. Mô phỏng reconnect liên tục, log không spam và UI không loạn state.
4. Gửi 3-5 tin liên tiếp trong cùng một DM, bot gom đúng cụm ý và trả lời một lần hợp lý.
5. Thread Zalo mới chưa có dữ liệu local, bot bootstrap được lịch sử gần nhất bằng `msg recent` hoặc fallback sạch nếu API lỗi.
6. Sau khi có lịch sử vài ngày, query context vẫn nhanh nhờ index và chỉ lấy recent turns + summary.
7. Sau hơn `3 ngày`, raw message cũ chỉ bị dọn khi thread đã có summary usable; summary `30 ngày` vẫn giữ continuity hội thoại.
8. Prompt runtime luôn chứa block `Nguyên tắc trả lời Zalo` trước phần thread context.

Exit criteria:
- bot đủ ổn để chạy nền dài hạn
- bot hiểu context theo từng thread tốt hơn thay vì chỉ dựa trên memory chung
- query context không phụ thuộc vào full history scan
- retention `3 ngày raw có điều kiện / 30 ngày summaries` hoạt động tự động và không làm mất continuity chính

## Phase 5 - Media Support

Mục tiêu:
- mở rộng Zalo bot từ text-only sang xử lý media theo cách không phá vỡ kiến trúc Phase 4

Tính năng:
- nhận metadata media inbound từ Zalo:
  - ảnh
  - file
  - media có caption
- map media vào schema nội bộ Zalo:
  - `media_type`
  - `media_path`
  - `media_urls`
  - `mime_type`
  - `caption`
- gộp text + caption + media vào cùng một bundle theo thread
- cho runtime bridge biết có media đi kèm để build prompt đúng ngữ cảnh
- ưu tiên inbound media trước outbound media
- nếu `openzca` hỗ trợ ổn định:
  - gửi ảnh/file outbound
  - fallback an toàn nếu không gửi được media
- giữ nguyên rule hiện tại:
  - DM auto reply
  - group chỉ reply khi `@mention`

Manual verification:
1. DM gửi ảnh có caption, bot hiểu được caption và metadata media.
2. Group gửi ảnh/file kèm `@mention`, bot xử lý đúng ngữ cảnh.
3. Media inbound không làm vỡ flow text-only hiện tại.
4. Nếu outbound media lỗi, bot fallback hoặc log rõ thay vì treo luồng.

Exit criteria:
- OmniMind xử lý được inbound media cơ bản trên Zalo mà không làm giảm độ ổn định của text flow

## Phase 6 - UI Polish và Operator Controls (Optional / Deferred)

Mục tiêu:
- bổ sung công cụ vận hành khi thực sự cần, không phải ưu tiên hiện tại

Tính năng:
- card trạng thái Zalo riêng trên Dashboard
- nút:
  - `Install/Repair openzca`
  - `Login`
  - `Logout`
  - `Re-login`
  - `Start Bot`
  - `Stop Bot`
  - `Dọn dữ liệu Zalo ngay`
- hiển thị account metadata cơ bản nếu lấy được
- editor prompt nguyên tắc Zalo
- editor group allowlist thân thiện hơn
- manual cleanup controls cho:
  - raw cũ
  - summaries cũ
  - cleanup all theo retention hiện tại

Manual verification:
1. Toàn bộ flow từ cài runtime đến bật bot thực hiện được từ UI.
2. Người dùng không cần gọi `openzca` tay trong terminal.

Exit criteria:
- feature đủ mức production beta cho người dùng nội bộ

## Phase 7 - Future Expansion

Mục tiêu:
- mở rộng mà không phá vỡ kiến trúc MVP

Tính năng tương lai:
- nhận/gửi ảnh và file
- command routing riêng cho Zalo
- xác nhận permission flow qua Zalo giống Telegram
- multi-turn control tốt hơn cho Codex qua Zalo
- có thể chạy song song Telegram + Zalo
- analytics số lượng thread / response / error

Nguyên tắc mở rộng:
- không chuyển sang multi-account cho đến khi single-account đủ ổn định
- không refactor transport abstraction lớn nếu chưa có ít nhất hai service thật sự cần dùng chung sâu

## 10) Thứ tự ưu tiên đề xuất

1. Phase 1
2. Phase 2
3. Phase 3
4. Phase 4
5. Phase 5
6. Phase 6
7. Phase 7

Lý do:
- phải cài runtime và xác định auth state ổn định trước khi nói đến bot logic
- bot MVP nên ra sớm nhưng reliability không được bỏ qua quá lâu
- sau khi text flow ổn định, phase tiếp theo ưu tiên media hơn là debug tooling

## 11) Rủi ro chính và cách chặn

### 11.1 `openzca` là community CLI

Rủi ro:
- policy/account/session có thể thay đổi

Giảm thiểu:
- isolate runtime
- pin version
- log structured
- có `repair/reinstall/re-login`

### 11.2 Session hết hạn

Rủi ro:
- bot im lặng nếu không phát hiện nhanh

Giảm thiểu:
- poll `auth status`
- heartbeat monitor
- Telegram alert
- UI state `Re-auth required`

### 11.3 Duplicate message khi reconnect

Rủi ro:
- bot trả lời hai lần

Giảm thiểu:
- idempotency key
- dedupe cache
- dead-letter / audit log

### 11.4 Group noise / spam

Rủi ro:
- bot trả lời sai nhóm hoặc spam nhóm đông

Giảm thiểu:
- chỉ reply khi mention
- group scope
- throttle outbound

### 11.5 Update drift

Rủi ro:
- OmniMind update xong nhưng `openzca` version lệch

Giảm thiểu:
- verify runtime version khi app start
- repair/install theo target version

## 12) Kiểm thử tối thiểu bắt buộc

### Unit / Integration test ưu tiên

- parse raw event JSON thành schema nội bộ
- filter rule cho DM / mention / group scope
- dedupe key generation
- state machine `Not logged in -> QR required -> Connected -> Re-auth required`
- command builder cho macOS / Windows

### Manual test matrix

macOS:
- install runtime
- login QR
- DM reply
- group mention reply
- re-login flow

Windows:
- install runtime
- login QR
- DM reply
- group mention reply
- subprocess chạy không bật cửa sổ console khó chịu

Regression:
- Telegram bot cũ không bị ảnh hưởng
- update OmniMind không làm mất `openzca` runtime/session

## 13) Gợi ý triển khai cho agent tiếp theo

Agent tiếp theo nên đi theo trình tự:
1. Implement `openzca_manager.py`
2. Thêm config keys + UI auth skeleton
3. Hoàn tất login state monitor
4. Implement `zalo_bot_service.py` text-only
5. Bổ sung hardening, logs, alerts

Nguyên tắc khi code:
- Không refactor lớn `TelegramBotService` ở vòng đầu.
- Không dùng global npm install làm mặc định.
- Không tạo profile mới khi user đổi tài khoản Zalo.
- Không đặt `openzca` runtime/session trong thư mục payload theo version.

## 14) Tài liệu tham chiếu ngoài dự án

- `openzca` README:
  - https://github.com/darkamenosa/openzca/blob/main/README.md
- `openzca` CLI feature reference:
  - https://github.com/darkamenosa/openzca/blob/main/docs/zca-cli-features-reference.md
