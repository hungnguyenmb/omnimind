# Checklist Sprint 9 - Decision Contract 2.0

Ngày cập nhật: `2026-03-14`

Tài liệu này chi tiết hóa `Sprint 9 - Decision Contract 2.0` trong:
- `docs/central_ai_behavior_taxonomy_sprint_plan.md`

Mục tiêu của Sprint 9:
- nâng decision contract của AI trung tâm từ router đơn giản sang router có ngữ nghĩa;
- để hệ thống giải thích được vì sao nó chọn direct reply, tool hay Codex;
- tạo nền cho các sprint sau như discovery tools, Codex role formalization và session focus.

---

## 1. Phạm vi Sprint 9

Sprint này làm:
- thêm các trường decision mới:
  - `task_shape`
  - `confidence`
  - `missing_context`
  - `why_not_tool`
  - `needs_approval`
  - `preferred_tool`
- chuẩn hóa trace tương ứng trong `CentralAiCoordinator`;
- nối trace mới vào metadata của Telegram/Zalo;
- thêm test script để rà nhanh decision contract.

Sprint này chưa làm:
- chưa thêm context discovery tools mới;
- chưa thêm session focus;
- chưa đổi toàn bộ router sang model-based classifier;
- chưa mở rộng đầy đủ cho browser/personal ops integration thật.

---

## 2. File mục tiêu

### Tạo mới
- [docs/central_ai_sprint9_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_sprint9_checklist.md)
- [scripts/test_decision_contract_v2.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/scripts/test_decision_contract_v2.py)

### Cập nhật
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [src/engine/telegram_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/telegram_bot_service.py)
- [src/engine/zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [docs/central_ai_behavior_taxonomy_sprint_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_behavior_taxonomy_sprint_plan.md)

---

## 3. Checklist triển khai

### 3.1 Decision fields

- [ ] Chuẩn hóa decision contract mới:
  - [ ] `mode`
  - [ ] `task_shape`
  - [ ] `confidence`
  - [ ] `reason`
  - [ ] `missing_context`
  - [ ] `why_not_tool`
  - [ ] `needs_approval`
  - [ ] `preferred_tool`
- [ ] Giữ tương thích ngược với trace cũ nếu cần.

### 3.2 Task shape heuristics

- [ ] Phân loại ít nhất các nhóm:
  - [ ] `conversation`
  - [ ] `knowledge`
  - [ ] `local_ops`
  - [ ] `exploratory_local`
  - [ ] `document_analysis`
  - [ ] `coding_ops`
  - [ ] `browser_ops`
  - [ ] `personal_ops`
  - [ ] `high_risk_action`
- [ ] Các case `workspace/repo/find/list file/debug/sửa code` phải bias rõ hơn.

### 3.3 Missing context

- [ ] Bóc tách được một số context còn thiếu:
  - [ ] `path`
  - [ ] `file_reference`
  - [ ] `workspace_reference`
  - [ ] `url`
  - [ ] `account`

### 3.4 Approval hint

- [ ] Heuristic `needs_approval` cho:
  - [ ] write/delete/restart
  - [ ] shell command
  - [ ] browser workflow nhạy cảm

### 3.5 Trace integration

- [ ] Trace của coordinator có đầy đủ decision fields mới.
- [ ] Telegram metadata lưu được trace mới.
- [ ] Zalo metadata lưu được trace mới.

### 3.6 Test

- [ ] `py_compile` pass.
- [ ] Test sample utterances:
  - [ ] câu hỏi kiến thức
  - [ ] đọc file cụ thể
  - [ ] `workspace nào`
  - [ ] `tìm file .md`
  - [ ] `debug bug này`
  - [ ] `truy cập web`
  - [ ] `kiểm tra email`
- [ ] Có script dump decision để rà nhanh router.

---

## 4. Exit criteria

- Decision contract có đủ trường ngữ nghĩa như taxonomy mới yêu cầu.
- Có thể nhìn vào trace để hiểu vì sao router chọn tool hay Codex.
- Có script test nhanh cho nhóm utterance phổ biến.
