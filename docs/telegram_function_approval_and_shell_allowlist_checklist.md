# Checklist - Telegram Built-in Function Approval Resume Và Shell Allowlist

Ngày cập nhật: `2026-03-14`

Mục tiêu của hạng mục này:
- cho phép AI trung tâm dùng `find` hoặc `rg --files` khi cần liệt kê file trong workspace;
- hoàn thiện luồng `approval -> đồng ý -> resume` cho built-in functions trong Telegram;
- giảm trường hợp user phải nhớ đường dẫn file tuyệt đối mới dùng được OmniMind.

---

## 1. Phạm vi

Hạng mục này làm:
- mở rộng shell allowlist cho các lệnh liệt kê file an toàn;
- lưu pending approval request cho built-in function trong Telegram;
- khi user trả lời `đồng ý`, Telegram chạy lại built-in function với `auto_approve=True`;
- trả kết quả thực thi về Telegram theo dạng người dùng đọc được.

Hạng mục này chưa làm:
- chưa thêm built-in function mới kiểu `list_local_files`;
- chưa có approval UI riêng trong desktop app;
- chưa đồng bộ approval-resume tương tự cho Zalo.

---

## 2. File cần sửa

- [src/engine/function_executor.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/function_executor.py)
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [src/engine/telegram_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/telegram_bot_service.py)

---

## 3. Checklist triển khai

- [ ] Mở rộng shell allowlist:
  - [ ] thêm `find`
  - [ ] thêm `rg --files` một cách tường minh
  - [ ] giữ nguyên chặn token shell nguy hiểm

- [ ] Chuẩn hóa dữ liệu approval của built-in function:
  - [ ] `CentralAiCoordinator` trả ra `approval_requests` khi tool loop gặp `APPROVAL_REQUIRED`
  - [ ] mỗi request có `kind`, `function_name`, `arguments`, `required_capabilities`, `message`

- [ ] Nối Telegram với built-in function approval:
  - [ ] nếu central AI trả về `approval_requests` thì lưu vào `_pending_permission_confirmations`
  - [ ] gửi hướng dẫn rõ để user trả lời `đồng ý` hoặc `hủy`

- [ ] Resume built-in function sau khi xác nhận:
  - [ ] `_execute_confirmed_permission_requests(...)` hỗ trợ `kind=function`
  - [ ] thực thi lại bằng `FunctionExecutor.execute_function(..., auto_approve=True)`
  - [ ] trả kết quả thành text dễ đọc qua Telegram

- [ ] Kiểm thử:
  - [ ] `py_compile` pass
  - [ ] test `run_shell_command` với `find`
  - [ ] test `run_shell_command` với `rg --files`
  - [ ] test luồng `approval_required -> đồng ý -> function chạy lại`
  - [ ] test `hủy` vẫn xóa pending request

---

## 4. Exit criteria

- User có thể yêu cầu liệt kê file bằng `find` hoặc `rg --files`.
- Telegram hiểu câu `đồng ý` để resume built-in function đang chờ approval.
- Kết quả sau resume được gửi lại rõ ràng, không bắt user tự chạy lệnh thủ công.
