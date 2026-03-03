# OmniMind Skill Creation & Publish Playbook

Tài liệu chuẩn để team hoặc AI agent tạo skill mới, đóng gói đúng định dạng, cấu hình CMS đúng schema và kiểm tra deploy end-to-end.

Phiên bản: 2026-03-03  
Phạm vi:
- Client app: `projects/omnimind`
- Backend API: `projects/license-server`
- CMS Dashboard: `projects/license-dashboard`

---

## 1. Mục tiêu và nguyên tắc

Skill hợp lệ trong hệ thống OmniMind phải thỏa 4 điều kiện:
1. Gói tải về là file nén thật (`.zip/.tar/.tgz/.tar.gz`), không phải HTML/JSON.
2. Trong package có `SKILL.md` hợp lệ.
3. Bản ghi skill trên CMS có `manifest_json.downloads` chứa ít nhất 1 URL theo OS.
4. URL tải resolve từ API `/api/v1/omnimind/skills/:id/download` trả được artifact đúng định dạng.

Nếu 1 trong 4 điều kiện sai, client sẽ lỗi khi cài skill.

---

## 2. Chuẩn cấu trúc skill local

## 2.1 Tên skill
- `skill_id`: dùng `kebab-case`, ví dụ `office-meeting-notes`.
- Regex backend chấp nhận: `^[a-z0-9][a-z0-9-_]{1,99}$`
- Không đổi `skill_id` khi chỉ cập nhật nội dung/version.

## 2.2 Cấu trúc thư mục tối thiểu

```text
<skill-id>/
└── SKILL.md
```

Ví dụ thực tế:

```text
projects/omnimind/marketplace-skills/office-meeting-notes/
└── SKILL.md
```

## 2.3 Chuẩn nội dung `SKILL.md`

Frontmatter bắt buộc:

```md
---
name: office-meeting-notes
description: Convert meeting transcripts into summary, decisions and action items.
---
```

Frontmatter tùy chọn (khuyến nghị):

```md
---
name: desktop-helper
description: Help automate desktop tasks.
required_capabilities:
  - ui_automation
  - screen_capture
---
```

`required_capabilities` hợp lệ hiện tại:
- `screen_capture`
- `camera_access`
- `ui_automation`
- `system_restart`

Lưu ý:
- App parse capability từ `SKILL.md`; nếu khai báo capability lạ sẽ không có preflight đúng.
- Nội dung skill nên có workflow rõ ràng và output template cụ thể.

---

## 3. Đóng gói artifact đúng định dạng

## 3.1 Định dạng package được client chấp nhận

Client cài skill tại `engine/skill_manager.py`:
- Chỉ giải nén khi là `zipfile.is_zipfile(...)` hoặc `tarfile.is_tarfile(...)`
- Sau khi giải nén phải tìm được `SKILL.md`

Khuyến nghị package:

```text
office_meeting_notes.zip
└── office-meeting-notes/
    └── SKILL.md
```

## 3.2 Script đóng gói mẫu đang dùng

File:
- `projects/omnimind/marketplace-skills/package_office_skills.sh`

Chạy:

```bash
cd projects/omnimind/marketplace-skills
./package_office_skills.sh
```

Output:
- `projects/omnimind/marketplace-skills/dist/*.zip`

## 3.3 Kiểm tra package trước khi upload

```bash
unzip -t projects/omnimind/marketplace-skills/dist/office_meeting_notes.zip
```

Kỳ vọng: `No errors detected`.

---

## 4. Chuẩn metadata skill trên CMS/backend

## 4.1 Trường bắt buộc khi tạo skill

Tối thiểu cần:
- `id`
- `name`
- `description`
- `skill_type` (`KNOWLEDGE` hoặc `TOOL`)
- `version`
- `manifest_json.downloads` có ít nhất 1 URL

Lưu ý quan trọng:
- Backend normalize `skill_type`; giá trị ngoài `KNOWLEDGE|TOOL` sẽ bị fallback.
- Không để thiếu downloads, nếu không backend trả lỗi validation.

## 4.2 Schema `manifest_json` chuẩn

```json
{
  "metadata_version": "1.0",
  "icon": "📝",
  "badge": "FREE",
  "color": "#0EA5E9",
  "category": "office",
  "tags": ["office", "meeting"],
  "short_description": "Biến ghi chú họp thành tóm tắt và action item.",
  "detail_description": "Chuẩn hóa biên bản theo summary/decisions/risks/action items.",
  "required_capabilities": ["screen_capture"],
  "min_app_version": "1.0.0",
  "dependencies": [],
  "entrypoint": "",
  "downloads": {
    "darwin": {
      "url": "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office_meeting_notes.zip",
      "checksum": "",
      "file_name": "office_meeting_notes.zip",
      "size": 810
    },
    "win32": {
      "url": "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office_meeting_notes.zip"
    },
    "linux": {
      "url": "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office_meeting_notes.zip"
    }
  }
}
```

Khuyến nghị dùng trực tiếp URL `/api/v1/omnimind/skills/artifacts/:file` để tránh lỗi static route.

---

## 5. Publish artifact lên server

Backend hiện serve artifact từ:
- Route: `GET /api/v1/omnimind/skills/artifacts/:file`
- Thư mục server: `projects/license-server/skill-artifacts/`

## 5.1 Quy trình chuẩn
1. Copy file zip vào `projects/license-server/skill-artifacts/`.
2. Deploy backend (script deploy hiện đã sync thư mục này).
3. Verify URL artifact trả `application/zip`.

Verify:

```bash
curl -I "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office_meeting_notes.zip"
```

Kỳ vọng:
- HTTP `200`
- `Content-Type: application/zip`

---

## 6. Quy trình tạo skill trên CMS (UI)

1. Mở CMS, vào mục quản trị Skill Marketplace.
2. Nhập `Skill ID`, `Name`, `Description`, `Type`, `Author`, `Version`, `Price`, `VIP`.
3. Khai báo metadata (icon, badge, color, short/detail description, tags, required capabilities).
4. Khai báo `downloads` theo OS.
5. Lưu skill.

Khuyến nghị:
- `download.file_name` nên đúng tên artifact thật.
- Nếu skill paid, cấu hình giá rõ ràng (`price` hoặc bảng override).

---

## 7. API checklist sau publish

## 7.1 Kiểm tra danh sách skill

```bash
curl "https://license.vinhyenit.com/api/v1/omnimind/skills?page=1&per_page=20&os_name=darwin"
```

## 7.2 Kiểm tra resolve download

```bash
curl "https://license.vinhyenit.com/api/v1/omnimind/skills/office-meeting-notes/download?os_name=darwin&license_key=<LICENSE_KEY>"
```

Kỳ vọng:
- `success: true`
- Có `url` trỏ tới artifact zip/tar

## 7.3 Kiểm tra byte đầu của artifact

```bash
curl -sL "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office_meeting_notes.zip" | head -c 4 | xxd -p
```

Kỳ vọng với zip: `504b0304` (`PK..`)

---

## 8. Smoke test trên app OmniMind

1. Mở app -> `Skill Marketplace`.
2. Nhấn `Làm mới`.
3. Cài skill cần test.
4. Kiểm tra kết quả:
- Skill xuất hiện trong tab `Đã cài đặt`.
- Không còn lỗi `Artifact trả về HTML`.
- Nếu có capability nhạy cảm, app hiển thị preflight permission đúng.

---

## 9. Lỗi phổ biến và cách xử lý

## 9.1 Lỗi `Gói skill không đúng định dạng zip/tar`
Nguyên nhân:
- URL trả HTML/JSON hoặc file hỏng.

Khắc phục:
1. Kiểm tra `/skills/:id/download` trả đúng URL artifact.
2. Kiểm tra artifact URL trả `application/zip`.
3. Kiểm tra file zip bằng `unzip -t`.

## 9.2 Lỗi `Skill package thiếu file SKILL.md`
Nguyên nhân:
- Gói nén sai cấu trúc.

Khắc phục:
- Đảm bảo trong package có `SKILL.md` ở root skill folder.

## 9.3 Skill không hiện quyền preflight đúng
Nguyên nhân:
- Khai báo `required_capabilities` sai tên.

Khắc phục:
- Chỉ dùng 4 capability được hỗ trợ hiện tại.

---

## 10. Mẫu “chuẩn production” end-to-end

## 10.1 Tạo skill

```text
projects/omnimind/marketplace-skills/my-new-skill/
└── SKILL.md
```

## 10.2 Đóng gói

```bash
cd projects/omnimind/marketplace-skills
zip -qr dist/my_new_skill.zip my-new-skill
unzip -t dist/my_new_skill.zip
```

## 10.3 Publish artifact

```bash
cp dist/my_new_skill.zip ../license-server/skill-artifacts/
```

## 10.4 Tạo metadata trên CMS
- `id = my-new-skill`
- `skill_type = KNOWLEDGE` hoặc `TOOL`
- downloads URL:
`https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/my_new_skill.zip`

## 10.5 Verify API + app
- Gọi `/api/v1/omnimind/skills`
- Gọi `/api/v1/omnimind/skills/:id/download`
- Cài trên app và kiểm tra tab Installed

---

## 11. Checklist ngắn cho AI Agent (copy-paste workflow)

1. Tạo thư mục `<skill-id>/SKILL.md` với frontmatter chuẩn.
2. Đóng gói zip, kiểm tra `unzip -t`.
3. Đưa zip vào `projects/license-server/skill-artifacts/`.
4. Trên CMS tạo/cập nhật skill + manifest + downloads.
5. Deploy backend.
6. Verify 3 endpoint: list, resolve download, artifact file.
7. Smoke test cài skill trên app.
8. Chỉ bàn giao khi cài thành công và không lỗi định dạng.

