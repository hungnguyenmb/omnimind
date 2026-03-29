# Kế Hoạch Nâng Cấp OmniMind Với AI Trung Tâm Và Function Calling

Ngày cập nhật: `2026-03-13`

Tài liệu này tổng hợp các quyết định kiến trúc đã thống nhất để nâng cấp `projects/omnimind` theo hướng:
- thêm `1` lớp AI trung tâm để điều phối hội thoại;
- ưu tiên phản hồi nhanh bằng model API bên ngoài;
- chỉ đẩy các tác vụ cần thao tác local sang Codex, built-in tool hoặc skill;
- hỗ trợ function calling/tool calling theo kiểu động;
- sau khi tool/skill chạy xong, kết quả phải quay lại cho AI xử lý rồi mới gửi ra Zalo/Telegram.

---

## 1. Vấn đề hiện tại

Trạng thái hiện tại của OmniMind:
- `TelegramBotService` và `ZaloBotService` xử lý message rồi khá nhanh đẩy xuống `CodexRuntimeBridge`.
- Codex đang bị dùng cho cả:
  - câu hỏi cần trả lời thông thường;
  - công việc local như đọc/sửa file, chạy lệnh, chạy skill.

Hệ quả:
- độ trễ cao với các câu hỏi đơn giản;
- tiêu tốn runtime Codex không cần thiết;
- trải nghiệm người dùng không tốt khi chỉ cần một câu trả lời nhanh.

Mục tiêu nâng cấp:
- tách `lớp quyết định` khỏi `lớp thực thi`;
- cho phép AI trung tâm tự quyết định:
  - trả lời trực tiếp;
  - gọi function/tool;
  - chạy skill;
  - hoặc chuyển sang Codex với các tác vụ local phức tạp.

---

## 2. Định hướng kiến trúc mới

### 2.1 Nguyên tắc cốt lõi

OmniMind sẽ có `1` lớp AI trung tâm chạy trên model API bên ngoài, ví dụ:
- OpenAI
- Gemini
- AI Gateway nội bộ trong tương lai

Lớp này có 3 vai trò:
1. nhận context hội thoại từ Telegram/Zalo;
2. chọn cách xử lý phù hợp nhất;
3. tổng hợp kết quả cuối cùng để gửi lại người dùng.

### 2.2 Cách chia lớp

Kiến trúc mục tiêu:

```text
Telegram/Zalo/UI
    -> CentralAiCoordinator
        -> FunctionRegistry
        -> BuiltinFunctionExecutor
        -> SkillFunctionExecutor
        -> CodexRuntimeExecutor
        -> Memory/Context Managers
    -> Channel Responder
```

Phân tách trách nhiệm:
- `Transport layer`
  - nhận/gửi tin nhắn;
  - không tự quyết định nghiệp vụ.
- `Central AI layer`
  - route và điều phối;
  - dùng function calling;
  - quyết định trả lời trực tiếp hay cần tool.
- `Execution layer`
  - built-in action;
  - installed skill;
  - Codex runtime.
- `Memory layer`
  - cung cấp context, facts, summaries, recent turns.

---

## 3. Hành vi mục tiêu của AI trung tâm

### 3.1 Các mode xử lý

AI trung tâm cần chuẩn hóa quyết định về 4 mode:
- `reply_direct`
- `run_builtin_function`
- `run_skill_function`
- `escalate_to_codex`

Không nên để AI phản hồi bằng văn bản tự do để chỉ định tác vụ. Thay vào đó cần có schema quyết định rõ ràng.

Ví dụ:

```json
{
  "mode": "reply_direct",
  "reason": "simple_question",
  "reply_text": "Nội dung trả lời nhanh",
  "function_name": "",
  "skill_id": "",
  "arguments": {}
}
```

### 3.2 Rule gate trước khi tới model

Khuyến nghị có một lớp rule-based gate trước AI router:
- nếu rõ ràng là thao tác file/local system thì cho phép route thẳng sang executor;
- nếu rõ ràng là câu hỏi thông thường thì có thể để AI trung tâm trả lời trực tiếp;
- nếu mơ hồ thì đưa vào model để quyết định.

Mục tiêu:
- giảm token và độ trễ;
- tránh router AI phân loại sai trong những case quá rõ.

---

## 4. Function calling trong OmniMind sẽ hoạt động thế nào

### 4.1 Nguyên tắc đúng

`Function calling` không phải là upload code lên OpenAI/Gemini.

Điều thực sự xảy ra:
- OmniMind gửi `tool schema` kèm theo mỗi request model;
- model trả về `tool call`;
- OmniMind tự map `tool call` đó sang code thật đang tồn tại ở local.

### 4.2 Hai loại function

#### Built-in functions

Code nằm sẵn trong OmniMind.

Ví dụ:
- đọc file;
- ghi file;
- sửa file;
- chạy shell command;
- lấy system info;
- trigger action có sẵn trong app.

#### Skill functions

Code không nằm sẵn trong app, mà nằm trong skill đã được cài local.

Ví dụ:
- tạo báo cáo Excel;
- điền form;
- xuất biên bản họp;
- tool automation đặc thù.

Skill sau khi cài local sẽ expose metadata để AI thấy được function schema.

### 4.3 Không có chuyện "upload function lên model provider"

Cần chốt lại:
- Cái được upload lên hệ thống OmniMind là `skill package` và `function manifest`.
- Đến lúc runtime, `CentralAiCoordinator` mới lấy danh sách function đang khả dụng và gửi kèm API request.
- Function schema là động, phụ thuộc vào:
  - built-in functions đang bật;
  - skills đã cài;
  - permissions/capabilities hiện có.

---

## 5. Vòng lặp xử lý đúng cho agent

### 5.1 Luồng mục tiêu

Luồng đúng cần là:

```text
User message
-> Central AI
-> tool/function/skill/Codex
-> execution result
-> Central AI post-process
-> final user reply
-> send via Telegram/Zalo
```

### 5.2 Vì sao phải quay lại cho AI sau khi tool chạy xong

Không nên đẩy raw result của tool ra thẳng cho user trong flow mặc định.

Nên để AI trung tâm:
- đọc kết quả kỹ thuật;
- tổng hợp lại thành ngôn ngữ tự nhiên;
- quyết định có cần gọi thêm tool tiếp không;
- gửi final answer phù hợp văn phong từng kênh.

Ví dụ:
- tool đọc log trả về hàng trăm dòng;
- AI rút gọn thành `lỗi chính là database timeout`.

Hoặc:
- skill tạo file thành công;
- AI nói lại `đã tạo xong báo cáo` và nếu cần thì kênh Telegram gửi thêm artifact.

### 5.3 Giới hạn vòng lặp

Cần có guard:
- tối đa `3-5` lần gọi tool trong `1` yêu cầu;
- timeout tổng;
- chống loop vô hạn;
- log đầy đủ từng bước.

---

## 6. Đề xuất module mới

### 6.1 Engine modules mới

#### `[NEW] src/engine/central_ai_coordinator.py`

Trách nhiệm:
- nhận input đã được normalize từ Telegram/Zalo;
- build context;
- lấy danh sách tools đang khả dụng;
- gọi model API;
- xử lý vòng lặp tool calling;
- trả final response và artifacts cho transport.

#### `[NEW] src/engine/function_registry.py`

Trách nhiệm:
- đăng ký built-in functions;
- đăng ký skill functions từ skill đã cài;
- lọc function theo capability, channel, policy;
- xuất schema tool cho OpenAI/Gemini.

#### `[NEW] src/engine/function_executor.py`

Trách nhiệm:
- validate arguments;
- map function sang executor phù hợp;
- trả kết quả chuẩn hóa.

#### `[NEW] src/engine/ai_gateway_client.py`

Trách nhiệm:
- adapter chung cho OpenAI/Gemini;
- function/tool calling API;
- cấu hình model nhanh và model nặng.

### 6.2 Modules hiện có cần sửa

#### `[MODIFY] src/engine/skill_manager.py`
- parse thêm tool/function manifest;
- expose danh sách function từ skill đã cài;
- chạy skill function theo entrypoint.

#### `[MODIFY] src/engine/action_executor.py`
- chuẩn hóa output để AI có thể đọc tiếp.

#### `[MODIFY] src/engine/codex_runtime_bridge.py`
- đổi vai trò thành `CodexRuntimeExecutor`;
- chỉ được gọi khi central AI quyết định escalate.

#### `[MODIFY] src/engine/telegram_bot_service.py`
- không build prompt và gọi Codex trực tiếp nữa;
- gọi `CentralAiCoordinator`.

#### `[MODIFY] src/engine/zalo_bot_service.py`
- tương tự Telegram path;
- nhận final response từ coordinator rồi mới gửi outbound.

#### `[MODIFY] src/engine/config_manager.py`
- thêm config cho AI provider, AI router model, final responder model, tool loop limits.

---

## 7. Runtime contract để quyết định và thực thi

### 7.1 Decision contract

AI/router phải trả về cấu trúc rõ:

```json
{
  "mode": "reply_direct|run_builtin_function|run_skill_function|escalate_to_codex",
  "reason": "string",
  "reply_text": "string",
  "function_name": "string",
  "arguments": {},
  "tool_choice_confidence": 0.0
}
```

### 7.2 Function execution result contract

Mỗi executor nên trả về cùng một schema:

```json
{
  "success": true,
  "message": "Tóm tắt kỹ thuật ngắn",
  "data": {},
  "artifacts": [],
  "error_code": "",
  "error_detail": "",
  "requires_human_approval": false
}
```

Trong đó:
- `message`: mô tả ngắn để AI đọc tiếp;
- `data`: payload có cấu trúc;
- `artifacts`: file path, image path, generated documents;
- `error_*`: để AI biết cách giải thích lỗi cho user.

### 7.3 Channel response contract

Coordinator nên trả về cho transport:

```json
{
  "success": true,
  "reply_text": "Nội dung gửi ra kênh chat",
  "artifacts": [
    {
      "type": "file",
      "path": "/tmp/report.xlsx",
      "caption": "Báo cáo đã tạo"
    }
  ],
  "trace": {
    "mode": "run_skill_function",
    "steps": 2
  }
}
```

---

## 8. Tích hợp với hệ thống skill hiện có

### 8.1 Nguyên tắc

Không tạo hệ thống function calling tách rời khỏi marketplace skill.

Nên tái sử dụng `skill package` hiện có và bổ sung `function manifest`.

Một skill có thể:
- không expose function nào;
- expose `1` hoặc nhiều function.

### 8.2 Đồng bộ package skill và function

Mục tiêu:
- skill vẫn được đóng gói và publish như cũ;
- client vẫn cài skill như cũ;
- sau khi cài, registry đọc thêm function schema và đăng ký tool.

Như vậy:
- store của OmniMind trở thành plugin marketplace;
- AI thấy được tools động theo bộ skill đã cài trên máy.

---

## 9. Kế hoạch triển khai theo pha

### Phase 1 - Foundation
- thêm `CentralAiCoordinator` ở mức skeleton;
- thêm `FunctionRegistry` cho built-in functions;
- thêm `AI Gateway Client` hỗ trợ một provider đầu tiên;
- đổi Telegram path sang coordinator, giữ fallback về Codex cũ.

Exit criteria:
- câu hỏi đơn giản được trả lời mà không cần gọi Codex;
- built-in function có thể chạy và trả kết quả ngược lại cho AI.

### Phase 2 - Skill Function Integration
- mở rộng `SkillManager` để parse tool manifest;
- registry auto-load function từ installed skills;
- thêm `SkillFunctionExecutor`;
- bổ sung validate schema và capability.

Exit criteria:
- một skill local có thể expose function và được model gọi thành công.

### Phase 3 - Multi-channel Agent Loop
- đổi Zalo path sang coordinator;
- chuẩn hóa final response contract cho Telegram/Zalo;
- hỗ trợ artifact/file response.

Exit criteria:
- kết quả tool/skill quay lại AI và gửi được final response ra cả Telegram và Zalo.

### Phase 4 - Codex Escalation Policy
- chỉ định khi nào được dùng Codex;
- bổ sung escalation policy;
- tách rõ task cần shell/file edit/code execution phức tạp.

Exit criteria:
- Codex chỉ còn được gọi cho local workflow phức tạp, không dùng cho FAQ thông thường.

### Phase 5 - Observability
- log decision của router;
- log tool call và tool result;
- log final reply và latency;
- có cơ chế debug theo thread.

Exit criteria:
- có thể truy vết đầy đủ `message -> decision -> tool -> final response`.

---

## 10. Rủi ro và cách giảm thiểu

### 10.1 Router quyết định sai
- giảm thiểu bằng rule gate trước AI;
- thêm confidence + fallback.

### 10.2 Tool nguy hiểm bị gọi tự do
- bắt buộc capability model;
- check approval policy trước execute;
- audit log đầy đủ.

### 10.3 Skill khai báo function sai
- validate schema lúc install;
- validate lại lúc execute;
- skill lỗi thì disable function đó.

### 10.4 Loop quá nhiều bước
- giới hạn step count;
- timeout tổng;
- hard stop và trả lời lịch sự khi vượt ngưỡng.

---

## 11. Ghi chú backlog: Zalo attachment intake

Trạng thái hiện tại:
- luồng Zalo mới xử lý ổn định phần text message;
- chưa có luồng hoàn chỉnh để nhận file đính kèm từ Zalo rồi tải về local cho AI xử lý;
- chưa có bước chuẩn hóa attachment thành artifact dùng chung cho AI trung tâm.

Các điểm đã xác nhận trong code:
- `ZaloInboundEvent` hiện chỉ chuẩn hóa `thread_id`, `sender_id`, `chat_type`, `content`, `mentions`, `timestamp`, `message_id`, `raw_payload`;
- `OpenZcaManager` hiện có wrapper cho `msg recent`, `msg send`, `msg typing`, nhưng chưa có wrapper tải file/media attachment;
- `ZaloBotService` hiện chưa có bước detect attachment, download file, lưu local path hoặc bơm artifact vào AI flow.

Hướng nghiên cứu sau:
1. Xác minh payload thật của OpenZCA khi Zalo gửi ảnh, file, audio, video.
2. Thiết kế `attachment normalizer` cho Zalo:
   - loại file
   - tên file
   - mime type
   - remote url hoặc file token
   - metadata OCR/vision nếu là ảnh
3. Thêm `download manager` để tải attachment về app data.
4. Chuẩn hóa output thành `artifacts` để `CentralAiCoordinator` dùng chung với Telegram.
5. Bổ sung policy:
   - giới hạn dung lượng
   - timeout tải file
   - whitelist loại file cho AI đọc
   - fallback khi tải lỗi hoặc file không hỗ trợ

Mục tiêu sau cùng:
- user gửi file qua Zalo;
- OmniMind tải file về local;
- AI trung tâm hoặc tool/skill đọc file đó;
- kết quả quay lại cho AI rồi mới gửi final response ra Zalo.

---

## 12. Định nghĩa thành công

OmniMind được xem là hoàn tất hướng nâng cấp này khi đáp ứng:
- có `1` lớp AI trung tâm dùng cho cả Telegram và Zalo;
- AI có thể tự trả lời nhanh nếu không cần local execution;
- AI có thể gọi built-in function hoặc skill function;
- kết quả tool/skill được đưa trở lại cho AI để tổng hợp;
- final response được gửi ra kênh chat, không đẩy raw tool result mặc định;
- Codex chỉ được gọi cho nhóm tác vụ local phức tạp;
- danh sách function/tool được nạp động từ built-in và installed skills.

---

## 13. File liên quan cần mở đầu tiên khi implement

- `src/engine/telegram_bot_service.py`
- `src/engine/zalo_bot_service.py`
- `src/engine/skill_manager.py`
- `src/engine/action_executor.py`
- `src/engine/codex_runtime_bridge.py`
- `src/engine/config_manager.py`
- `src/engine/conversation_orchestrator.py`
- `src/engine/zalo_prompt_builder.py`

Tài liệu chuẩn hóa skill/tool đi kèm:
- `docs/skill_tool_function_standard.md`
