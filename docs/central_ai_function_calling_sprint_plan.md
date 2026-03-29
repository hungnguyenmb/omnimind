# Sprint Plan - Central AI Và Function Calling Cho OmniMind

Ngày cập nhật: `2026-03-13`

Tài liệu này chia kế hoạch nâng cấp OmniMind thành các sprint triển khai cụ thể, bám theo định hướng trong:
- `docs/central_ai_function_calling_upgrade_plan.md`
- `docs/skill_tool_function_standard.md`
- `docs/OPENAPI_CONTENT_VISION_PLAN.md`

Mục tiêu tổng:
- thêm lớp AI trung tâm dùng model API ngoài để phản hồi nhanh;
- chỉ gọi Codex cho tác vụ local phức tạp;
- hỗ trợ function calling cho built-in tool và installed skills;
- cho phép kết quả tool/skill quay lại AI để sinh final response rồi gửi ra Telegram/Zalo.

---

## Sprint 1 - OpenAPI Gateway Foundation

## Mục tiêu
Tạo nền móng để OmniMind gọi được AI API ngoài một cách ổn định và có cấu hình riêng cho AI trung tâm.

## Phạm vi
- Thêm config/env cho OpenAPI gateway.
- Tạo client chung để gọi:
  - text chat;
  - vision/OCR;
  - model listing;
  - chuẩn bị chỗ cho tool/function calling.
- Chưa thay thế luồng Telegram/Zalo cũ.

## File dự kiến
- `[NEW] src/engine/ai_gateway_client.py`
- `[MODIFY] src/engine/config_manager.py`
- `[MODIFY] src/ui/pages/auth_page.py`

## Checklist
- [ ] Thêm config:
  - [ ] `openapi_proxy_base`
  - [ ] `openapi_proxy_api_key`
  - [ ] `openapi_proxy_text_model`
  - [ ] `openapi_proxy_image_model`
- [ ] Tạo `AiGatewayClient` với helper:
  - [ ] `list_models()`
  - [ ] `chat_completion(...)`
  - [ ] `vision_completion(...)`
  - [ ] `chat_with_tools(...)`
- [ ] Thêm timeout/retry/friendly error mapping.
- [ ] Verify `gpt-5.4` hoạt động với text chat.
- [ ] Verify payload vision/OCR hoạt động với `image_url`.
- [ ] Xác minh thật function calling có được OpenAPI gateway hỗ trợ theo schema nào.

## Exit criteria
- OmniMind gọi được OpenAPI gateway bằng API key cấu hình.
- Có 1 client dùng lại được cho AI trung tâm.
- Đã xác nhận thật format tool/function calling của endpoint.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- Đã triển khai `AiGatewayClient`, config gateway trong `ConfigManager`, UI cấu hình/probe trong `AuthPage`.
- Đã test thật:
  - `/models` thành công
  - text chat `gpt-5.4` thành công
  - vision với `image_url` thành công
  - tool calling probe thành công và có `tool_calls`
- Kết luận: Sprint 1 đã đạt mục tiêu chính và có thể coi là hoàn tất phần foundation.

---

## Sprint 2 - Central AI Coordinator Skeleton

## Mục tiêu
Tạo lớp AI trung tâm làm bộ não điều phối, nhưng mới xử lý direct reply và fallback về luồng cũ.

## Phạm vi
- Thêm `CentralAiCoordinator`.
- Chưa chạy skill function thực sự.
- Chỉ hỗ trợ:
  - direct reply;
  - fallback sang Codex path cũ khi cần.

## File dự kiến
- `[NEW] src/engine/central_ai_coordinator.py`
- `[MODIFY] src/engine/conversation_orchestrator.py`
- `[MODIFY] src/engine/codex_runtime_bridge.py`

## Checklist
- [ ] Định nghĩa request contract chung cho AI trung tâm:
  - [ ] channel
  - [ ] user_text
  - [ ] thread_id/chat_id
  - [ ] context/messages
  - [ ] attachments/artifacts placeholder
- [ ] Định nghĩa response contract chung:
  - [ ] `reply_text`
  - [ ] `artifacts`
  - [ ] `trace`
  - [ ] `used_tools`
- [ ] Tạo mode quyết định ban đầu:
  - [ ] `reply_direct`
  - [ ] `escalate_to_codex`
- [ ] Tạo rule gate đơn giản:
  - [ ] câu hỏi thông thường -> direct reply
  - [ ] yêu cầu đọc/sửa/chạy local -> fallback Codex
- [ ] Ghi log decision vào runtime logs.

## Exit criteria
- Có một coordinator callable độc lập.
- Coordinator trả lời được câu hỏi đơn giản mà không gọi Codex.
- Các case local phức tạp vẫn fallback về Codex path cũ an toàn.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- Đã triển khai `CentralAiCoordinator` skeleton.
- Đã có request/response contract chung, decision trace và runtime log riêng.
- Đã test thật:
  - câu hỏi đơn giản đi `reply_direct` và trả lời thành công qua `gpt-5.4`
  - yêu cầu local kiểu đọc file đi `escalate_to_codex`
  - nhánh Codex fallback trả lời thành công qua `app-server`
- Kết luận: Sprint 2 đã đạt mục tiêu skeleton ban đầu.

---

## Sprint 3 - Telegram Integration

## Mục tiêu
Đưa Telegram qua AI trung tâm, nhưng vẫn giữ rollback path nếu coordinator fail.

## Phạm vi
- Tách `TelegramBotService` khỏi việc gọi Codex trực tiếp.
- Dùng AI trung tâm cho direct reply.
- Chưa mở full function calling nhiều bước.

## File dự kiến
- `[MODIFY] src/engine/telegram_bot_service.py`
- `[MODIFY] src/engine/memory_manager.py`
- `[MODIFY] src/engine/assistant_memory_manager.py`

## Checklist
- [ ] `TelegramBotService` gọi `CentralAiCoordinator` thay vì tự build prompt rồi gọi Codex trực tiếp cho mọi case.
- [ ] Giữ fallback path nếu coordinator lỗi hoặc timeout.
- [ ] Chuẩn hóa luồng memory:
  - [ ] inbound user message
  - [ ] decision trace
  - [ ] final assistant reply
- [ ] Verify streaming hoặc non-streaming output vẫn ổn với Telegram.
- [ ] Verify không làm hỏng luồng gửi file hiện có của Telegram.

## Exit criteria
- Telegram dùng được AI trung tâm cho direct reply.
- Không regression các case Telegram đang chạy ổn.
- Có fallback path rõ ràng nếu gateway lỗi.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- Đã nối `TelegramBotService` sang `CentralAiCoordinator` ở bước routing.
- Nhánh `reply_direct` hiện đi qua AI trung tâm và trả lời thật bằng gateway.
- Nhánh local/Codex vẫn giữ luồng cũ của Telegram để bảo toàn:
  - streaming preview;
  - runtime directives;
  - artifact send/document flow.
- Đã test:
  - route quyết định đúng giữa `reply_direct` và `escalate_to_codex`
  - direct AI path thành công qua `gpt-5.4`
- Backlog còn lại chuyển sang sprint sau:
  - chưa chuyển Telegram sang built-in tool calling path của AI trung tâm cho các yêu cầu local;
  - chưa có `FunctionRegistry` và `FunctionExecutor` để AI trung tâm tự gọi tool built-in;
  - chưa có approval policy chuẩn cho built-in function;
  - chưa có tool result loop `AI -> function -> AI -> final reply`;
  - chưa unify hoàn toàn memory/trace giữa direct path và Codex path;
  - chưa để `CentralAiCoordinator` tự quản installed skill execution.
- Kết luận: Sprint 3 đã đạt mục tiêu tích hợp Telegram ở mức an toàn và có rollback path rõ ràng.

---

## Sprint 4 - Built-in Function Registry Và Executor

## Mục tiêu
Cho AI trung tâm gọi được built-in tool thật thay vì chỉ trả lời hoặc fallback Codex.

## Phạm vi
- Tạo registry và executor cho built-in functions.
- Chưa tích hợp skill function từ marketplace.

## File dự kiến
- `[NEW] src/engine/function_registry.py`
- `[NEW] src/engine/function_executor.py`
- `[MODIFY] src/engine/action_executor.py`
- `[MODIFY] src/engine/config_manager.py`

## Checklist
- [ ] Định nghĩa schema tool/function nội bộ.
- [ ] Đăng ký built-in functions đầu tiên:
  - [ ] đọc file local
  - [ ] ghi/sửa file local
  - [ ] chạy shell command có kiểm soát
  - [ ] lấy system info
- [ ] Thêm capability model:
  - [ ] `fs_read`
  - [ ] `fs_write`
  - [ ] `exec`
  - [ ] `network`
- [ ] Thêm approval policy check.
- [ ] Chuẩn hóa function result contract.
- [ ] Cho AI trung tâm chạy 1 vòng:
  - [ ] user -> tool call
  - [ ] tool result -> AI
  - [ ] AI final reply

## Exit criteria
- AI gọi được ít nhất 2 built-in functions thật.
- Tool result quay lại AI để sinh final reply.
- Có audit log tối thiểu cho built-in function execution.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- Đã thêm `FunctionRegistry` và `FunctionExecutor`.
- Đã mở rộng capability model cho:
  - `fs_read`
  - `fs_write`
  - `exec`
  - `network`
- Đã đăng ký built-in functions nền tảng:
  - `get_system_info`
  - `read_local_file`
  - `write_local_file`
  - `run_shell_command`
- Đã expose thêm một số runtime actions dạng function:
  - `runtime_ping`
  - `screen_capture`
  - `camera_snapshot`
  - `ui_automation_type_text`
  - `system_restart`
- `CentralAiCoordinator` đã chạy được vòng:
  - AI chọn tool
  - app thực thi built-in function thật
  - kết quả function quay lại AI
  - AI sinh final reply
- `TelegramBotService` đã nhận diện được nhánh `tool_calling` và vẫn có fallback legacy về Codex nếu built-in path fail.
- Đã test thật qua gateway:
  - `read_local_file` thành công và AI tóm tắt được nội dung file
  - `get_system_info` thành công và AI tóm tắt được thông tin máy
- Phần còn lại cho sprint sau:
  - chưa có approval UI/xác nhận nhiều bước cho function `on-request`
  - chưa load function từ installed skills
  - chưa có multi-step tool loop nhiều vòng
- Kết luận: Sprint 4 đã đạt mục tiêu built-in function calling ở mức một vòng thực thi an toàn.

---

## Sprint 5 - Skill Function Standard Và Local Loading

## Mục tiêu
Cho OmniMind nạp function từ installed skills theo manifest chuẩn.

## Phạm vi
- Parse `tool_manifest.json`.
- Đăng ký function từ installed skills.
- Chưa rollout mạnh ra marketplace production.

## File dự kiến
- `[MODIFY] src/engine/skill_manager.py`
- `[MODIFY] src/engine/skill_runtime_manager.py`
- `[MODIFY] src/engine/skill_action_runners.py`

## Checklist
- [ ] Parse `tool_manifest.json` khi quét installed skill.
- [ ] Validate:
  - [ ] schema
  - [ ] entrypoint tồn tại
  - [ ] required_capabilities
  - [ ] approval_policy
- [ ] Đăng ký skill functions vào `FunctionRegistry`.
- [ ] Tạo executor cho `python_script`.
- [ ] Cho phép disable function lỗi mà không làm hỏng cả skill.
- [ ] Thêm 1 skill mẫu để test local end-to-end.

## Exit criteria
- Ít nhất 1 installed skill expose function thành công.
- AI trung tâm gọi được skill function thật.
- Output của skill đi đúng contract chuẩn.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- `SkillManager` đã parse được `tool_manifest.json` từ installed skills.
- Skill functions hợp lệ đã được đưa vào `FunctionRegistry`.
- `FunctionExecutor` đã thực thi được `skill_function` qua script runtime hiện có.
- Đã thêm script test local cho sample skill function.
- Đã test thật:
  - parse manifest thành công
  - executor chạy sample skill function thành công
  - AI trung tâm gọi sample skill function qua gateway và trả final reply đúng
- Lỗi manifest của function được skip theo từng function, không làm hỏng cả skill.
- Phần còn lại cho sprint sau:
  - chưa có UI bật/tắt từng skill function
  - chưa đồng bộ function metadata với backend/CMS
  - chưa có multi-step tool loop nhiều hơn 1 vòng
- Kết luận: Sprint 5 đã đạt mục tiêu local loading cho installed skill functions.

---

## Sprint 6 - Multi-step Tool Loop

## Mục tiêu
Biến AI trung tâm thành agent loop có giới hạn, không chỉ là router một bước.

## Phạm vi
- Cho phép nhiều hơn 1 lần tool call trong một request.
- Tool result luôn quay lại AI trước khi trả lời user.

## File dự kiến
- `[MODIFY] src/engine/central_ai_coordinator.py`
- `[MODIFY] src/engine/function_executor.py`
- `[MODIFY] src/engine/ai_gateway_client.py`

## Checklist
- [ ] Thêm vòng lặp tối đa `3-5` bước.
- [ ] Thêm timeout tổng.
- [ ] Thêm hard stop chống loop vô hạn.
- [ ] Log từng bước:
  - [ ] tool selected
  - [ ] args
  - [ ] result
  - [ ] final reply
- [ ] Support:
  - [ ] direct reply ngay từ đầu
  - [ ] 1 tool call rồi trả lời
  - [ ] nhiều tool call nối tiếp
  - [ ] tool fail rồi AI giải thích lỗi

## Exit criteria
- Coordinator xử lý được multi-step task có tool loop.
- Không xảy ra loop vô hạn.
- Có trace/debug đủ để phân tích.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- `CentralAiCoordinator` đã được nâng lên thành multi-step tool loop.
- Đã thêm config guard cho loop:
  - `central_ai_tool_loop_max_steps`
  - `central_ai_tool_loop_timeout_sec`
  - `central_ai_tool_loop_max_calls_per_step`
- Đã có:
  - timeout tổng cho tool loop
  - hard stop khi chạm max steps
  - hard stop khi phát hiện lặp lại cùng function + arguments
  - trace từng step trong `tool_loop_trace`
- Đã test thật qua gateway:
  - request dùng `get_system_info` + `read_local_file`
  - request lỗi lặp `read_local_file` và dừng đúng ở `repeated_tool_calls`
- Kết luận: Sprint 6 đã đạt mục tiêu multi-step tool loop ở mức runtime ổn định.

---

## Sprint 7 - Zalo Integration Qua Central AI

## Mục tiêu
Đưa luồng Zalo sang AI trung tâm giống Telegram.

## Phạm vi
- Zalo dùng coordinator cho direct reply và tool loop text-based.
- Chưa làm attachment/file intake từ Zalo.

## File dự kiến
- `[MODIFY] src/engine/zalo_bot_service.py`
- `[MODIFY] src/engine/zalo_prompt_builder.py`
- `[MODIFY] src/engine/zalo_memory_manager.py`

## Checklist
- [ ] `ZaloBotService` gọi `CentralAiCoordinator`.
- [ ] Chuẩn hóa request context cho Zalo:
  - [ ] thread_id
  - [ ] group/dm
  - [ ] mention state
  - [ ] recent bundle text
- [ ] Verify Zalo direct reply.
- [ ] Verify Zalo tool loop text-based.
- [ ] Final response vẫn đi qua policy mention/group allowlist hiện có.

## Exit criteria
- Zalo dùng được AI trung tâm cho text flow.
- Không làm vỡ logic debounce, dedupe, bootstrap hiện có.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- `ZaloBotService` đã tích hợp `CentralAiCoordinator`.
- Zalo bundle hiện route theo:
  - `reply_direct` -> AI trung tâm
  - `tool_calling` -> AI trung tâm
  - fail -> fallback legacy qua `ZaloPromptBuilder + Codex`
- Đã giữ tương thích flow cũ:
  - typing heartbeat
  - outbound chunk send
  - runtime skill directives ở nhánh legacy
  - summary refresh và outbound store
- Đã test thật ở mức coordinator path với `channel='zalo'`:
  - direct AI thành công
  - tool path với `get_system_info` thành công
- Kết luận: Sprint 7 đã đạt mục tiêu tích hợp Zalo với AI trung tâm ở mức an toàn, có fallback legacy rõ ràng.

---

## Sprint 8 - Attachment Và Vision Foundation

## Mục tiêu
Mở đường cho AI xử lý file/ảnh qua Telegram trước, và chuẩn bị cho Zalo sau.

## Phạm vi
- Chuẩn hóa artifact contract dùng chung.
- Vision/OCR đi qua OpenAPI gateway.
- Zalo attachment mới ở mức nghiên cứu/payload capture.

## File dự kiến
- `[MODIFY] src/engine/ai_gateway_client.py`
- `[MODIFY] src/engine/telegram_bot_service.py`
- `[NEW] src/engine/artifact_manager.py`

## Checklist
- [ ] Tạo artifact contract dùng chung:
  - [ ] file
  - [ ] image
  - [ ] generated document
- [ ] Cho AI trung tâm đọc ảnh qua vision endpoint.
- [ ] Cho Telegram file/image đi vào coordinator.
- [ ] Log và capture payload Zalo attachment để nghiên cứu phase sau.
- [ ] Viết note kỹ thuật cho `Zalo attachment intake`.

## Exit criteria
- Telegram file/image có thể đi vào AI trung tâm.
- Vision/OCR hoạt động qua gateway.
- Có dữ liệu thật để thiết kế Zalo attachment phase sau.

## Trạng thái kiểm tra
Trạng thái cập nhật ngày `2026-03-13`:
- Đã thêm `ArtifactManager` để chuẩn hóa artifact contract cho:
  - image
  - text-like document
  - unsupported binary
- `AiGatewayClient` đã có helper vision cho ảnh local.
- `CentralAiCoordinator` đã hiểu `attachments`, route được:
  - `vision_direct` khi có ảnh hợp lệ
  - `tool_calling` khi có document text-like hoặc yêu cầu local
  - trả lỗi thân thiện nếu attachment chưa hỗ trợ hoặc không hợp lệ
- `TelegramBotService` đã normalize photo/document thành artifact và đưa vào request của coordinator.
- `ZaloBotService` đã có foundation log cho attachment candidates từ raw payload, nhưng chưa tải file thật.
- Đã test thật:
  - `py_compile` pass cho các file Sprint 8
  - vision với ảnh local thật thành công qua gateway
  - invalid binary attachment trả về hướng dẫn thân thiện cho user
- Phần còn lại cho sprint sau:
  - chưa có end-to-end test đầy đủ cho Telegram photo/document với bot thật
  - chưa có invalid attachment audit log riêng
  - chưa có download/normalization attachment thật cho Zalo
  - chưa có OCR prompt flow chuyên biệt
- Kết luận: Sprint 8 đã hoàn tất phần foundation cho attachment và vision, còn phần hardening sẽ chuyển sang sprint sau.

---

## Sprint 9 - UI, Config Và Operator Tools

## Mục tiêu
Cho phép bật/tắt, cấu hình và quan sát AI trung tâm trong app.

## Phạm vi
- UI cấu hình provider/model.
- UI debug tối thiểu cho traces.

## File dự kiến
- `[MODIFY] src/ui/pages/auth_page.py`
- `[MODIFY] src/ui/pages/dashboard_page.py`
- `[MODIFY] src/engine/config_manager.py`

## Checklist
- [ ] UI nhập:
  - [ ] API base
  - [ ] API key
  - [ ] text model
  - [ ] image model
- [ ] UI chọn mode:
  - [ ] ưu tiên direct AI
  - [ ] ưu tiên Codex
  - [ ] hybrid
- [ ] Dashboard hiển thị:
  - [ ] AI gateway status
  - [ ] model hiện tại
  - [ ] số lần dùng tool
  - [ ] latency gần nhất
- [ ] Có viewer log/traces cơ bản cho 1 request gần nhất.

## Exit criteria
- Có thể vận hành và debug AI trung tâm từ UI.
- Không cần sửa tay config DB cho các thao tác thường xuyên.

---

## Sprint 10 - Hardening, QA Và Rollout

## Mục tiêu
Ổn định hóa trước khi coi kiến trúc mới là đường chính.

## Phạm vi
- test
- fallback
- observability
- release checklist

## File dự kiến
- `[NEW] scripts/test_central_ai_gateway.py`
- `[NEW] scripts/test_function_registry.py`
- `[MODIFY] docs/sprint6_release_checklist_and_rollback_playbook.md`

## Checklist
- [ ] Test:
  - [ ] direct reply
  - [ ] built-in function
  - [ ] skill function
  - [ ] tool fail
  - [ ] gateway timeout
  - [ ] fallback Codex
  - [ ] Telegram path
  - [ ] Zalo path
- [ ] Rate limit / timeout handling.
- [ ] Sensitive data masking trong logs.
- [ ] Rollback switch:
  - [ ] tắt central AI
  - [ ] quay về Codex-first path
- [ ] Cập nhật checklist release riêng cho AI gateway.

## Exit criteria
- Có đủ test và rollback để phát hành an toàn.
- Kiến trúc mới có thể bật production từng phần.

---

## Thứ tự ưu tiên khuyến nghị

Nên triển khai theo thứ tự:
1. Sprint 1
2. Sprint 2
3. Sprint 3
4. Sprint 4
5. Sprint 5
6. Sprint 6
7. Sprint 7
8. Sprint 9
9. Sprint 10
10. Sprint 8

Ghi chú:
- Sprint 8 có thể làm sớm hơn nếu nhu cầu file/image cấp bách.
- Zalo attachment vẫn nên coi là backlog tách riêng, không khóa đường đi của text flow.

---

## Definition of Done tổng cho chương trình nâng cấp

Chương trình được xem là hoàn tất khi:
- OmniMind có AI trung tâm hoạt động ổn định qua gateway;
- Telegram và Zalo dùng chung một lớp điều phối;
- built-in functions và skill functions chạy được qua function calling;
- tool result quay lại AI để sinh final response;
- Codex chỉ còn là executor cho nhóm tác vụ local phức tạp;
- có UI cấu hình, trace tối thiểu, test tối thiểu và rollback path rõ ràng.
