# Checklist Sprint 4 - Built-in Function Registry Và Executor

Ngày cập nhật: `2026-03-13`

Tài liệu này chi tiết hóa `Sprint 4 - Built-in Function Registry Và Executor` trong:
- `docs/central_ai_function_calling_sprint_plan.md`

Mục tiêu của Sprint 4:
- để AI trung tâm gọi được built-in function thật thay vì chỉ trả lời hoặc fallback sang Codex;
- chuẩn hóa function schema nội bộ cho OmniMind;
- thực thi ít nhất các built-in function nền tảng như đọc file, lấy system info, shell command có kiểm soát;
- đưa kết quả function quay lại AI để sinh final reply.

## Trạng thái hiện tại

Trạng thái cập nhật ngày `2026-03-13`:
- Đã hoàn thành phần lõi:
  - `FunctionRegistry`
  - `FunctionExecutor`
  - capability model mở rộng trong `ActionExecutor`
  - tool loop một vòng trong `CentralAiCoordinator`
  - Telegram route nhận diện `tool_calling`
- Đã verify thật:
  - `get_system_info`
  - `read_local_file`
  - AI -> tool -> AI final reply qua gateway
- Chưa làm trong Sprint 4:
  - approval UI/phê duyệt nhiều bước cho function `on-request`
  - load function từ installed skills
  - multi-step tool loop lớn hơn 1 vòng reasoning

---

## 1. Phạm vi Sprint 4

Sprint này tập trung vào built-in function nội bộ.

Sprint này làm:
- tạo `FunctionRegistry`;
- tạo `FunctionExecutor`;
- mở rộng capability model cho built-in functions;
- cho `CentralAiCoordinator` chạy một vòng tool calling;
- tích hợp bước đầu với Telegram nếu coordinator chọn built-in tool path.

Sprint này chưa làm:
- chưa load function từ installed skills;
- chưa có multi-step agent loop nhiều vòng;
- chưa có approval UI/phê duyệt nhiều bước trong app;
- chưa hợp nhất hoàn toàn với Zalo.

---

## 2. File mục tiêu

### Tạo mới
- [src/engine/function_registry.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/function_registry.py)
- [src/engine/function_executor.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/function_executor.py)
- [scripts/test_builtin_function_loop.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/scripts/test_builtin_function_loop.py)

### Cập nhật
- [src/engine/action_executor.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/action_executor.py)
- [src/engine/config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [src/engine/telegram_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/telegram_bot_service.py)

---

## 3. Checklist triển khai

## 3.1 Function schema và registry

- [ ] Định nghĩa schema nội bộ cho function:
  - [ ] `name`
  - [ ] `description`
  - [ ] `input_schema`
  - [ ] `required_capabilities`
  - [ ] `approval_policy`
  - [ ] `execution_target`
- [ ] Tạo `FunctionRegistry`.
- [ ] Đăng ký built-in functions đầu tiên:
  - [ ] `get_system_info`
  - [ ] `read_local_file`
  - [ ] `write_local_file`
  - [ ] `run_shell_command`
- [ ] Cân nhắc expose thêm runtime actions có sẵn:
  - [ ] `runtime_ping`
  - [ ] `screen_capture`
  - [ ] `camera_snapshot`
  - [ ] `ui_automation_type_text`
  - [ ] `system_restart`

## 3.2 Capability model và approval policy

- [ ] Mở rộng `ActionExecutor.CAPABILITY_MATRIX` cho:
  - [ ] `fs_read`
  - [ ] `fs_write`
  - [ ] `exec`
  - [ ] `network`
- [ ] Chốt `approval_policy` tối thiểu:
  - [ ] `auto`
  - [ ] `on-request`
- [ ] Function an toàn đọc/truy vấn cho phép `auto`.
- [ ] Function ghi file/chạy shell/restart để `on-request`.

## 3.3 Function executor

- [ ] Tạo `FunctionExecutor`.
- [ ] Validate function name và arguments.
- [ ] Chạy preflight capability trước khi thực thi.
- [ ] Trả về contract chuẩn:
  - [ ] `success`
  - [ ] `code`
  - [ ] `message`
  - [ ] `data`
  - [ ] `artifacts`
  - [ ] `approval_required`
  - [ ] `function_name`
- [ ] Đảm bảo có audit log qua `ActionExecutor`.

## 3.4 Tích hợp với AI trung tâm

- [ ] `CentralAiCoordinator` có thể lấy danh sách tool schema từ `FunctionRegistry`.
- [ ] Nếu request thuộc nhóm local/tool-friendly thì thử `chat_with_tools(...)`.
- [ ] Nếu model trả `tool_calls`:
  - [ ] parse arguments
  - [ ] execute built-in function
  - [ ] append tool result vào messages
  - [ ] gọi AI thêm 1 lần để sinh final reply
- [ ] Nếu tool path lỗi hoàn toàn thì mới fallback về Codex.

## 3.5 Tích hợp với Telegram

- [ ] Nếu Telegram route vào built-in tool path, dùng `CentralAiCoordinator.handle_request(...)`.
- [ ] Giữ nguyên rollback path cũ về Codex nếu built-in function path fail.
- [ ] Không làm hỏng luồng file/document/directive đang chạy ổn.

## 3.6 Kiểm thử

- [ ] `py_compile` pass cho các file mới/sửa.
- [ ] Test `get_system_info`.
- [ ] Test `read_local_file`.
- [ ] Test 1 yêu cầu thực qua AI:
  - [ ] AI gọi tool
  - [ ] function chạy thật
  - [ ] AI tóm tắt kết quả
- [ ] Test fallback về Codex khi function path không đủ khả năng.

---

## 4. Exit criteria

- AI trung tâm gọi được ít nhất 2 built-in functions thật.
- Tool result quay lại AI để sinh final reply.
- Telegram có thể đi qua built-in function path mà vẫn có fallback an toàn.
- Có script test nội bộ cho built-in tool loop.
