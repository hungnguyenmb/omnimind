# Chuẩn Hóa Taxonomy Hành Vi Và Routing Policy Cho OmniMind

Ngày cập nhật: `2026-03-14`

Tài liệu này tổng hợp và chuẩn hóa các quyết định đã trao đổi để nâng cao khả năng xử lý của OmniMind theo hướng:
- AI trung tâm phản hồi nhanh nhưng không ôm đồm;
- tool/skill chỉ xử lý tác vụ nhỏ, rõ ràng, có biên;
- Codex có vai trò chính thức, không chỉ là fallback mơ hồ;
- hệ thống biết khi nào cần hỏi thêm context, khi nào cần approval, khi nào phải chuyển sang Codex.

Tài liệu này bổ sung cho:
- `docs/central_ai_function_calling_upgrade_plan.md`
- `docs/skill_tool_function_standard.md`
- `docs/central_ai_function_calling_sprint_plan.md`

---

## 1. Mục tiêu

OmniMind cần phân loại yêu cầu người dùng theo cách gần với hành vi của một trợ lý AI cá nhân thật sự, không chỉ theo góc nhìn kỹ thuật `tool có hay không`.

Mục tiêu cụ thể:
- phản hồi nhanh với các yêu cầu thuần ngôn ngữ;
- dùng built-in tool hoặc skill cho tác vụ nhỏ, có đầu vào rõ;
- gọi Codex sớm cho các tác vụ local khám phá, multi-step, coding hoặc workflow mở;
- giảm trường hợp AI trả lời lấp lửng khi thiếu tool phù hợp;
- giảm việc bắt user phải nhớ đường dẫn file hoặc diễn đạt quá máy móc.

---

## 2. Phân Vai Rõ Ràng

## 2.1 AI trung tâm

Vai trò:
- giao tiếp tự nhiên với user;
- hiểu ngữ cảnh hội thoại;
- phân loại yêu cầu;
- quyết định dùng `direct reply`, `tool`, `skill`, hay `Codex`;
- tổng hợp kết quả cuối cùng để gửi lại cho user.

AI trung tâm không nên:
- tự bịa là đã thao tác local;
- cố xử lý các bài toán local khám phá mở khi không có tool phù hợp;
- coi Codex chỉ là fallback sau khi đã trả lời sai.

## 2.2 Tool/Built-in Function

Vai trò:
- xử lý tác vụ nhỏ, bounded, rõ input/output;
- thường chỉ cần 1 bước hoặc vài bước rất ngắn;
- phù hợp cho truy vấn hoặc thao tác local có scope hẹp.

Ví dụ:
- `get_system_info`
- `read_local_file`
- `write_local_file`
- `run_shell_command`
- `screen_capture`

## 2.3 Skill Function

Vai trò:
- xử lý tác vụ chuyên biệt theo nghiệp vụ hoặc workflow đóng gói;
- nằm giữa tool đơn giản và Codex tổng quát;
- thường dùng khi đã có package/manifest chuẩn.

Ví dụ:
- tạo báo cáo;
- ghi ledger;
- điền form;
- xuất biên bản họp;
- xử lý tài liệu theo domain cụ thể.

## 2.4 Codex

Codex phải được định nghĩa là một executor chính thức của hệ thống.

Codex có 2 vai:
- `Codex executor`
  - làm local workflow nhiều bước nhưng mục tiêu đã rõ.
- `Codex agent`
  - tự khám phá, lập kế hoạch, điều tra, đọc repo/workspace, debug, sửa code.

Codex phù hợp khi:
- yêu cầu mang tính local discovery;
- phải tìm file trước khi đọc;
- cần đọc nhiều file rồi tổng hợp;
- cần debug/sửa code/chạy test;
- tool hiện có không đủ diễn đạt công việc.

---

## 3. Nhóm Hành Vi Người Dùng Thường Gặp

## 3.1 Conversation / Knowledge

Ví dụ:
- giải thích khái niệm;
- viết nội dung;
- tóm tắt văn bản;
- gợi ý cách làm;
- trả lời kiến thức chung.

Executor phù hợp:
- `AI trung tâm`

## 3.2 Personal Ops Có Cấu Trúc

Ví dụ:
- kiểm tra email mới;
- xem lịch hôm nay;
- xem task quá hạn;
- lấy thông tin từ CRM/DB đã có schema rõ.

Executor phù hợp:
- `tool` hoặc `skill`

Điều kiện:
- phải có integration hoặc function rõ ràng;
- nếu chưa có integration thì không nên giả vờ trả lời như thật.

## 3.3 Local Ops Xác Định Rõ

Ví dụ:
- đọc file cụ thể;
- ghi file cụ thể;
- chụp màn hình;
- lấy system info;
- chạy lệnh đơn giản, an toàn.

Executor phù hợp:
- `tool`

## 3.4 Exploratory Local

Ví dụ:
- `trong workspace này có gì`
- `tìm file .md rồi tổng hợp`
- `repo này đang dùng config telegram ở đâu`
- `xem thư mục này có gì liên quan đến zalo`

Executor phù hợp:
- ưu tiên `Codex`
- chỉ dùng `tool` nếu đã có bộ discovery tools rõ ràng

## 3.5 Browser / Web Ops

Ví dụ:
- mở trang web;
- vào dashboard;
- lấy báo cáo từ portal;
- đăng nhập rồi thao tác nhiều bước.

Executor phù hợp:
- `tool` nếu có API/browser automation ổn định;
- `Codex` nếu workflow mở, nhiều bước, khó đoán.

## 3.6 Data/Tài Liệu Phân Tích

Ví dụ:
- đọc PDF rồi tóm tắt;
- phân tích CSV/Excel;
- so sánh 3 file;
- kết hợp email + file + notes để tạo insight.

Executor phù hợp:
- `tool + AI trung tâm` nếu dữ liệu đầu vào rõ;
- `Codex` nếu phải khám phá nhiều nguồn hoặc chuẩn hóa nhiều bước.

## 3.7 Coding / Debugging / Repo Work

Ví dụ:
- code cho tôi;
- sửa bug;
- chạy test;
- debug lỗi runtime;
- thêm API;
- refactor module.

Executor phù hợp:
- `Codex`

## 3.8 Workflow Mở / Executive Assistant

Ví dụ:
- chuẩn bị báo cáo cuối ngày;
- dọn email chưa đọc;
- tìm mọi thứ liên quan khách hàng A;
- kiểm tra repo này đang dở gì.

Executor phù hợp:
- `Codex agent`
- hoặc `planner -> Codex`

---

## 4. Taxonomy Chuẩn Cho OmniMind

OmniMind nên chuẩn hóa `task_shape` thành các nhóm sau:

- `conversation`
- `knowledge`
- `personal_ops`
- `local_ops`
- `exploratory_local`
- `browser_ops`
- `document_analysis`
- `coding_ops`
- `high_risk_action`

Ý nghĩa:
- `conversation`, `knowledge`: thường do AI trung tâm xử lý.
- `personal_ops`, `local_ops`: thường đi tool/skill.
- `exploratory_local`, `coding_ops`: thường đi Codex.
- `high_risk_action`: cần approval hoặc chặn.

---

## 5. Decision Contract Mới Cho AI Trung Tâm

Decision contract nên được mở rộng, không chỉ có `mode`.

Ví dụ:

```json
{
  "mode": "reply_direct | tool_calling | run_skill_function | escalate_to_codex | ask_clarification",
  "task_shape": "conversation | personal_ops | local_ops | exploratory_local | browser_ops | document_analysis | coding_ops | high_risk_action",
  "confidence": 0.0,
  "reason": "",
  "missing_context": [],
  "preferred_tool": "",
  "why_not_tool": "",
  "needs_approval": false
}
```

Giải thích:
- `mode`
  - executor cuối cùng được chọn.
- `task_shape`
  - loại công việc ở mức nghiệp vụ.
- `confidence`
  - mức chắc chắn của router.
- `missing_context`
  - thiếu `path`, `workspace`, `account`, `url`, `time_range`, v.v.
- `preferred_tool`
  - tool/skill nên thử trước nếu có.
- `why_not_tool`
  - lý do phải lên Codex.
- `needs_approval`
  - có cần approval trước khi chạy không.

---

## 6. Quy Tắc Routing Thực Dụng

## 6.1 Khi nào AI trung tâm tự trả lời

Chọn `reply_direct` khi:
- yêu cầu thuần ngôn ngữ;
- không cần state local;
- không cần truy vấn hệ thống bên ngoài;
- không cần khám phá file/workspace/repo.

## 6.2 Khi nào dùng tool/skill

Chọn `tool_calling` hoặc `run_skill_function` khi:
- task có input rõ;
- output có thể chuẩn hóa;
- không cần khám phá quá nhiều;
- đã có tool/skill phù hợp.

Ví dụ:
- đọc một file cụ thể;
- chụp màn hình;
- lấy system info;
- gọi API email/lịch đã tích hợp;
- tạo báo cáo bằng skill chuyên biệt.

## 6.3 Khi nào phải gọi Codex sớm

Chọn `escalate_to_codex` khi:
- phải tìm kiếm trong workspace/repo trước khi biết file nào;
- yêu cầu mang tính `exploratory_local`;
- cần đọc nhiều file rồi tổng hợp;
- cần sửa code, debug, chạy lệnh nhiều bước;
- tool hiện có không đủ để mô tả công việc;
- request mơ hồ nhưng rõ là local workflow.

Các pattern nên bias mạnh sang Codex:
- `workspace nào`
- `repo này`
- `trong project này`
- `tìm file`
- `list file`
- `kiểm tra source`
- `xem cấu trúc thư mục`
- `debug`
- `sửa code`
- `chạy test`
- `xem log và phân tích`

## 6.4 Khi nào nên hỏi lại user

Chọn `ask_clarification` khi:
- có nhiều workspace khả dĩ;
- user nói `file đó` nhưng chưa có session focus;
- thao tác có rủi ro cao;
- thiếu context mà không nên tự đoán.

Không nên hỏi lại nếu:
- có thể tự lấy context bằng discovery tool;
- hoặc Codex có thể điều tra an toàn.

---

## 7. Context Discovery Là Nhóm Tool Riêng

Đây là phần rất quan trọng để giảm việc gọi Codex không cần thiết.

OmniMind nên có một nhóm `context discovery tools`:
- `get_current_workspace`
- `list_workspace_roots`
- `list_local_files`
- `search_files_by_name`
- `list_recent_files`
- `get_git_repo_info`

Mục tiêu:
- trả lời các câu hỏi kiểu `đang ở đâu`, `có file nào`, `repo nào đang mở`;
- giúp AI trung tâm tự thu context trước khi quyết định có cần Codex hay không.

Nếu chưa có nhóm tool này:
- các case discovery nên ưu tiên đi Codex thay vì cố trả lời bằng ngôn ngữ.

---

## 8. Session Focus

Mỗi thread Telegram/Zalo nên có state ngắn hạn:
- `active_workspace`
- `active_project`
- `active_task`
- `recent_files`
- `recent_urls`
- `recent_entities`

Lợi ích:
- user không phải lặp `trong repo OmniMind`;
- câu như `mở file config đó` mới có cơ sở để hiểu;
- giảm ambiguity giữa nhiều workspace.

Session focus nên:
- lưu theo thread/chat;
- có TTL;
- được cập nhật khi user hoặc Codex đã xác định rõ workspace/file/task.

---

## 9. Confidence Và Missing Context

AI trung tâm không chỉ chọn `mode`, mà phải tự đánh giá:
- `mình có chắc không`;
- `mình đang thiếu gì`.

Ví dụ:
- `hãy tìm file config telegram`
  - `task_shape = exploratory_local`
  - `confidence = 0.91`
  - `missing_context = []`
  - `mode = escalate_to_codex`

- `đọc file report.csv`
  - nếu chưa có path:
  - `task_shape = local_ops`
  - `confidence = 0.74`
  - `missing_context = ["path"]`
  - `mode = ask_clarification` hoặc `tool_calling` với `search_files_by_name`

Nguyên tắc:
- confidence thấp + local context nặng -> Codex hoặc clarification
- confidence cao + deterministic -> tool

---

## 10. Approval Và Risk Model

OmniMind cần phân biệt:
- `read-only query`
- `mutating action`
- `high-risk action`

## 10.1 Read-only query

Ví dụ:
- đọc file;
- list file;
- lấy system info;
- xem email.

Mặc định:
- cố gắng tự động nếu policy cho phép.

## 10.2 Mutating action

Ví dụ:
- ghi file;
- sửa file;
- gửi email;
- điền form;
- tải file lên web.

Mặc định:
- cần approval hoặc policy rõ.

## 10.3 High-risk action

Ví dụ:
- restart máy;
- xóa nhiều file;
- shell command mở rộng;
- thao tác tài khoản production.

Mặc định:
- cần approval mạnh;
- có thể chặn cứng nếu policy không cho.

---

## 11. Fallback Ladder Chuẩn

OmniMind nên vận hành theo thang sau:

1. `reply_direct`
2. `tool_calling`
3. `run_skill_function`
4. `escalate_to_codex`
5. `ask_clarification`

Quan trọng:
- `Codex` không phải chỉ đứng sau `tool fail`;
- nó là executor chuẩn cho `exploratory_local` và `coding_ops`.

Nguyên tắc:
- `tool không đủ` != `thất bại`
- `tool không đủ` thường phải map thành `đây là việc của Codex`

---

## 12. Ví Dụ Mapping Nhanh

- `kiểm tra email cho tôi`
  - nếu đã có email integration: `tool`
  - nếu chưa có: `Codex` chỉ khi Codex thật sự truy cập được workflow đó

- `tìm 1 file nào đó rồi tổng hợp`
  - `Codex`

- `phân tích file PDF này`
  - `tool + AI trung tâm`

- `truy cập cho tôi một web`
  - web đơn giản/API rõ: `tool`
  - nhiều bước/login/phức tạp: `Codex`

- `code cho tôi`
  - `Codex`

- `tạo file mới`
  - file đơn giản, path rõ: `tool`
  - nhiều file/cấu trúc project: `Codex`

- `bạn đang làm việc trong workspace nào`
  - nếu có discovery tool: `tool`
  - nếu chưa có discovery tool: `Codex`

---

## 13. Hướng Nâng Cấp Ưu Tiên

Ba ưu tiên nên làm sớm nhất:

1. Chuẩn hóa decision contract với:
   - `task_shape`
   - `confidence`
   - `missing_context`
   - `why_not_tool`

2. Thêm `context discovery tools`

3. Định nghĩa `Codex` là executor chính thức cho:
   - `exploratory_local`
   - `coding_ops`
   - workflow local nhiều bước

---

## 14. Kết Luận

Muốn OmniMind xử lý tốt như một trợ lý AI cá nhân thật sự, hệ thống không thể chỉ nghĩ theo mô hình:
- có tool thì dùng
- không có tool thì fail

Thay vào đó, OmniMind phải nghĩ theo mô hình:
- đây là loại hành vi gì;
- đây là việc của AI trung tâm, tool, skill hay Codex;
- thiếu context nào;
- có cần approval không;
- khi nào nên điều tra thay vì hỏi lại;
- khi nào phải giao việc cho Codex ngay từ đầu.

Đây là nền để nâng cấp OmniMind từ một chat app có tool calling thành một personal AI assistant có điều phối thực sự.
