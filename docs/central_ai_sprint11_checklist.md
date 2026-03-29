# Checklist Sprint 11 - Codex Role Formalization

Ngày cập nhật: `2026-03-14`

Tài liệu này chi tiết hóa `Sprint 11 - Codex Role Formalization` trong:
- `docs/central_ai_behavior_taxonomy_sprint_plan.md`

Mục tiêu của Sprint 11:
- định nghĩa rõ `Codex` là executor chính thức cho các việc local nhiều bước, khám phá mở, và coding workflow;
- không để AI trung tâm xử lý nửa vời kiểu “thiếu tool thì trả fail mơ hồ”;
- giữ cho built-in tools chỉ xử lý các tác vụ read-only hoặc deterministic một bước.

---

## 1. Phạm vi Sprint 11

Sprint này làm:
- chuẩn hóa policy phân vai giữa `AI trung tâm`, `built-in tools`, `Codex`;
- cập nhật routing để các case `exploratory_local` phức tạp và `coding_ops` đi Codex chủ động;
- thêm trace rõ lý do “vì sao gọi Codex”;
- cải thiện fallback ladder giữa `tool_calling`, `ask_clarification`, `escalate_to_codex`;
- kiểm tra lại Telegram/Zalo để dùng Codex như executor chính thức, không phải fallback mơ hồ.

Sprint này chưa làm:
- chưa có session focus dài hạn theo thread;
- chưa có planner riêng nhiều agent;
- chưa thêm browser ops hoặc personal ops integration thật;
- chưa làm UI debug riêng cho Codex route.

---

## 2. File mục tiêu

### Tạo mới
- [docs/central_ai_sprint11_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_sprint11_checklist.md)
- [scripts/test_codex_routing_policy.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/scripts/test_codex_routing_policy.py)

### Cập nhật
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [src/engine/codex_runtime_bridge.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/codex_runtime_bridge.py)
- [src/engine/telegram_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/telegram_bot_service.py)
- [src/engine/zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [docs/central_ai_behavior_taxonomy_and_routing_policy.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_behavior_taxonomy_and_routing_policy.md)
- [docs/central_ai_behavior_taxonomy_sprint_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_behavior_taxonomy_sprint_plan.md)

---

## 3. Checklist triển khai

### 3.1 Chuẩn hóa vai trò Codex

- [x] Chốt trong code và docs:
- [x] `AI trung tâm` = trả lời nhanh + gọi tool deterministic
- [x] `built-in tools` = action/tool read-only hoặc bounded
- [x] `Codex executor` = local workflow nhiều bước, code/repo/workspace reasoning
- [x] `Codex` không còn là fallback mơ hồ, mà là route chính thức

### 3.2 Routing policy cho Codex

- [x] Với `coding_ops`:
- [x] luôn ưu tiên `escalate_to_codex`
- [x] không thử tool loop trước nếu yêu cầu rõ là sửa code/debug/chạy test/build

- [x] Với `exploratory_local`:
- [x] discovery một bước -> giữ `tool_calling`
- [x] discovery nhiều bước hoặc mở -> `escalate_to_codex`

- [x] Bổ sung rule rõ cho các nhóm sau:
- [x] `tìm file rồi đọc/tóm tắt nhiều file`
- [x] `xem repo này có gì`
- [ ] `kiểm tra project này đang lỗi gì`
- [x] `debug`
- [x] `sửa code`
- [x] `chạy test`
- [ ] `tìm tất cả chỗ dùng X trong repo`

### 3.3 Decision trace và contract

- [x] Khi route sang Codex phải có:
- [x] `mode = escalate_to_codex`
- [x] `task_shape`
- [x] `confidence`
- [x] `why_not_tool`
- [x] `codex_reason`
- [x] `codex_task_type`

- [x] Có thể phân biệt ít nhất:
- [x] `codex_task_type = exploratory_local`
- [x] `codex_task_type = coding_workflow`
- [x] `codex_task_type = multi_step_local`

### 3.4 Fallback ladder

- [x] Nếu tool hiện có không đủ cho yêu cầu mở:
- [x] không trả lời kiểu “em chưa làm được”
- [x] ưu tiên escalate sang Codex

- [ ] Nếu thiếu context nghiêm trọng:
- [ ] có thể hỏi lại ngắn gọn
- [ ] chỉ hỏi lại khi thật sự cần, không hỏi lại vô ích

- [x] Nếu Codex path fail:
- [x] trace phải nói rõ là fail ở đâu
- [x] không làm mất phản hồi cho user

### 3.5 Telegram/Zalo integration

- [x] Telegram dùng Codex như executor chính thức cho exploratory/coding cases.
- [x] Zalo dùng cùng policy route như Telegram.
- [ ] Không để chênh lệch hành vi quá lớn giữa 2 kênh.
- [x] Metadata lưu memory cần có `central_ai_trace` và dấu vết route sang Codex.

### 3.6 Prompt và handoff sang Codex

- [x] Khi gọi Codex phải handoff đủ context:
- [x] user request
- [x] task_shape
- [x] lý do không dùng tool
- [x] workspace/repo/path nếu đã biết
- [x] artifact/path quan trọng nếu đã có từ tool trước đó

- [x] Không nhét quá nhiều lịch sử thô vào prompt Codex.
- [x] Tận dụng memory compact đã làm ở Sprint 10.

### 3.7 Test

- [x] `py_compile` pass.
- [x] Test route các câu sau:
- [x] `hãy tìm tất cả file config telegram rồi tóm tắt`
- [x] `xem repo này đang có gì`
- [x] `debug lỗi này trong project OmniMind`
- [x] `sửa file config để bật bot`
- [x] `chạy test rồi báo lỗi`

- [x] Test các câu sau vẫn không đi Codex:
- [x] `bạn đang làm việc trong workspace nào`
- [x] `liệt kê file .md trong docs`
- [x] `repo hiện tại là gì`
- [x] `tìm file WORKING_PRINCIPLES`

- [ ] Test Telegram thật ít nhất 2 case:
- [ ] 1 case discovery đơn giản
- [ ] 1 case coding/exploratory phải đi Codex

## 5. Ghi chú kết quả

Kết quả cập nhật ngày `2026-03-14`:
- `CentralAiCoordinator` đã có `codex_reason` và `codex_task_type` trong decision trace.
- `CodexRuntimeBridge` đã nhận `request_context` và phát `codex_handoff` event.
- Telegram/Zalo đã gọi nhánh `escalate_to_codex` của `CentralAiCoordinator`, không còn bỏ qua coordinator khi route sang Codex.
- Đã thêm script kiểm tra `scripts/test_codex_routing_policy.py`.
- Kết quả route test nội bộ:
  - `hãy tìm tất cả file config telegram rồi tóm tắt` -> `escalate_to_codex`
  - `xem repo này đang có gì` -> `escalate_to_codex`
  - `debug lỗi này trong project OmniMind` -> `escalate_to_codex`
  - `sửa file config để bật bot` -> `escalate_to_codex`
  - `chạy test rồi báo lỗi` -> `escalate_to_codex`
  - `bạn đang làm việc trong workspace nào` -> `tool_calling`
  - `liệt kê file .md trong docs` -> `tool_calling`
  - `repo hiện tại là gì` -> `tool_calling`
  - `tìm file WORKING_PRINCIPLES` -> `tool_calling`

---

## 4. Exit criteria

- Codex có vai trò rõ ràng trong kiến trúc, không còn chỉ là fallback khi tool fail.
- Các case `coding_ops` luôn đi Codex chủ động.
- Các case `exploratory_local` được tách tốt giữa:
- discovery một bước -> tool
- exploratory nhiều bước -> Codex
- Telegram/Zalo phản hồi nhất quán hơn, không còn câu trả lời lấp lửng kiểu “em tìm được file nhưng chưa đọc” khi thực ra nên giao cho Codex hoặc tool follow-up.
