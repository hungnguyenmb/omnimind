# Checklist Sprint 10 - Context Discovery Tools

Ngày cập nhật: `2026-03-14`

Tài liệu này chi tiết hóa `Sprint 10 - Context Discovery Tools` trong:
- `docs/central_ai_behavior_taxonomy_sprint_plan.md`

Mục tiêu của Sprint 10:
- thêm nhóm tool read-only để OmniMind tự biết đang làm việc ở đâu và có gì trong workspace;
- giảm việc phải gọi Codex cho các câu hỏi discovery đơn giản;
- chuẩn bị nền cho session focus ở Sprint 12.

---

## 1. Phạm vi Sprint 10

Sprint này làm:
- thêm built-in discovery tools đầu tiên;
- cập nhật function registry/executor;
- nối Central AI để ưu tiên các discovery tools này ở case đơn giản;
- thêm test script hoặc case test cho discovery tools.

Sprint này chưa làm:
- chưa có session focus dài hạn;
- chưa có UI chọn workspace;
- chưa làm discovery nhiều workspace nâng cao;
- chưa thay thế hoàn toàn Codex cho mọi exploratory local case.

---

## 2. File mục tiêu

### Tạo mới
- [docs/central_ai_sprint10_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_sprint10_checklist.md)
- [scripts/test_context_discovery_tools.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/scripts/test_context_discovery_tools.py)

### Cập nhật
- [src/engine/function_registry.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/function_registry.py)
- [src/engine/function_executor.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/function_executor.py)
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [docs/central_ai_behavior_taxonomy_sprint_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_behavior_taxonomy_sprint_plan.md)

---

## 3. Checklist triển khai

### 3.1 Built-in discovery tools

- [x] Thêm ít nhất các function:
- [x] `get_current_workspace`
- [x] `list_local_files`
- [x] `search_files_by_name`
- [x] `get_git_repo_info`

### 3.2 Contract và policy

- [x] Mỗi tool có:
- [x] `description`
- [x] `input_schema`
- [x] `required_capabilities`
- [x] `approval_policy`
- [x] `execution_target`
- [x] Ưu tiên `approval_policy=auto` cho read-only discovery tools.
- [x] Giới hạn output:
- [x] `max_depth`
- [x] `max_entries`
- [x] giới hạn preview/status trả về ở executor

### 3.3 Executor logic

- [x] `get_current_workspace`
- [x] trả `cwd`
- [x] trả `codex_home`
- [x] trả thêm `workspace_path` và `git_repo_root` nếu có

- [x] `list_local_files`
- [x] nhận `path`
- [x] optional `pattern`
- [x] optional `max_entries`
- [x] optional `max_depth`
- [x] chỉ list read-only

- [x] `search_files_by_name`
- [x] nhận `query`
- [x] optional `root_path`
- [x] optional `max_entries`
- [x] dùng `rg --files` hoặc fallback `os.walk`

- [x] `get_git_repo_info`
- [x] trả `repo_root`
- [x] trả `branch`
- [x] trả status summary ngắn

### 3.4 Coordinator integration

- [x] Với các case:
- [x] `workspace nào`
- [x] `repo hiện tại`
- [x] `có file nào`
- [x] `tìm file tên X`
thì ưu tiên discovery tools trước Codex nếu câu hỏi đủ đơn giản.
- [x] Nếu discovery tool không đủ, vẫn cho phép escalate sang Codex.

### 3.5 Test

- [x] `py_compile` pass.
- [x] Test `get_current_workspace`.
- [x] Test `list_local_files` với path hợp lệ.
- [x] Test `search_files_by_name` với query `central_ai` và discovery root hợp lệ.
- [x] Test `get_git_repo_info` trong repo OmniMind.
- [x] Test routing:
- [x] `bạn đang làm việc trong workspace nào`
- [x] `liệt kê file .md trong docs`
- [x] `repo hiện tại là gì`

## 5. Ghi chú kết quả

Kết quả cập nhật ngày `2026-03-14`:
- Đã thêm script kiểm tra: `scripts/test_context_discovery_tools.py`
- `CentralAiCoordinator` đã route các case discovery đơn giản sang `tool_calling`
- `test_decision_contract_v2_cases.json` đã cập nhật expectation cho Sprint 10
- Các case discovery phức tạp, nhiều bước hoặc mở rộng vẫn giữ quyền escalate sang Codex

---

## 4. Exit criteria

- OmniMind tự trả lời được các câu discovery đơn giản về workspace/repo/file bằng built-in tools.
- Không cần gọi Codex cho các case discovery một bước.
- Discovery tools không mở rộng quyền quá mức và vẫn giữ read-only.
