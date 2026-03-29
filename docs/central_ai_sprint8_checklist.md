# Checklist Sprint 8 - Attachment Và Vision Foundation

Ngày cập nhật: `2026-03-13`

Tài liệu này chi tiết hóa `Sprint 8 - Attachment Và Vision Foundation` trong:
- `docs/central_ai_function_calling_sprint_plan.md`

Mục tiêu của Sprint 8:
- mở đường cho OmniMind xử lý file và ảnh thay vì chỉ text;
- chuẩn hóa artifact contract dùng chung cho AI, tool và channel transport;
- đưa vision/OCR vào AI trung tâm qua OpenAPI gateway;
- nối intake file/image từ Telegram vào flow coordinator;
- chuẩn bị nền cho attachment flow của Zalo ở sprint sau.

---

## 1. Phạm vi Sprint 8

Sprint này làm:
- tạo artifact contract dùng chung;
- cho AI trung tâm đọc ảnh qua vision endpoint;
- chuẩn hóa file/image từ Telegram để đưa vào coordinator;
- log và capture payload attachment từ Zalo ở mức nghiên cứu.

Sprint này chưa làm:
- chưa hoàn thiện full attachment pipeline cho Zalo;
- chưa có upload/download manager tổng quát cho mọi loại file lớn;
- chưa có UI duyệt artifact trong app desktop.

## Trạng thái hiện tại

Trạng thái cập nhật ngày `2026-03-13`:
- Đã thêm `ArtifactManager` và artifact contract dùng chung cho image, text-like document và unsupported binary.
- `CentralAiCoordinator` đã hiểu `attachments`, route được sang:
  - `vision_direct` cho ảnh hợp lệ;
  - `tool_calling` cho document text-like;
  - trả lỗi thân thiện nếu attachment không hợp lệ hoặc chưa hỗ trợ.
- `AiGatewayClient` đã có helper đọc ảnh local và gọi vision endpoint.
- `TelegramBotService` đã normalize photo/document thành artifact trước khi gửi vào coordinator.
- `ZaloBotService` mới dừng ở mức capture/log attachment candidates từ raw payload để nghiên cứu phase sau.
- Đã test thật:
  - vision với ảnh local thành công;
  - invalid attachment trả về hướng dẫn thân thiện cho user.

---

## 2. File mục tiêu

### Tạo mới
- [docs/central_ai_sprint8_checklist.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/central_ai_sprint8_checklist.md)
- [src/engine/artifact_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/artifact_manager.py)
- [scripts/test_vision_artifact_flow.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/scripts/test_vision_artifact_flow.py)

### Cập nhật
- [src/engine/ai_gateway_client.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/ai_gateway_client.py)
- [src/engine/central_ai_coordinator.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/central_ai_coordinator.py)
- [src/engine/telegram_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/telegram_bot_service.py)
- [src/engine/zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)

---

## 3. Checklist triển khai

## 3.1 Artifact contract dùng chung

- [x] Định nghĩa schema artifact chuẩn:
  - [x] `artifact_id`
  - [x] `type`
  - [x] `path`
  - [x] `mime_type`
  - [x] `size_bytes`
  - [x] `source_channel`
  - [x] `source_message_id`
  - [x] `metadata`
- [x] Tạo `ArtifactManager` để normalize artifact.
- [x] Thêm helper detect loại artifact:
  - [x] image
  - [x] document
  - [ ] generated_file
  - [x] unknown_binary

## 3.2 Vision/OCR qua gateway

- [x] Chuẩn hóa API `vision_completion(...)` để dùng được từ coordinator.
- [x] Thêm helper đọc ảnh local:
  - [x] convert local file -> base64 hoặc URL strategy phù hợp
  - [x] validate mime type
- [x] Thêm prompt vision mặc định:
  - [x] mô tả ảnh
  - [ ] OCR text
  - [x] tóm tắt nội dung ảnh
- [x] Ghi rõ error mapping khi:
  - [x] file không phải ảnh
  - [x] ảnh quá lớn
  - [x] gateway vision lỗi

## 3.3 Telegram attachment intake

- [x] Chuẩn hóa output của `_download_telegram_file(...)` thành artifact metadata.
- [x] Khi nhận:
  - [x] photo
  - [x] document
  - [x] caption
  thì tạo `attachments/artifacts` trong request gửi vào `CentralAiCoordinator`.
- [x] Nếu là ảnh:
  - [x] AI có thể chọn vision flow
  - [x] hoặc tool/text flow tùy request
- [x] Nếu là document text-like:
  - [x] gắn local path/artifact cho tool loop dùng `read_local_file`

## 3.4 Central AI attachment-aware flow

- [x] Mở rộng request contract của coordinator để dùng `attachments`.
- [x] Nếu request có artifact ảnh:
  - [x] cho phép đi vision path
- [x] Nếu request có artifact file:
  - [x] cho phép đi tool loop với local path
- [x] Final reply vẫn phải do AI trung tâm sinh ra sau khi có kết quả vision/tool.

## 3.5 Zalo attachment foundation

- [x] Capture thêm raw payload có attachment metadata từ listener nếu có.
- [x] Ghi note/log riêng cho attachment candidates của Zalo.
- [x] Chưa cần download file thật, nhưng phải đủ dữ liệu để nghiên cứu phase sau.
- [ ] Cập nhật backlog/note kỹ thuật nếu phát hiện schema payload mới.

## 3.6 Kiểm thử

- [x] `py_compile` pass.
- [x] Test vision thật với một ảnh công khai hoặc local image.
- [ ] Test Telegram photo -> coordinator -> AI reply.
- [ ] Test Telegram document -> coordinator -> tool loop -> AI reply.
- [ ] Test log capture cho payload attachment của Zalo nếu có mẫu data.

## 3.7 Invalid input và invalid attachment handling

- [x] Chuẩn hóa nhóm lỗi đầu vào:
  - [x] file không tồn tại
  - [x] file sai định dạng
  - [x] mime type không hỗ trợ
  - [x] file quá lớn
  - [x] ảnh hỏng hoặc đọc không được
  - [ ] user gửi file nhưng yêu cầu không khớp loại file
- [x] Tạo error contract thân thiện cho attachment/vision flow:
  - [x] `code`
  - [x] `message`
  - [x] `user_hint`
  - [ ] `artifact_path` nếu có
- [x] Nếu input sai:
  - [x] không crash pipeline
  - [x] không để AI bịa là đã xử lý xong
  - [x] trả hướng dẫn rõ cho user nên gửi lại gì
- [ ] Test các case:
  - [ ] ảnh giả mạo extension
  - [ ] file rỗng
  - [x] file binary không đọc được như text
  - [ ] file vượt giới hạn size
  - [x] message không có text nhưng chỉ có attachment
  - [ ] request yêu cầu OCR nhưng lại gửi file không phải ảnh
  - [ ] request yêu cầu đọc tài liệu nhưng file không phải loại hỗ trợ
- [ ] Ghi log riêng cho invalid attachment để dễ debug production.

---

## 4. Exit criteria

- OmniMind có artifact contract dùng chung.
- AI trung tâm xử lý được ít nhất 1 case ảnh qua vision.
- Telegram file/image đi được vào coordinator flow có cấu trúc.
- Zalo attachment đã có foundation log/payload để làm sprint sau.
