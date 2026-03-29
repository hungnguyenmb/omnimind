# Tiêu Chuẩn Skill Và Tool Function Cho OmniMind

Ngày cập nhật: `2026-03-13`

Tài liệu này là chuẩn để team hoặc AI agent phát triển skill/tool cho OmniMind trong giai đoạn có:
- Central AI Coordinator
- function calling / tool calling
- plugin execution từ built-in functions và installed skills

Tài liệu này bổ sung cho:
- `docs/skill_creation_and_publish_playbook.md`
- `docs/skill_preparation_and_cms_upload.md`
- `docs/skill_packaging_vps_database_runbook.md`

Mục tiêu:
- thống nhất cách khai báo function;
- thống nhất runtime contract giữa AI, registry và executor;
- giúp agent sau này tạo skill/tool đúng format ngay từ đầu.

---

## 1. Nguyên tắc nền tảng

### 1.1 Phân biệt 3 khái niệm

#### Skill

Là package được cài đặt và quản lý bởi marketplace OmniMind.

Skill có thể chứa:
- hướng dẫn text;
- script/code;
- assets;
- function manifest.

#### Tool function

Là một khả năng để AI có thể gọi bằng function calling.

Tool function chỉ là metadata:
- tên function;
- mô tả;
- input schema;
- capability;
- execution mode.

Tool function không phải là code.

#### Executor

Là thành phần local thực thi code thật.

Executor có thể là:
- built-in executor trong app;
- skill script executor;
- Codex executor.

### 1.2 Nguyên tắc quan trọng

- Không viết function schema mà không có code local để thực thi.
- Không để AI tự sinh tên function ngoài danh sách registry.
- Không cho skill chạy trực tiếp nếu không qua capability và approval checks.
- Mỗi function phải có `JSON schema` input rõ ràng.
- Mỗi tool result phải được trả về theo schema chuẩn.

---

## 2. Cấu trúc package skill chuẩn

### 2.1 Cấu trúc tối thiểu

```text
<skill-id>/
  SKILL.md
```

### 2.2 Cấu trúc khuyến nghị cho skill có function

```text
<skill-id>/
  SKILL.md
  tool_manifest.json
  scripts/
    main.py
  assets/
    icon.png
  examples/
    sample_input.json
```

### 2.3 Quy tắc đặt tên

- `skill_id`: `kebab-case`
- `function_name`: `snake_case`
- `entrypoint`: đường dẫn tương đối trong package skill

Ví dụ:
- skill id: `office-excel-report`
- function name: `generate_excel_report`
- entrypoint: `scripts/main.py`

---

## 3. Chuẩn `SKILL.md`

### 3.1 Frontmatter bắt buộc

```md
---
name: office-excel-report
description: Tạo báo cáo Excel từ dữ liệu đầu vào.
version: 1.0.0
skill_type: TOOL
---
```

### 3.2 Frontmatter khuyến nghị

```md
---
name: office-excel-report
description: Tạo báo cáo Excel từ dữ liệu đầu vào.
version: 1.0.0
skill_type: TOOL
entrypoint: scripts/main.py
required_capabilities:
  - fs_read
  - fs_write
supported_channels:
  - telegram
  - zalo
---
```

### 3.3 Trường cho phép

- `name`
- `description`
- `version`
- `skill_type`
- `entrypoint`
- `required_capabilities`
- `supported_channels`

Lưu ý:
- `SKILL.md` vẫn giữ vai trò hướng dẫn nghiệp vụ cho AI.
- Function calling metadata chi tiết phải nằm trong `tool_manifest.json`.

---

## 4. Chuẩn `tool_manifest.json`

### 4.1 Mục đích

File này mô tả các function mà skill expose cho AI.

Nếu skill không cần function calling thì có thể bỏ qua file này.

### 4.2 Schema tổng quát

```json
{
  "manifest_version": "1.0",
  "skill_id": "office-excel-report",
  "functions": [
    {
      "name": "generate_excel_report",
      "description": "Tạo một file báo cáo Excel từ dữ liệu đầu vào",
      "input_schema": {
        "type": "object",
        "properties": {
          "source_path": { "type": "string" },
          "output_name": { "type": "string" }
        },
        "required": ["source_path"],
        "additionalProperties": false
      },
      "execution": {
        "type": "python_script",
        "entrypoint": "scripts/main.py"
      },
      "required_capabilities": ["fs_read", "fs_write"],
      "approval_policy": "on-request",
      "supported_channels": ["telegram", "zalo"],
      "timeout_seconds": 90,
      "returns_artifacts": true
    }
  ]
}
```

### 4.3 Trường bắt buộc trong mỗi function

- `name`
- `description`
- `input_schema`
- `execution.type`
- `execution.entrypoint`

### 4.4 Trường khuyến nghị

- `required_capabilities`
- `approval_policy`
- `supported_channels`
- `timeout_seconds`
- `returns_artifacts`

---

## 5. Execution modes được phép

### 5.1 `python_script`

Dùng cho skill script Python.

Ví dụ:

```json
{
  "execution": {
    "type": "python_script",
    "entrypoint": "scripts/main.py"
  }
}
```

Runtime kỳ vọng:
- OmniMind sẽ chạy script bằng Python runtime do app quản lý;
- arguments được truyền qua JSON file, stdin hoặc argv theo contract của executor.

### 5.2 `builtin_action`

Dùng cho built-in function do app sở hữu.

Ví dụ:

```json
{
  "execution": {
    "type": "builtin_action",
    "action_id": "read_local_file"
  }
}
```

Lưu ý:
- loại này thường không nằm trong skill package bên ngoài;
- chủ yếu dùng cho registry nội bộ của app.

### 5.3 `codex_escalation`

Dùng cho task mà app muốn đánh dấu là phải đẩy sang Codex runtime.

Lưu ý:
- không khuyến nghị để skill thường expose trực tiếp loại này;
- ưu tiên để Central AI tự quyết định escalate.

---

## 6. Capability model chuẩn

Mỗi function phải khai báo capability tối thiểu để app có thể preflight và xin quyền đúng mức.

### 6.1 Capability đề xuất

- `fs_read`
- `fs_write`
- `fs_delete`
- `exec`
- `network`
- `browser`
- `ui_automation`
- `screen_capture`
- `camera_access`
- `system_restart`

### 6.2 Nguyên tắc

- Không khai báo capability dự phòng không cần thiết.
- Function nào có khả năng gây tác động hệ thống thì phải khai báo rõ.
- App được phép chặn execute nếu capability manifest quá rộng hoặc nguy hiểm.

---

## 7. Approval policy chuẩn

Giá trị hợp lệ:
- `never`
- `on-request`
- `always`

Ý nghĩa:
- `never`
  - chỉ cho function an toàn, read-only hoặc đã được sandbox chặt chẽ.
- `on-request`
  - mặc định cho function có tác động local.
- `always`
  - luôn cần user xác nhận trước khi chạy.

Khuyến nghị:
- mặc định dùng `on-request`.
- không dùng `never` cho function có `fs_write`, `exec`, `network`, `ui_automation`.

---

## 8. Input schema chuẩn

### 8.1 Quy tắc

- Dùng JSON schema object.
- Có `required`.
- Có `additionalProperties: false` nếu có thể.
- Tên field rõ ràng, không viết tắt mơ hồ.

### 8.2 Ví dụ tốt

```json
{
  "type": "object",
  "properties": {
    "source_path": {
      "type": "string",
      "description": "Đường dẫn file nguồn local"
    },
    "sheet_name": {
      "type": "string",
      "description": "Tên worksheet đích"
    }
  },
  "required": ["source_path"],
  "additionalProperties": false
}
```

### 8.3 Ví dụ xấu

```json
{
  "type": "object",
  "properties": {
    "data": { "type": "string" }
  }
}
```

Lý do xấu:
- tên field mơ hồ;
- không rõ path hay content;
- không có required;
- dễ để AI truyền sai payload.

---

## 9. Runtime contract cho skill executor

### 9.1 Đầu vào mà executor phải nhận

Skill executor cần nhận được:
- `skill_id`
- `function_name`
- `arguments`
- `request_context`

`request_context` khuyến nghị gồm:
- `channel`: `telegram|zalo|ui`
- `thread_id`
- `user_message`
- `workspace_path`
- `request_id`

### 9.2 Đầu ra mà executor phải trả

Mỗi skill function phải trả về một JSON object theo chuẩn:

```json
{
  "success": true,
  "message": "Đã tạo xong báo cáo",
  "data": {
    "rows_processed": 120
  },
  "artifacts": [
    {
      "type": "file",
      "path": "/tmp/report.xlsx",
      "label": "Báo cáo Excel"
    }
  ],
  "error_code": "",
  "error_detail": ""
}
```

### 9.3 Quy tắc cho output

- `message` phải ngắn, mang tính kỹ thuật.
- `data` phải có cấu trúc, không nhồi text dài.
- `artifacts` chỉ chứa thông tin tài nguyên sinh ra.
- nếu lỗi:
  - `success = false`
  - `error_code` bắt buộc có giá trị
  - `error_detail` phải hữu ích cho debug

---

## 10. Quan hệ giữa tool result và final user reply

Skill/tool không nên tự tạo final message theo văn phong chat để gửi thẳng cho user.

Dùng flow đúng:
1. skill/tool trả về kết quả kỹ thuật;
2. Central AI đọc kết quả;
3. Central AI viết lại final reply theo ngữ cảnh;
4. transport gửi ra Telegram/Zalo.

Được phép có trường phụ:

```json
{
  "suggested_user_reply": "Đã tạo xong báo cáo"
}
```

Nhưng:
- chỉ là gợi ý;
- không được coi là final reply bắt buộc.

---

## 11. Đăng ký function vào registry

### 11.1 Lúc nào đăng ký

Function được đăng ký khi:
- app khởi động và scan installed skills;
- skill mới được cài đặt;
- skill được update;
- registry được refresh thủ công.

### 11.2 Điều kiện để đăng ký thành công

- skill package hợp lệ;
- `tool_manifest.json` parse được;
- function schema hợp lệ;
- entrypoint tồn tại trong skill dir;
- capability/approval policy hợp lệ.

Nếu `1` function lỗi:
- disable function đó;
- không disable toàn bộ skill nếu các function khác vẫn hợp lệ.

---

## 12. Rule cho agent khi phát triển skill/tool

Agent phải tuân thủ:
- không tạo function tên trùng với built-in function nếu không được chỉ định;
- không tạo entrypoint ngoài thư mục skill;
- không dùng đường dẫn tuyệt đối trong manifest;
- không khai báo capability vượt nhu cầu thật;
- không trả output là plain text nếu function sinh artifact hoặc data có cấu trúc;
- không hardcode đường dẫn local của máy dev.

Agent nên làm:
- thêm `examples/` nếu payload phức tạp;
- viết `SKILL.md` ngắn gọn, rõ workflow;
- trả output JSON ổn định;
- khai báo timeout hợp lý;
- test local package trước khi publish.

---

## 13. Checklist review một skill có function

1. `SKILL.md` có frontmatter hợp lệ.
2. `tool_manifest.json` tồn tại và parse được.
3. Mỗi function có `name`, `description`, `input_schema`, `execution`.
4. `entrypoint` tồn tại thật.
5. `required_capabilities` đã được tối thiểu hóa.
6. `approval_policy` hợp lý.
7. Executor output đúng schema chuẩn.
8. Package zip/tar có cấu trúc đúng.
9. Skill cài local được và registry nạp function được.
10. Tool result có thể quay lại cho AI để sinh final reply.

---

## 14. Ví dụ hoàn chỉnh

### 14.1 `SKILL.md`

```md
---
name: office-excel-report
description: Tạo báo cáo Excel từ CSV hoặc JSON.
version: 1.0.0
skill_type: TOOL
entrypoint: scripts/main.py
required_capabilities:
  - fs_read
  - fs_write
supported_channels:
  - telegram
  - zalo
---

Skill này tạo báo cáo Excel từ file dữ liệu đầu vào.
Nếu user không cung cấp output_name thì tự sinh tên mặc định.
```

### 14.2 `tool_manifest.json`

```json
{
  "manifest_version": "1.0",
  "skill_id": "office-excel-report",
  "functions": [
    {
      "name": "generate_excel_report",
      "description": "Tạo một file Excel từ file CSV hoặc JSON đầu vào",
      "input_schema": {
        "type": "object",
        "properties": {
          "source_path": {
            "type": "string",
            "description": "Đường dẫn local tới file đầu vào"
          },
          "output_name": {
            "type": "string",
            "description": "Tên file xuất ra, không bắt buộc"
          }
        },
        "required": ["source_path"],
        "additionalProperties": false
      },
      "execution": {
        "type": "python_script",
        "entrypoint": "scripts/main.py"
      },
      "required_capabilities": ["fs_read", "fs_write"],
      "approval_policy": "on-request",
      "supported_channels": ["telegram", "zalo"],
      "timeout_seconds": 90,
      "returns_artifacts": true
    }
  ]
}
```

### 14.3 Output executor

```json
{
  "success": true,
  "message": "Đã tạo xong báo cáo Excel",
  "data": {
    "rows_processed": 120,
    "sheet_count": 1
  },
  "artifacts": [
    {
      "type": "file",
      "path": "/tmp/output/report.xlsx",
      "label": "Excel report"
    }
  ],
  "error_code": "",
  "error_detail": ""
}
```

---

## 15. Định nghĩa done cho một skill/tool mới

Một skill/tool được xem là đạt chuẩn khi:
- cài đặt được qua OmniMind marketplace;
- function schema được registry nhận diện;
- AI có thể gọi function đó;
- code local thực thi được an toàn;
- kết quả được trả ngược lại cho AI;
- AI sinh final reply gửi ra Telegram/Zalo đúng ngữ cảnh.
