# Sprint Plan - Nâng Cấp Taxonomy Hành Vi Và Routing Policy Cho OmniMind

Ngày cập nhật: `2026-03-14`

Tài liệu này là roadmap triển khai tiếp theo, dựa trên:
- `docs/central_ai_behavior_taxonomy_and_routing_policy.md`
- `docs/central_ai_function_calling_upgrade_plan.md`
- `docs/central_ai_function_calling_sprint_plan.md`

Giả định:
- Sprint 1-8 hiện tại đã tạo được nền OpenAPI, central coordinator, built-in functions, skill functions, tool loop, Telegram/Zalo integration cơ bản, attachment và vision foundation.
- Roadmap dưới đây là giai đoạn nâng cấp tiếp theo để OmniMind xử lý hành vi người dùng tốt hơn.

---

## Sprint 9 - Decision Contract 2.0

## Mục tiêu
Nâng decision contract của AI trung tâm từ `mode` đơn giản sang routing contract đầy đủ.

## Phạm vi
- Thêm:
  - `task_shape`
  - `confidence`
  - `missing_context`
  - `why_not_tool`
  - `needs_approval`
- Chuẩn hóa trace mới cho Telegram/Zalo/UI.

## File dự kiến
- `[MODIFY] src/engine/central_ai_coordinator.py`
- `[MODIFY] src/engine/conversation_orchestrator.py`
- `[MODIFY] docs/central_ai_behavior_taxonomy_and_routing_policy.md`

## Exit criteria
- Mọi request đều có decision trace giàu ngữ nghĩa hơn `mode`.
- Có thể giải thích vì sao hệ thống chọn tool hoặc Codex.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-14`:
- Đã tạo checklist chi tiết tại `docs/central_ai_sprint9_checklist.md`.
- `CentralAiCoordinator` đã có decision fields mới:
  - `task_shape`
  - `confidence`
  - `missing_context`
  - `why_not_tool`
  - `needs_approval`
  - `preferred_tool`
- Đã thêm heuristic classifier ban đầu cho:
  - `knowledge`
  - `local_ops`
  - `document_analysis`
  - `exploratory_local`
  - `coding_ops`
  - `browser_ops`
  - `personal_ops`
  - `high_risk_action`
- Đã thêm script kiểm tra nhanh decision contract.
- Phần còn lại cho sprint sau:
  - chưa có discovery tools thật
  - chưa có session focus
  - `browser_ops` và `personal_ops` mới dừng ở mức taxonomy/trace, chưa có integration thực
- Kết luận: Sprint 9 đã bắt đầu ở mức Decision Contract 2.0 foundation.

---

## Sprint 10 - Context Discovery Tools

## Mục tiêu
Thêm nhóm tool read-only chuyên để tìm và xác định context local.

## Phạm vi
- Thêm built-in functions như:
  - `get_current_workspace`
  - `list_local_files`
  - `search_files_by_name`
  - `get_git_repo_info`
- ưu tiên auto/read-only, hạn chế approval.

## File dự kiến
- `[MODIFY] src/engine/function_registry.py`
- `[MODIFY] src/engine/function_executor.py`
- `[MODIFY] src/engine/central_ai_coordinator.py`

## Exit criteria
- Câu hỏi kiểu `đang ở workspace nào`, `có file nào`, `repo hiện tại là gì` không cần đi Codex trong case đơn giản.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-14`:
- Đã tạo checklist chi tiết tại `docs/central_ai_sprint10_checklist.md`.
- Đã thêm 4 built-in discovery tools:
  - `get_current_workspace`
  - `list_local_files`
  - `search_files_by_name`
  - `get_git_repo_info`
- `FunctionExecutor` đã có logic read-only cho workspace/file/repo discovery.
- `CentralAiCoordinator` đã route các case discovery đơn giản sang `tool_calling` với `preferred_tool` cụ thể.
- Đã thêm script kiểm tra `scripts/test_context_discovery_tools.py`.
- Đã cập nhật dataset `scripts/test_decision_contract_v2_cases.json` để phản ánh behavior của Sprint 10.
- Kết quả kiểm tra:
  - `workspace nào` -> `tool_calling` / `get_current_workspace`
  - `liệt kê file .md trong docs` -> `tool_calling` / `list_local_files`
  - `repo hiện tại là gì` -> `tool_calling` / `get_git_repo_info`
  - `tìm các file .md trong repo này` -> `tool_calling` / `search_files_by_name`
- Giới hạn còn lại:
  - chưa có session focus dài hạn
  - chưa có multi-workspace discovery nâng cao
  - các case discovery nhiều bước hoặc cần tổng hợp sâu vẫn nên escalate sang Codex

---

## Sprint 11 - Codex Role Formalization

## Mục tiêu
Định nghĩa Codex là executor chính thức cho nhóm `exploratory_local` và `coding_ops`.

## Phạm vi
- Chuẩn hóa route `escalate_to_codex`.
- Thêm rule gate cho:
  - `workspace nào`
  - `tìm file`
  - `repo này`
  - `debug`
  - `sửa code`
  - `chạy test`
- Không để tool loop trả lời lấp lửng khi tool không đủ.

## File dự kiến
- `[MODIFY] src/engine/central_ai_coordinator.py`
- `[MODIFY] src/engine/codex_runtime_bridge.py`
- `[MODIFY] src/engine/telegram_bot_service.py`
- `[MODIFY] src/engine/zalo_bot_service.py`

## Exit criteria
- Các case `exploratory_local` và `coding_ops` đi Codex chủ động, không đợi fail.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-14`:
- Đã tạo checklist chi tiết tại `docs/central_ai_sprint11_checklist.md`.
- `CentralAiCoordinator` đã có thêm:
  - `codex_reason`
  - `codex_task_type`
  - rule route chủ động cho `coding_ops`, `exploratory_local` mở, và một phần `local_ops` nhiều bước / sửa config
- `CodexRuntimeBridge` đã nhận `request_context` để phát `codex_handoff` event.
- Telegram/Zalo đã gọi luôn nhánh `escalate_to_codex` của `CentralAiCoordinator`, thay vì bỏ qua coordinator rồi đi legacy flow ngay từ đầu.
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
- Phần còn lại:
  - cần E2E thật trên Telegram/Zalo cho ít nhất 1 case discovery đơn giản và 1 case coding/exploratory
  - clarification policy riêng vẫn thuộc Sprint 13

---

## Sprint 12 - Session Focus

## Mục tiêu
Mỗi thread/chat có session focus riêng để AI biết đang làm việc ở đâu và về cái gì.

## Phạm vi
- Lưu:
  - `active_workspace`
  - `active_project`
  - `active_task`
  - `recent_files`
  - `recent_urls`
- Cập nhật focus sau mỗi request có ngữ cảnh rõ.

## File dự kiến
- `[MODIFY] src/database/db_manager.py`
- `[MODIFY] src/engine/assistant_memory_manager.py`
- `[MODIFY] src/engine/zalo_memory_manager.py`
- `[MODIFY] src/engine/telegram_bot_service.py`
- `[MODIFY] src/engine/zalo_bot_service.py`

## Exit criteria
- User không cần nhắc lại workspace/project ở mọi câu.
- Các đại từ như `file đó`, `repo này` có thể resolve tốt hơn.

---

## Sprint 13 - Clarification Policy

## Mục tiêu
Tách rõ khi nào nên hỏi lại user thay vì cố dùng tool hoặc đẩy sang Codex.

## Phạm vi
- Thêm mode `ask_clarification`.
- Chuẩn hóa `missing_context`.
- Định nghĩa template hỏi lại ngắn, đúng trọng tâm.

## File dự kiến
- `[MODIFY] src/engine/central_ai_coordinator.py`
- `[MODIFY] src/engine/telegram_bot_service.py`
- `[MODIFY] src/engine/zalo_bot_service.py`

## Exit criteria
- Hệ thống chỉ hỏi lại khi thật sự cần.
- Các câu hỏi lại có cấu trúc ngắn, không gây khó chịu.

---

## Sprint 14 - Personal Ops Foundation

## Mục tiêu
Xây nền cho nhóm `personal_ops`, không để mọi thứ đổ sang Codex.

## Phạm vi
- chuẩn hóa function/spec cho:
  - email
  - calendar
  - task list
  - notes/document index
- nếu chưa có tích hợp thật, ít nhất phải có contract/API abstraction.

## File dự kiến
- `[NEW] src/engine/personal_ops_registry.py`
- `[MODIFY] src/engine/function_registry.py`
- `[MODIFY] docs/skill_tool_function_standard.md`

## Exit criteria
- OmniMind có taxonomy và contract rõ cho personal assistant workflows.

---

## Sprint 15 - Browser Ops Policy

## Mục tiêu
Phân biệt rõ browser automation đơn giản và web workflow nên giao cho Codex.

## Phạm vi
- định nghĩa `browser_ops`
- capability model cho browser
- rule:
  - web read-only đơn giản -> tool
  - login/phức tạp/nhiều bước -> Codex

## File dự kiến
- `[MODIFY] src/engine/function_registry.py`
- `[MODIFY] src/engine/central_ai_coordinator.py`
- `[NEW] docs/browser_ops_policy.md`

## Exit criteria
- Không còn nhập nhằng giữa `open url` và `đi làm workflow web`.

---

## Sprint 16 - Approval Và Risk Matrix

## Mục tiêu
Tách rõ `read-only`, `mutating`, `high-risk`.

## Phạm vi
- mỗi function/skill phải có:
  - `risk_level`
  - `approval_policy`
  - `user_visible_confirmation_text`
- Telegram/Zalo approval flow hiển thị rõ hơn.

## File dự kiến
- `[MODIFY] src/engine/function_registry.py`
- `[MODIFY] src/engine/function_executor.py`
- `[MODIFY] src/engine/telegram_bot_service.py`
- `[MODIFY] src/engine/zalo_bot_service.py`

## Exit criteria
- User hiểu rõ mình đang xác nhận loại thao tác gì.
- Action nguy hiểm không đi chung policy với query read-only.

---

## Sprint 17 - Observability Và Evaluation

## Mục tiêu
Đo được routing đúng/sai, tool đủ/thiếu, Codex bị gọi quá nhiều hay quá ít.

## Phạm vi
- log:
  - task_shape
  - confidence
  - why_not_tool
  - fallback_reason
- thêm bộ test/eval cho các utterance mẫu.

## File dự kiến
- `[MODIFY] src/engine/central_ai_coordinator.py`
- `[NEW] scripts/eval_routing_policy.py`
- `[NEW] docs/routing_eval_dataset.md`

## Exit criteria
- Có thể đánh giá chất lượng router theo nhóm hành vi, không chỉ theo cảm giác.

---

## Sprint 18 - Hardening Và Rollout

## Mục tiêu
Đưa taxonomy mới thành đường vận hành chính an toàn.

## Phạm vi
- rollout theo feature flag
- rollback policy
- QA checklist riêng cho:
  - conversation
  - personal ops
  - local ops
  - exploratory local
  - coding ops

## File dự kiến
- `[MODIFY] docs/monitoring_and_rollback_checklist.md`
- `[NEW] docs/behavior_taxonomy_rollout_checklist.md`

## Exit criteria
- Có thể bật dần routing policy mới mà không làm gãy flow hiện tại.

---

## Thứ Tự Ưu Tiên Khuyến Nghị

Nên làm theo thứ tự:
1. Sprint 9
2. Sprint 10
3. Sprint 11
4. Sprint 12
5. Sprint 13
6. Sprint 16
7. Sprint 17
8. Sprint 14
9. Sprint 15
10. Sprint 18

Lý do:
- quyết định route tốt hơn phải đến trước;
- discovery tools và Codex role phải rõ trước khi mở rộng personal/browser ops;
- observability nên có trước khi rollout rộng.
