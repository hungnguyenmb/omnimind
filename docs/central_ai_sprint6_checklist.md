# Checklist Sprint 6 - Multi-step Tool Loop

Ngày cập nhật: `2026-03-13`

Tài liệu này chi tiết hóa `Sprint 6 - Multi-step Tool Loop` trong:
- `docs/central_ai_function_calling_sprint_plan.md`

Mục tiêu của Sprint 6:
- biến AI trung tâm từ router một bước thành agent loop có giới hạn;
- cho phép nhiều lần tool call trong một request;
- luôn đưa tool result quay lại AI trước khi trả lời user;
- có guard chống loop vô hạn, timeout tổng và trace từng bước.

## Trạng thái hiện tại

Trạng thái cập nhật ngày `2026-03-13`:
- Đã hoàn thành phần lõi:
  - multi-step tool loop trong `CentralAiCoordinator`
  - giới hạn số bước
  - timeout tổng
  - guard phát hiện tool call lặp lại
  - trace chi tiết từng step
- Đã verify thật:
  - request multi-step dùng `get_system_info` + `read_local_file`
  - request lặp một tool và dừng đúng ở `repeated_tool_calls`
- Chưa làm trong Sprint 6:
  - planner riêng hoặc memory write-back theo từng step
  - UI quan sát live tool loop
  - orchestration đa agent/background jobs

---

## 1. Phạm vi Sprint 6

Sprint này làm:
- nâng `CentralAiCoordinator` thành multi-step tool loop;
- thêm giới hạn số bước và timeout tổng;
- log chi tiết từng vòng tool call;
- fallback có kiểm soát nếu tool loop không chốt được câu trả lời.

Sprint này chưa làm:
- chưa có planner riêng hoặc memory write-back theo từng tool step;
- chưa có UI quan sát live tool loop;
- chưa làm orchestration đa agent hoặc background job dài.

---

## 2. File mục tiêu

### Tạo mới
- [docs/central_ai_sprint6_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_sprint6_checklist.md)
- [scripts/test_multi_step_tool_loop.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/scripts/test_multi_step_tool_loop.py)

### Cập nhật
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [src/engine/config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)
- [src/engine/ai_gateway_client.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/ai_gateway_client.py)

---

## 3. Checklist triển khai

## 3.1 Guard rail cho tool loop

- [ ] Thêm config:
  - [ ] `central_ai_tool_loop_max_steps`
  - [ ] `central_ai_tool_loop_timeout_sec`
  - [ ] `central_ai_tool_loop_max_calls_per_step`
- [ ] Stop loop khi:
  - [ ] vượt `max_steps`
  - [ ] quá `timeout_sec`
  - [ ] phát hiện tool call lặp vô ích

## 3.2 Multi-step tool orchestration

- [ ] `CentralAiCoordinator` gọi model theo vòng lặp.
- [ ] Mỗi vòng:
  - [ ] gửi messages hiện tại + tool schemas
  - [ ] nhận `tool_calls`
  - [ ] execute từng tool
  - [ ] append tool results vào messages
  - [ ] tiếp tục vòng tiếp theo nếu model còn cần tool
- [ ] Nếu model dừng và trả text:
  - [ ] dùng text đó làm final reply

## 3.3 Trace và audit

- [ ] Trace phải có:
  - [ ] tổng số bước
  - [ ] từng tool call
  - [ ] args preview
  - [ ] result code
  - [ ] success/fail
  - [ ] lý do kết thúc loop
- [ ] Ghi vào `central_ai_runtime.jsonl`.

## 3.4 Fallback behavior

- [ ] Nếu loop không tạo được final reply:
  - [ ] thử chốt bằng summary từ tool results
  - [ ] hoặc fallback sang Codex nếu policy cho phép
- [ ] Nếu tool loop bị timeout:
  - [ ] trả lỗi rõ và không treo request

## 3.5 Kiểm thử

- [ ] `py_compile` pass.
- [ ] Test prompt cần ít nhất 2 tool:
  - [ ] ví dụ `get_system_info` + `read_local_file`
- [ ] Xác nhận trace ghi đủ nhiều bước.
- [ ] Test case tool lặp lại để loop dừng đúng.
- [ ] Test fallback khi loop không hoàn tất.

---

## 4. Exit criteria

- AI trung tâm xử lý được ít nhất 1 request cần nhiều hơn 1 tool.
- Có giới hạn bước và timeout tổng hoạt động đúng.
- Trace thể hiện rõ từng step và lý do kết thúc loop.
