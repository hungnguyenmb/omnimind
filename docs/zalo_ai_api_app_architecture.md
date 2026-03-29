# Zalo AI API App Architecture

Tài liệu này mô tả lại luồng xử lý tin nhắn Zalo đang chạy trong `projects/omnimind`, nhưng được viết theo góc nhìn kiến trúc tổng quát để đội khác có thể xây một app mới dùng AI API thông thường thay vì phụ thuộc vào Codex runtime.

Mục tiêu của bản thiết kế này là giữ lại các phần đã chứng minh là hữu ích:
- listener ổn định
- dedupe
- debounce theo thread
- memory cục bộ theo thread
- prompt builder có context
- skill/tool execution tách riêng khỏi model
- outbound sender có retry

Không nhất thiết phải giữ nguyên công nghệ hiện tại. Phần quan trọng là giữ đúng thứ tự xử lý và các ranh giới giữa các lớp.

## 1. Phạm vi và mục tiêu

App mới cần làm được các việc sau:
- Nhận tin nhắn mới từ Zalo hoặc một bridge tương đương.
- Gom nhiều tin liên tiếp của cùng một thread trước khi gọi AI.
- Lưu lịch sử hội thoại cục bộ để dùng làm context.
- Sinh prompt từ memory đã tóm tắt, fact, và recent turns.
- Gọi một AI API bên ngoài để lấy câu trả lời.
- Cho phép model phát tool directive hoặc function call để chạy hành động thật.
- Gửi phản hồi ngược về Zalo.
- Lưu lại toàn bộ inbound, outbound, summary, dead-letter để debug.

App mới không cần phụ thuộc vào:
- Codex CLI
- Codex bridge
- prompt format riêng của Codex

Thay vào đó có thể dùng:
- OpenAI Responses/Chat API
- Anthropic API
- Gemini API
- hoặc một AI gateway nội bộ

## 2. Thành phần chính trong OmniMind hiện tại

Luồng hiện tại được trải trên các file sau:
- `src/engine/zalo_bot_service.py`
- `src/engine/zalo_prompt_builder.py`
- `src/engine/zalo_memory_manager.py`
- `src/engine/zalo_models.py`
- `src/engine/codex_runtime_bridge.py`
- `src/engine/skill_manager.py`

Nếu xây app mới, có thể tách thành các service độc lập:
- `ZaloListener`
- `InboundNormalizer`
- `ThreadDispatcher`
- `ConversationMemoryStore`
- `PromptBuilder`
- `AiClient`
- `ToolExecutor`
- `OutboundSender`
- `ObservabilityLogger`

## 3. Luồng xử lý end-to-end

### 3.1. Listener nhận sự kiện

Listener hiện tại đọc output từ OpenZCA runtime, mỗi dòng là một JSON event.

Việc cần làm:
- nhận raw event
- parse thành object chuẩn hóa
- bỏ qua lifecycle event nếu không liên quan
- đưa message event vào hàng đợi nội bộ

Model dữ liệu logic tối thiểu:

```json
{
  "thread_id": "string",
  "sender_id": "string",
  "chat_type": "dm|group",
  "content": "string",
  "mentions": ["user-id"],
  "timestamp": "iso-or-epoch",
  "message_id": "string",
  "raw_payload": {}
}
```

### 3.2. Normalize inbound event

Trong OmniMind, bước này được gói trong `ZaloInboundEvent.from_raw_payload(...)`.

App mới nên chuẩn hóa ngay từ đầu:
- `thread_id`
- `sender_id`
- `chat_type`
- `content`
- `message_id`
- `timestamp`
- `mentions`

Lợi ích:
- các bước sau không cần hiểu payload riêng của OpenZCA
- có thể thay listener nguồn khác mà không ảnh hưởng lõi xử lý

### 3.3. Dedupe

Trước khi xử lý, hệ thống tạo một dedupe key:
- ưu tiên `thread_id + message_id`
- nếu không có `message_id` thì fallback `thread_id + sender_id + timestamp + content`

Nếu message đã thấy trong TTL cache thì bỏ qua.

Mục đích:
- tránh reply trùng
- tránh lưu trùng message vào DB
- chống trường hợp listener emit lặp

Khuyến nghị cho app mới:
- dùng memory TTL cache cho tốc độ
- nếu cần an toàn hơn, kết hợp unique key trong database

### 3.4. Gating: có nên auto-reply không

Trong OmniMind, một event chỉ được đưa vào flow trả lời khi qua các điều kiện:
- không phải message do chính tài khoản bot gửi
- bot đang bật
- auto reply đang bật
- nếu là group chat thì phải mention đúng bot
- nếu dùng allowlist thì thread phải nằm trong danh sách được phép

Đây là bước cực quan trọng để giảm nhiễu.

Khuyến nghị cho app mới:
- tách logic gating thành một policy riêng
- policy nên trả về cả `allow/deny` và `reason`
- reason phải được log ra để dễ debug

Ví dụ:

```json
{
  "allowed": false,
  "reason": "no_mention"
}
```

### 3.5. Lưu inbound vào memory store

Ngay cả khi bot quyết định không trả lời, OmniMind vẫn lưu inbound message vào DB cục bộ.

Lý do:
- dùng làm context cho lần sau
- lưu dấu vết sự kiện thật
- phục vụ bootstrap, summary, audit, debug

Tối thiểu cần các bảng hoặc collection tương đương:
- `threads`
- `messages`
- `thread_summaries`
- `thread_facts`

### 3.6. Debounce theo thread

Đây là một điểm rất đáng giữ.

OmniMind không gọi AI ngay khi vừa có một message mới. Nó gom message theo `thread_id`, đợi một khoảng debounce ngắn rồi xử lý cả bundle.

Behavior hiện tại:
- DM có debounce ngắn hơn
- Group có debounce dài hơn
- nếu thread vừa nhận tin mới khi còn idle, bot gửi typing indicator ngay

Ví dụ:
- người dùng nhắn 3 tin liên tiếp trong 1 giây
- hệ thống chờ debounce
- AI chỉ bị gọi 1 lần với cả bundle 3 tin

Lợi ích:
- giảm số lần gọi AI
- bám đúng ngữ cảnh hội thoại thật
- tránh trả lời vội từng mảnh

### 3.7. Bootstrap history

Trước khi xử lý một thread lần đầu, OmniMind cố nhập một lượng tin gần đây từ nguồn chat để seed local memory.

Luồng:
- kiểm tra thread đã bootstrap chưa
- nếu chưa, gọi API/lệnh lấy recent messages
- import về local DB
- đánh dấu bootstrap done

Mục đích:
- để AI không trả lời “mù” ngay lần đầu
- có ít nhất một đoạn lịch sử gần đây cho prompt

App mới nên giữ cơ chế này.

### 3.8. Build bundle text

Nếu thread chỉ có 1 tin mới:
- bundle text chính là nội dung tin đó

Nếu thread có nhiều tin mới:
- bundle text được dựng thành một đoạn có đánh số

Ví dụ:

```text
Người dùng vừa gửi liên tiếp 3 tin nhắn trên Zalo:
1. Anh kiểm tra giúp em
2. Báo giá bên kia chưa
3. Nếu chưa thì nhắc lại giúp em
```

Đây là một cách khá hiệu quả để model hiểu “nhiều tin liên tiếp nhưng cùng một lượt ý”.

### 3.9. Build thread context

Đây là lớp giúp prompt ngắn mà vẫn đủ ngữ cảnh.

OmniMind hiện build context từ 4 nguồn:
- `thread metadata`
- `latest summary` và vài summary gần nhất
- `thread facts`
- `recent turns`

#### Thread metadata

Bao gồm:
- `thread_id`
- `chat_type`
- `display_name`
- `participant_hint`

#### Summaries

Summary là bản tóm tắt cuộn của thread.

Sau mỗi turn xử lý xong, hệ thống sinh summary từ khoảng 10-14 message gần nhất rồi lưu lại.

Mục đích:
- giảm số token phải gửi mỗi lần
- không cần nhét toàn bộ raw history vào prompt

#### Facts

Facts là các preference hoặc instruction ngắn được trích từ tin nhắn người dùng.

Các pattern hiện tại là các câu kiểu:
- `tôi muốn...`
- `hãy luôn...`
- `ưu tiên...`
- `đừng...`
- `không được...`

Facts được lưu riêng và tăng `hit_count` theo thời gian.

#### Recent turns

Từ raw messages, hệ thống build thành turns kiểu:
- user
- assistant

Rồi nhét một số turn gần nhất vào prompt trong giới hạn char budget.

#### Char budget

OmniMind không nhét context vô hạn.

Nó có một budget ký tự, rồi nhét vào theo thứ tự:
- summaries
- facts
- recent turns

cho đến khi gần chạm budget.

Đây là kỹ thuật nên giữ trong app mới, kể cả khi sau này dùng token budget thay vì char budget.

### 3.10. Build prompt

Prompt builder hiện tại ghép các khối sau:
- persona chung
- nguyên tắc Zalo cấu hình bởi operator
- latest summary
- recent summaries
- facts
- recent turns
- metadata thread
- hướng dẫn tool runtime
- bundle text mới nhất
- yêu cầu format output

Điểm quan trọng:
- prompt không nên chỉ là “hãy trả lời tin nhắn này”
- nó phải có cấu trúc cố định
- các khối context cần được làm sạch trước khi ghép

Đề xuất cho app mới:
- giữ `PromptBuilder` là một lớp riêng
- không build prompt rải rác trong business code
- cho phép đổi provider AI mà không đụng logic memory

### 3.11. Gọi AI API

Trong OmniMind hiện tại, bước này đi qua `CodexRuntimeBridge.stream_reply(...)`.

Khi xây app mới, thay thế bằng một interface trung lập:

```python
class AiClient:
    def generate(self, prompt: str, model: str, timeout_sec: int) -> dict:
        ...
```

Output chuẩn hóa nên có:

```json
{
  "success": true,
  "output_text": "...",
  "provider": "openai",
  "model": "gpt-5-mini",
  "latency_ms": 1234,
  "usage": {
    "input_tokens": 1000,
    "output_tokens": 120
  }
}
```

Khuyến nghị:
- log thời gian gọi model
- log model thực tế đang dùng
- log token usage nếu provider hỗ trợ
- có timeout chặt thay vì chờ quá lâu

### 3.12. Parse tool directive hoặc function call

Đây là phần then chốt để biến model từ “người nói” thành “người làm”.

Trong OmniMind hiện tại, model có thể phát chuỗi text kiểu:

```text
[[OMNIMIND_RUN_SKILL:skill_id=google-sheet-ledger-writer;payload_json={...};auto_request_permissions=true]]
```

Sau đó app:
- bóc directive ra khỏi text
- parse payload
- chạy skill thật

Nếu xây app mới bằng AI API hiện đại, nên cân nhắc dùng:
- function calling
- JSON schema tool call
- structured output

Thay vì regex trên text tự do.

Tuy nhiên, dù dùng cách nào, kiến trúc nên vẫn là:
- model quyết định có cần tool không
- app parse tool request
- app thực thi tool ngoài model
- app lấy kết quả tool rồi dựng outbound cuối

### 3.13. Execute tool hoặc skill

Trong OmniMind, bước này đi qua `SkillManager.execute_installed_skill(...)`.

Tool executor nên là lớp riêng.

Input:
- `tool_name`
- `payload`
- `timeout`
- `permission policy`

Output chuẩn:

```json
{
  "success": true,
  "code": "",
  "message": "Tool chạy thành công",
  "data": {}
}
```

Nếu thất bại:

```json
{
  "success": false,
  "code": "PERMISSION_REQUIRED",
  "message": "Thiếu quyền ghi file",
  "data": {
    "missing_permissions": ["disk_write"]
  }
}
```

Điều quan trọng là:
- không để model tự giả vờ “đã làm xong”
- chỉ khi tool chạy xong mới được kết luận thành công

### 3.14. Compose final outbound text

Sau khi có:
- cleaned model text
- kết quả tool thật

hệ thống compose ra message cuối cùng.

Logic hiện tại:
- nếu model text rỗng nhưng tool có user-facing message thì dùng message từ tool
- sanitize text cho giống một tin nhắn chat thật
- bỏ heading, markdown, bullet quá máy móc

App mới nên có một bước `OutboundComposer`.

### 3.15. Gửi message ra Zalo

OmniMind gửi outbound theo chunk:
- mỗi chunk tối đa `1800` ký tự
- retry một lần nếu lỗi
- log failure vào dead-letter

Đây là lớp nên giữ độc lập với AI.

Giao diện nên kiểu:

```python
class ChatSender:
    def send_text(self, thread_id: str, text: str, is_group: bool) -> dict:
        ...
```

### 3.16. Persist outbound và refresh summary

Sau khi gửi thành công:
- outbound message được lưu lại vào memory store
- thread summary được refresh
- interaction được log

Đây là bước rất quan trọng để turn tiếp theo có context đúng.

## 4. Kiến trúc module đề xuất cho app mới

### 4.1. Listener layer

Nhiệm vụ:
- nhận raw event
- parse JSON
- chuẩn hóa message event
- đẩy vào queue

### 4.2. Policy layer

Nhiệm vụ:
- quyết định có xử lý hay không
- kiểm tra self message
- mention gating
- allowlist
- bot enabled

### 4.3. Dispatcher layer

Nhiệm vụ:
- buffer event theo `thread_id`
- debounce
- mở worker xử lý cho từng thread

### 4.4. Memory layer

Nhiệm vụ:
- lưu messages
- lưu threads
- lưu summaries
- lưu facts
- bootstrap history
- build context

### 4.5. AI layer

Nhiệm vụ:
- build prompt hoặc tool schema
- gọi provider API
- trả về response chuẩn hóa

### 4.6. Tool layer

Nhiệm vụ:
- chạy action thật
- kiểm soát permission
- chuẩn hóa output và error

### 4.7. Delivery layer

Nhiệm vụ:
- gửi typing indicator
- gửi outbound text
- retry
- split chunks

### 4.8. Observability layer

Nhiệm vụ:
- inbound log
- outbound log
- dead letter
- latency metrics
- model usage
- tool usage

## 5. Data model tối thiểu

### 5.1. threads

Gợi ý field:
- `thread_id`
- `chat_type`
- `display_name`
- `participant_hint`
- `last_message_at`
- `last_bootstrap_at`
- `bootstrap_done`
- `updated_at`

### 5.2. messages

Gợi ý field:
- `id`
- `thread_id`
- `chat_type`
- `sender_id`
- `message_id`
- `direction`
- `content`
- `mentions_json`
- `raw_json`
- `timestamp`
- `created_at`

### 5.3. thread_summaries

Gợi ý field:
- `id`
- `thread_id`
- `summary_text`
- `from_ts`
- `to_ts`
- `message_count`
- `source`
- `updated_at`

### 5.4. thread_facts

Gợi ý field:
- `id`
- `thread_id`
- `fact`
- `confidence`
- `hit_count`
- `last_seen_at`
- `created_at`
- `updated_at`

## 6. Những quyết định kiến trúc nên giữ

### 6.1. Tool execution phải tách khỏi model

Đây là nguyên tắc số 1.

Model chỉ nên:
- hiểu ngôn ngữ
- quyết định có cần tool không
- đề xuất payload cho tool

App mới phải là nơi:
- parse tool request
- chạy tool thật
- kiểm chứng success/failure
- quyết định outbound cuối

### 6.2. Debounce theo thread là bắt buộc

Nếu bỏ debounce:
- AI bị gọi quá nhiều
- trả lời vội từng tin
- mất tự nhiên

### 6.3. Local memory là bắt buộc

Không nên chỉ dựa vào model context của từng lượt.

Phải có local store cho:
- recent messages
- summaries
- facts
- thread metadata

### 6.4. Summary cuộn quan trọng hơn việc giữ full raw trong prompt

Raw history vẫn phải lưu.

Nhưng prompt hằng lượt nên ưu tiên:
- summary
- recent turns
- facts

thay vì dump toàn bộ lịch sử.

### 6.5. Gating trước khi gọi AI

Không phải tin nào cũng cần vào AI.

Cần lọc sớm:
- no mention
- self message
- duplicate
- bot disabled

### 6.6. Observability phải có từ đầu

Ít nhất phải có:
- inbound events log
- outbound events log
- dead-letter log
- model latency
- tool latency
- error reason

## 7. Cách thay Codex bằng AI API

### 7.1. Thay bridge bằng AI adapter

Hiện tại OmniMind dùng `CodexRuntimeBridge`.

App mới nên thay bằng:

```python
class AiAdapter:
    def reply(self, prompt: str, model: str, timeout_sec: int, tools: list[dict] | None = None) -> dict:
        ...
```

### 7.2. Ưu tiên function calling nếu provider hỗ trợ

Nếu dùng OpenAI hoặc provider có tool call chính thức:
- định nghĩa tool schema
- cho model call tool bằng structured payload
- app nhận tool call dưới dạng JSON

Cách này tốt hơn regex directive text vì:
- ít lỗi parse hơn
- ít prompt hơn
- ít phụ thuộc vào wording

### 7.3. Nếu provider không hỗ trợ tool calling

Vẫn có thể dùng “machine directive trong text” như OmniMind hiện tại.

Nhưng cần:
- format rất cứng
- parser tách riêng
- chặn model tự khẳng định thành công nếu tool chưa chạy

## 8. Sequence đề xuất cho app mới

```text
Zalo Listener
  -> Normalize inbound event
  -> Dedupe
  -> Store inbound
  -> Gating policy
  -> Thread debounce buffer
  -> Bootstrap history if needed
  -> Build bundle text
  -> Build thread context
  -> Build prompt / tool schema
  -> Call AI API
  -> Parse tool calls
  -> Execute tools
  -> Compose final outbound
  -> Send response
  -> Store outbound
  -> Refresh summary
  -> Write logs/metrics
```

## 9. Interface contract đề xuất

### 9.1. Inbound event contract

```json
{
  "thread_id": "123",
  "sender_id": "456",
  "chat_type": "group",
  "content": "@Bot vay anh Thắng 10000000",
  "mentions": ["bot-user-id"],
  "timestamp": "2026-03-12T23:11:39Z",
  "message_id": "abc",
  "raw_payload": {}
}
```

### 9.2. AI result contract

```json
{
  "success": true,
  "output_text": "Đã nhận.",
  "tool_calls": [
    {
      "tool_name": "google_sheet_ledger_write",
      "arguments": {
        "content": "Vay anh Thắng",
        "entry_mode": "direct_total",
        "direct_total_value": 10000000,
        "sign_hint": "negative",
        "raw_message": "Vay anh Thắng 10000000"
      }
    }
  ],
  "latency_ms": 1800
}
```

### 9.3. Tool result contract

```json
{
  "success": true,
  "message": "Đã thêm vào Google Sheet",
  "data": {
    "row_number": 13,
    "saved_values": {
      "date": "12/03/2026 23:15:11",
      "content": "Vay anh Thắng",
      "col_c": "",
      "col_d": "",
      "col_e": -10000000
    }
  }
}
```

## 10. Khuyến nghị nếu bắt đầu dự án mới

### 10.1. Tối thiểu hóa prompt

Đừng nhét toàn bộ business rule vào skill mô tả dài.

Nên tách:
- prompt: rule nhận diện ngắn, persona, tool policy
- tool code: validation và business logic thật

### 10.2. Dùng structured tool calls nếu được

Nếu AI API hỗ trợ, đây là lựa chọn tốt hơn text directive.

### 10.3. Thêm timing log theo từng chặng

Ít nhất cần đo:
- listener to buffer
- buffer to model start
- model latency
- tool latency
- outbound latency

Nếu không có các mốc này, rất khó phân tích chậm ở đâu.

### 10.4. Cho phép fallback rule-based tool trigger

Với một số pattern rất rõ như kế toán, có thể thêm fallback:
- nếu message match chắc chắn một rule
- app tự gọi tool ngay
- không chờ model nghĩ lại toàn bộ

Điều này giúp giảm latency và tăng độ ổn định.

## 11. File hiện tại nên tham khảo khi clone logic

Nếu đội khác muốn đọc code nguồn để triển khai nhanh hơn, ưu tiên các file này:
- [zalo_bot_service.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_bot_service.py)
- [zalo_prompt_builder.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_prompt_builder.py)
- [zalo_memory_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_memory_manager.py)
- [zalo_models.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/zalo_models.py)

## 12. Kết luận

Giá trị lớn nhất của luồng Zalo hiện tại không nằm ở Codex, mà nằm ở kiến trúc xử lý:
- normalize event
- dedupe
- gating
- debounce theo thread
- local memory
- prompt builder có summary và facts
- tool execution tách khỏi model
- outbound sender có retry

Nếu xây app mới dùng AI API, chỉ cần thay lớp gọi model và lớp tool-call format. Phần còn lại của kiến trúc vẫn nên giữ gần như nguyên vẹn.
