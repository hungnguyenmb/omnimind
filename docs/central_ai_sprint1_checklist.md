# Checklist Sprint 1 - OpenAPI Gateway Foundation

Ngày cập nhật: `2026-03-13`

Tài liệu này chi tiết hóa `Sprint 1 - OpenAPI Gateway Foundation` trong:
- `docs/central_ai_function_calling_sprint_plan.md`

Mục tiêu của Sprint 1:
- tạo nền móng để OmniMind gọi được AI API ngoài một cách ổn định;
- cấu hình được gateway cho AI trung tâm;
- có client chung để dùng lại cho text chat, vision/OCR và chuẩn bị cho function calling;
- chưa thay thế luồng Telegram/Zalo hiện tại.

## Trạng thái hiện tại

Trạng thái cập nhật ngày `2026-03-13`:
- Đã triển khai:
  - `ConfigManager` cho OpenAPI gateway
  - `AiGatewayClient`
  - UI cấu hình/test gateway trong `AuthPage`
  - script probe `scripts/test_openapi_gateway.py`
- Đã verify thật bằng API:
  - `GET /models` -> `200 OK`
  - text chat với `gpt-5.4` -> `200 OK`
  - vision qua `chat/completions` với `image_url` -> `200 OK`
  - tool calling probe -> `200 OK`, có `tool_calls`
- Kết luận:
  - phần nền tảng kỹ thuật của Sprint 1 đã đạt mục tiêu chính;
  - các test âm như `API key sai`, `base URL sai`, `base64 OCR` vẫn nên giữ là checklist bổ sung khi làm hardening.

---

## 1. Phạm vi Sprint 1

Sprint này chỉ làm các phần nền:
- cấu hình gateway và model;
- client gọi API;
- test kết nối thật;
- xác minh format response;
- xác minh function calling có được hỗ trợ hay không.

Sprint này chưa làm:
- chưa thêm `CentralAiCoordinator`;
- chưa đổi Telegram/Zalo sang AI trung tâm;
- chưa chạy tool loop;
- chưa parse skill function manifest.

---

## 2. File mục tiêu

### Tạo mới
- [src/engine/ai_gateway_client.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/ai_gateway_client.py)

### Cập nhật
- [src/engine/config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)
- [src/ui/pages/auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

### Tài liệu liên quan
- [OPENAPI_CONTENT_VISION_PLAN.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/OPENAPI_CONTENT_VISION_PLAN.md)
- [central_ai_function_calling_upgrade_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_function_calling_upgrade_plan.md)

---

## 3. Checklist triển khai

## 3.1 Chuẩn bị cấu hình

- [ ] Chốt tên config dùng trong app cho gateway:
  - [ ] `openapi_proxy_base`
  - [ ] `openapi_proxy_api_key`
  - [ ] `openapi_proxy_text_model`
  - [ ] `openapi_proxy_image_model`
  - [ ] `openapi_proxy_image_predict_base`
- [ ] Quyết định thứ tự ưu tiên đọc config:
  - [ ] ENV
  - [ ] `app_configs`
  - [ ] fallback mặc định
- [ ] Chốt model mặc định cho text:
  - [ ] `gpt-5.4`
- [ ] Chốt model mặc định cho image generation:
  - [ ] `imagen-4.0-fast-generate-001`
- [ ] Chốt quy tắc không log lộ API key ra file log/UI.

## 3.2 Cập nhật `ConfigManager`

- [ ] Thêm getter cho:
  - [ ] `get_openapi_proxy_base()`
  - [ ] `get_openapi_proxy_api_key()`
  - [ ] `get_openapi_proxy_text_model()`
  - [ ] `get_openapi_proxy_image_model()`
  - [ ] `get_openapi_proxy_image_predict_base()`
- [ ] Thêm setter tương ứng nếu cần lưu từ UI.
- [ ] Đánh dấu `openapi_proxy_api_key` là sensitive config.
- [ ] Đảm bảo key nhạy cảm được dùng cùng cơ chế mã hóa như `telegram_token` và `license_jwt`.
- [ ] Đảm bảo getter trả về fallback hợp lý nếu config trống.

## 3.3 Tạo `AiGatewayClient`

- [ ] Tạo class `AiGatewayClient`.
- [ ] Thêm helper build header:
  - [ ] `Authorization: Bearer ...`
  - [ ] `Content-Type: application/json`
- [ ] Thêm helper build base URL từ `ConfigManager`.
- [ ] Tích hợp retry và timeout.
- [ ] Tích hợp error mapping thân thiện.
- [ ] Không log full API key.

### Các method tối thiểu cần có
- [ ] `list_models()`
- [ ] `chat_completion(messages, model="", temperature=None, max_tokens=None, extra_payload=None)`
- [ ] `vision_completion(prompt_text, image_url=None, image_base64=None, model="")`
- [ ] `chat_with_tools(messages, tools, tool_choice=None, model="", extra_payload=None)`

### Yêu cầu cho `vision_completion`
- [ ] Hỗ trợ `image_url` công khai.
- [ ] Hỗ trợ `data:image/...;base64,...`.
- [ ] Validate không cho đồng thời `image_url` và `image_base64` sai logic.

### Yêu cầu cho `chat_with_tools`
- [ ] Chưa cần dùng trong runtime chính.
- [ ] Bắt buộc lưu raw response mẫu để phân tích schema.
- [ ] Nếu gateway chưa support tool calling, phải trả lỗi rõ ràng.

## 3.4 Chuẩn hóa response contract của client

- [ ] Chốt format trả về chung cho `AiGatewayClient`:
  - [ ] `success`
  - [ ] `message`
  - [ ] `data`
  - [ ] `raw`
  - [ ] `status_code`
- [ ] Có helper tách text output từ `chat.completions`.
- [ ] Có helper tách model list.
- [ ] Với vision, có helper tách nội dung text mô tả/OCR.
- [ ] Với tool calling, có helper phát hiện:
  - [ ] tool calls
  - [ ] finish_reason
  - [ ] content text fallback

## 3.5 Tích hợp UI tối thiểu trong `AuthPage`

- [ ] Thêm khu vực hiển thị cấu hình OpenAPI gateway.
- [ ] Có ô nhập:
  - [ ] base URL
  - [ ] API key
  - [ ] text model
  - [ ] image model
- [ ] Có nút test kết nối.
- [ ] Có nhãn trạng thái:
  - [ ] kết nối thành công
  - [ ] lỗi xác thực
  - [ ] timeout
  - [ ] model không tồn tại
- [ ] Không hiển thị full API key sau khi lưu.

## 3.6 Viết test/manual verification helper

- [ ] Có script hoặc helper test nội bộ:
  - [ ] gọi `/models`
  - [ ] gọi text chat đơn giản
  - [ ] gọi vision với 1 ảnh mẫu
  - [ ] gọi thử payload tools nếu gateway hỗ trợ
- [ ] Lưu kết quả test vào log debug hoặc report ngắn.

Khuyến nghị file:
- [ ] `scripts/test_openapi_gateway.py`

## 3.7 Xác minh thật function calling

Đây là hạng mục bắt buộc của Sprint 1.

- [ ] Gọi thử `/chat/completions` với payload có `tools`.
- [ ] Ghi nhận gateway có chấp nhận hay không.
- [ ] Nếu chấp nhận:
  - [ ] ghi lại format request đúng
  - [ ] ghi lại format response đúng
  - [ ] xác nhận field `tool_calls` hoặc tương đương
- [ ] Nếu không chấp nhận:
  - [ ] ghi rõ lỗi
  - [ ] xác định cần fallback schema hay endpoint khác
- [ ] Cập nhật lại tài liệu sau khi test thật.

---

## 4. Checklist kiểm thử thủ công

## 4.1 Kết nối cơ bản

- [ ] Test `list_models()` thành công.
- [ ] Có `gpt-5.4` trong danh sách model hoặc xác nhận model alias tương đương.
- [ ] API key sai trả lỗi dễ hiểu.
- [ ] Base URL sai trả lỗi dễ hiểu.

## 4.2 Text chat

- [ ] Gọi prompt đơn giản và nhận text trả lời.
- [ ] Unicode tiếng Việt hiển thị đúng.
- [ ] Timeout ngắn được xử lý đúng, không treo UI.

## 4.3 Vision/OCR

- [ ] Gọi với `image_url` công khai thành công.
- [ ] Gọi với `base64` thành công.
- [ ] Trả lỗi rõ nếu ảnh sai định dạng hoặc quá lớn.

## 4.4 Tool calling probe

- [ ] Gửi payload có `tools`.
- [ ] Ghi nhận response thực tế.
- [ ] Chốt được kết luận:
  - [ ] gateway hỗ trợ tool calling đầy đủ
  - [ ] hoặc chưa hỗ trợ / hỗ trợ khác chuẩn

---

## 5. Rủi ro trong Sprint 1

### 5.1 Gateway không hỗ trợ tool calling như kỳ vọng
- Cách xử lý:
  - vẫn hoàn thành Sprint 1 với text + vision;
  - ghi rõ kết quả xác minh;
  - dời decision cuối về Sprint 2 hoặc 4.

### 5.2 Lộ API key trong log/UI
- Cách xử lý:
  - mask key trong log;
  - lưu key theo cơ chế sensitive config;
  - không render full key trong giao diện.

### 5.3 UI bị phụ thuộc quá sớm vào runtime mới
- Cách xử lý:
  - UI Sprint 1 chỉ là cấu hình + test kết nối;
  - chưa gắn vào Telegram/Zalo runtime.

### 5.4 Timeout làm treo giao diện
- Cách xử lý:
  - mọi call test từ UI phải chạy qua worker thread.

---

## 6. Exit criteria

Sprint 1 chỉ được xem là xong khi thỏa cả các điều kiện:
- [x] OmniMind lưu và đọc được cấu hình OpenAPI gateway.
- [x] `AiGatewayClient` gọi được `/models`.
- [x] `AiGatewayClient` gọi được text chat với `gpt-5.4`.
- [x] `AiGatewayClient` gọi được vision/OCR qua `chat/completions`.
- [x] API key được bảo vệ như sensitive config.
- [x] Có test kết nối từ UI hoặc script nội bộ.
- [x] Đã xác minh bằng test thật gateway có hỗ trợ function calling hay không.
- [x] Kết quả xác minh đã được ghi lại trong tài liệu.

---

## 7. Đầu ra mong muốn sau Sprint 1

Sau Sprint 1, OmniMind phải có:
- một client gateway dùng lại được;
- cấu hình gateway lưu được trong app;
- khả năng gọi model text và vision độc lập với Codex;
- dữ liệu thực tế để quyết định thiết kế function calling cho Sprint sau.

Sprint 1 hoàn tất không đồng nghĩa AI trung tâm đã hoạt động end-to-end. Nó chỉ tạo nền móng kỹ thuật để Sprint 2 bắt đầu triển khai `CentralAiCoordinator`.
