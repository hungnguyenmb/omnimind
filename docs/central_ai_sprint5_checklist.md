# Checklist Sprint 5 - Skill Function Standard Và Local Loading

Ngày cập nhật: `2026-03-13`

Tài liệu này chi tiết hóa `Sprint 5 - Skill Function Standard Và Local Loading` trong:
- `docs/central_ai_function_calling_sprint_plan.md`

Mục tiêu của Sprint 5:
- cho OmniMind đọc được `tool_manifest.json` từ skill đã cài;
- đăng ký skill functions vào `FunctionRegistry`;
- thực thi được skill function qua `FunctionExecutor`;
- giữ nguyên nguyên tắc: lỗi function của một skill không làm hỏng toàn bộ skill.

## Trạng thái hiện tại

Trạng thái cập nhật ngày `2026-03-13`:
- Đã hoàn thành phần lõi:
  - parse `tool_manifest.json`
  - normalize skill functions
  - đăng ký vào `FunctionRegistry`
  - thực thi `skill_function` qua `FunctionExecutor`
  - AI loop gọi được sample skill function
- Đã verify thật:
  - local manifest scan thành công
  - executor chạy sample skill script thành công
  - AI trung tâm gọi sample skill function qua gateway thành công
- Chưa làm trong Sprint 5:
  - UI enable/disable từng function
  - sync function metadata lên backend/CMS
  - multi-step tool loop nhiều vòng

---

## 1. Phạm vi Sprint 5

Sprint này làm:
- parse `tool_manifest.json` của installed skill;
- validate function metadata tối thiểu;
- expose skill functions cho AI trung tâm;
- thực thi local skill function bằng script executor hiện có;
- thêm test local end-to-end với một sample skill.

Sprint này chưa làm:
- chưa rollout backend/CMS để publish function metadata;
- chưa đồng bộ schema function lên API catalog;
- chưa có UI quản lý enable/disable từng function;
- chưa làm multi-step agent loop nhiều bước.

---

## 2. File mục tiêu

### Tạo mới
- [docs/central_ai_sprint5_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_sprint5_checklist.md)
- [scripts/test_skill_function_loop.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/scripts/test_skill_function_loop.py)

### Cập nhật
- [src/engine/skill_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/skill_manager.py)
- [src/engine/function_registry.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/function_registry.py)
- [src/engine/function_executor.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/function_executor.py)
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)

---

## 3. Checklist triển khai

## 3.1 Parse và validate `tool_manifest.json`

- [ ] Thêm helper đọc `tool_manifest.json` từ thư mục skill local.
- [ ] Validate tối thiểu:
  - [ ] `manifest_version`
  - [ ] `skill_id`
  - [ ] `functions[]`
  - [ ] `name`
  - [ ] `description`
  - [ ] `input_schema`
  - [ ] `execution.type`
  - [ ] `execution.entrypoint`
- [ ] Nếu function lỗi, ghi warning và bỏ qua function đó.
- [ ] Không fail cả skill chỉ vì một function khai báo sai.

## 3.2 Nối vào `SkillManager`

- [ ] Thêm API lấy danh sách function từ installed skills.
- [ ] Chuẩn hóa metadata function để `FunctionRegistry` dùng được.
- [ ] Thêm API thực thi một installed skill function theo:
  - [ ] `skill_id`
  - [ ] `function_name`
  - [ ] `arguments`
- [ ] Tôn trọng:
  - [ ] `required_capabilities`
  - [ ] `approval_policy`
  - [ ] `timeout_seconds`
  - [ ] `entrypoint`

## 3.3 Nối vào `FunctionRegistry`

- [ ] Registry tự load built-in functions + skill functions.
- [ ] Tên function phải tránh collision giữa nhiều skills.
- [ ] Tool schema trả ra cho model phải hợp lệ với OpenAI-compatible tool calling.

## 3.4 Nối vào `FunctionExecutor`

- [ ] Thêm execution target cho `skill_function`.
- [ ] Skill function phải dùng lại runtime executor có sẵn, không viết một pipeline riêng.
- [ ] Chuẩn hóa result contract giống built-in function:
  - [ ] `success`
  - [ ] `code`
  - [ ] `message`
  - [ ] `data`
  - [ ] `artifacts`
  - [ ] `function_name`

## 3.5 Nối vào AI trung tâm

- [ ] `CentralAiCoordinator` nhìn thấy skill functions như một phần của tool list.
- [ ] Nếu model gọi skill function:
  - [ ] app execute skill function thật
  - [ ] trả tool result về model
  - [ ] model sinh final reply
- [ ] Nếu skill function không khả dụng, fallback rõ ràng.

## 3.6 Kiểm thử

- [ ] `py_compile` pass cho file mới/sửa.
- [ ] Test local:
  - [ ] parse manifest thành công
  - [ ] registry thấy được sample skill function
  - [ ] executor chạy sample skill function thành công
- [ ] Test AI loop:
  - [ ] model chọn sample skill function
  - [ ] skill script chạy thật
  - [ ] AI trả final reply đúng ngữ cảnh

---

## 4. Exit criteria

- Ít nhất 1 installed skill expose function thành công.
- AI trung tâm gọi được skill function thật.
- Lỗi manifest của một function không làm hỏng cả skill.
- Có script test local end-to-end cho sample skill function.
