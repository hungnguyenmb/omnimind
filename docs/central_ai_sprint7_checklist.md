# Checklist Sprint 7 - Zalo Integration Qua Central AI

Ngày cập nhật: `2026-03-13`

Tài liệu này chi tiết hóa `Sprint 7 - Zalo Integration Qua Central AI` trong:
- `docs/central_ai_function_calling_sprint_plan.md`

Mục tiêu của Sprint 7:
- đưa Zalo vào cùng kiến trúc AI trung tâm như Telegram;
- cho Zalo dùng direct reply, built-in tool loop và skill functions khi phù hợp;
- vẫn giữ fallback path cũ qua `ZaloPromptBuilder + Codex` để tránh regression.

## Trạng thái hiện tại

Trạng thái cập nhật ngày `2026-03-13`:
- Đã hoàn thành phần lõi:
  - `ZaloBotService` tạo request chuẩn cho `channel='zalo'`
  - dùng `CentralAiCoordinator` cho `reply_direct` và `tool_calling`
  - fallback legacy nếu central AI không chốt được câu trả lời
- Đã verify thật:
  - direct AI trên `channel='zalo'`
  - tool path trên `channel='zalo'` với `get_system_info`
- Chưa làm trong Sprint 7:
  - attachment intake/download cho Zalo
  - hợp nhất hoàn toàn memory giữa `ZaloMemoryManager` và `AssistantMemoryManager`
  - UI debug riêng cho Zalo tool loop

---

## 1. Phạm vi Sprint 7

Sprint này làm:
- tích hợp `ZaloBotService` với `CentralAiCoordinator`;
- route bundle text của Zalo qua AI trung tâm;
- nếu AI trung tâm fail thì fallback về luồng Zalo cũ;
- log trace cho nhánh central AI trên Zalo.

Sprint này chưa làm:
- chưa xử lý attachment download intake cho Zalo;
- chưa hợp nhất hoàn toàn memory giữa `ZaloMemoryManager` và `AssistantMemoryManager`;
- chưa có UI debug riêng cho Zalo tool loop.

---

## 2. File mục tiêu

### Tạo mới
- [docs/central_ai_sprint7_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_sprint7_checklist.md)

### Cập nhật
- [src/engine/zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [docs/central_ai_function_calling_sprint_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_function_calling_sprint_plan.md)

---

## 3. Checklist triển khai

## 3.1 Tích hợp route

- [ ] `ZaloBotService` khởi tạo `CentralAiCoordinator`.
- [ ] Khi gom bundle messages xong, tạo request chuẩn cho channel `zalo`.
- [ ] Nếu route là:
  - [ ] `reply_direct` -> dùng AI trung tâm
  - [ ] `tool_calling` -> dùng AI trung tâm
  - [ ] fail hoặc không chốt được -> fallback legacy Codex path

## 3.2 Giữ tương thích flow cũ

- [ ] Không phá `ZaloPromptBuilder` hiện có.
- [ ] Không phá `execute_runtime_skill_directives`.
- [ ] Không phá luồng `typing heartbeat`.
- [ ] Không phá outbound chunk send hiện tại.

## 3.3 Memory và trace

- [ ] Lưu `central_ai_trace` vào metadata runtime interaction của Zalo.
- [ ] Ghi log JSONL khi Zalo dùng central AI path.
- [ ] Vẫn refresh thread summary như flow cũ.

## 3.4 Kiểm thử

- [ ] `py_compile` pass.
- [ ] Test route:
  - [ ] câu hỏi đơn giản trên channel `zalo`
  - [ ] yêu cầu local/tool trên channel `zalo`
- [ ] Test direct AI thật qua gateway với `channel='zalo'`.
- [ ] Xác nhận nếu central AI fail thì service vẫn đi fallback legacy.

---

## 4. Exit criteria

- Zalo dùng được `CentralAiCoordinator` cho direct reply và tool path.
- Fallback legacy vẫn an toàn khi central AI lỗi.
- Metadata/log đủ để phân biệt Zalo central AI path và legacy path.
