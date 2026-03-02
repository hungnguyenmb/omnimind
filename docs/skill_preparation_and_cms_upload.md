# Hướng Dẫn Chuẩn Bị Skill Và Upload Lên CMS

Tài liệu này mô tả quy trình chuẩn để tạo skill mới cho OmniMind Marketplace, đóng gói artifact đúng format, upload file, và khai báo skill trên CMS.

> Phiên bản tài liệu: `2026-03-01`
> 
> Áp dụng cho:
> - Client: `projects/omnimind/`
> - Backend: `projects/license-server/`
> - CMS: `projects/license-dashboard/`

---

## 1. Chuẩn Hóa Đầu Vào Skill

### 1.1 Quy tắc đặt tên
- `skill_id`: dùng `kebab-case`, ví dụ `office-meeting-notes`.
- Không dùng khoảng trắng, không dùng ký tự đặc biệt.
- `skill_id` là khóa chính trong DB và là tên thư mục cài đặt local.

### 1.2 Cấu trúc tối thiểu
Mỗi skill phải có tối thiểu:

```text
<skill-folder>/
└── SKILL.md
```

`SKILL.md` bắt buộc có YAML frontmatter:

```md
---
name: office-meeting-notes
description: Convert meeting transcripts or notes into summary, decisions, and action items.
---
```

`required_capabilities` là tùy chọn, dùng để khai báo quyền hệ thống cần có khi skill chạy tool nhạy cảm:

```md
---
name: office-desktop-helper
description: Assist with desktop workflows.
required_capabilities:
  - ui_automation
  - screen_capture
---
```

Capability hiện hỗ trợ trong app:
- `screen_capture` -> cần quyền `screenshot`.
- `camera_access` -> cần quyền `camera`.
- `ui_automation` -> cần quyền `accessibility`.
- `system_restart` -> action nhạy cảm, có thể yêu cầu quyền admin/elevation theo OS.

Runtime contract phía client:
- Khi thực thi action của skill, app gọi `SkillManager.execute_skill_action(...)`.
- Nếu thiếu quyền, response chuẩn có:
  - `success: false`
  - `code: PERMISSION_REQUIRED`
  - `preflight.missing_permissions` để UI mở màn hình cấp quyền và retry.
- Có thể retry tự động qua `SkillManager.retry_skill_action_with_permission_request(...)`.

Lưu ý:
- `name` nên trùng `skill_id` để đồng bộ.
- `description` phải mô tả rõ ngữ cảnh trigger.

### 1.3 Nội dung SKILL.md nên có
- Workflow từng bước, ngắn gọn, dạng mệnh lệnh.
- Output format rõ ràng (sections, checklist, template).
- Không viết lan man; tập trung vào tác vụ skill giải quyết.

---

## 2. Đóng Gói Skill Artifact Đúng Chuẩn

Client cài skill bằng cách tải `.zip/.tar` và kiểm tra có file `SKILL.md` ở thư mục root của skill.

Ví dụ đúng:

```text
office-meeting-notes.zip
└── office-meeting-notes/
    └── SKILL.md
```

Không dùng zip có đường dẫn tuyệt đối kiểu `Users/...`.

### 2.1 Script đóng gói mẫu trong dự án
Đã có script tại:
- `projects/omnimind/marketplace-skills/package_office_skills.sh`

Chạy:

```bash
cd projects/omnimind/marketplace-skills
./package_office_skills.sh
```

Artifact output:
- `projects/omnimind/marketplace-skills/dist/*.zip`

---

## 3. Upload Artifact (File .zip) Lên Server

Có thể host file ở static server, CDN hoặc object storage. Hiện tại production đang serve từ:

- `https://license.vinhyenit.com/skills/<file>.zip`

Ví dụ đường dẫn file thực tế trên VPS:

- `/opt/docker/antigravity/license-server/frontend/dist/skills`

Sau khi upload, kiểm tra bằng HTTP:

```bash
curl -I https://license.vinhyenit.com/skills/office_meeting_notes.zip
```

Kỳ vọng: `HTTP/1.1 200 OK`, `Content-Type: application/zip`.

---

## 4. Khai Báo Skill Trên CMS Dashboard

Vào CMS (`license-dashboard`) -> menu `Marketplace Skills` -> `Tạo Skill`.

### 4.1 Các trường bắt buộc
- `Skill ID`: ví dụ `office-meeting-notes`
- `Tên Skill`
- `Loại` (`skill_type`)
- `Version`
- `Tác giả`
- `Giá`
- `VIP`
- `Mô tả ngắn` (`description`)
- `Icon`, `Badge`, `Color`, `Category`
- `Short Description`, `Detail Description`
- `Downloads` theo từng OS (`darwin`, `win32`, `linux`) - ít nhất 1 link

### 4.2 Metadata chuẩn được CMS build thành `manifest_json`

```json
{
  "metadata_version": "1.0",
  "icon": "📝",
  "badge": "FREE",
  "color": "#0EA5E9",
  "category": "office",
  "tags": ["office", "meeting"],
  "short_description": "Biến ghi chú họp thành tóm tắt và action items.",
  "detail_description": "Chuẩn hóa biên bản họp theo summary, decisions, risks, action items.",
  "required_capabilities": ["screen_capture"],
  "downloads": {
    "darwin": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" },
    "win32": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" },
    "linux": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" }
  }
}
```

### 4.3 Mapping field từ CMS -> DB
- `id` -> `marketplace_skills.id`
- `name` -> `marketplace_skills.name`
- `description` -> `marketplace_skills.description`
- `skill_type` -> `marketplace_skills.skill_type`
- `price` -> `marketplace_skills.price`
- `author` -> `marketplace_skills.author`
- `version` -> `marketplace_skills.version`
- `is_vip` -> `marketplace_skills.is_vip`
- `manifest_json` -> `marketplace_skills.manifest_json`

---

## 5. Checklist Kiểm Tra Sau Khi Upload

### 5.1 Kiểm tra API public

```bash
curl "https://license.vinhyenit.com/api/v1/omnimind/skills?page=1&per_page=20&platform=darwin"
curl "https://license.vinhyenit.com/api/v1/omnimind/skills/<skill_id>/download?platform=darwin"
```

Kỳ vọng:
- Skill xuất hiện trong danh sách `/skills`.
- `/download` trả `success: true` và có `url`.

### 5.2 Kiểm tra cài đặt từ client
- Mở OmniMind -> tab `Kho Kỹ Năng`.
- Nhấn `Làm mới`.
- Nhấn `Tải về & Cài đặt`.
- Skill phải xuất hiện trong tab `Đã Cài Đặt`.

---

## 6. Quy Trình Update Skill (phiên bản mới)

1. Cập nhật nội dung trong `SKILL.md`.
2. Repackage zip.
3. Upload đè artifact hoặc dùng file tên mới.
4. Update record trên CMS:
- tăng `version`
- cập nhật `manifest_json.downloads.*.url` nếu URL đổi.
5. Kiểm tra lại API và client.

Khuyến nghị:
- Dùng tên file theo version nếu cần rollback dễ hơn.
- Không đổi `skill_id` nếu chỉ là cập nhật nội dung.

---

## 7. Lỗi Thường Gặp

- Zip sai cấu trúc (đường dẫn tuyệt đối) -> client báo thiếu `SKILL.md`.
- `skill_id` trong DB khác thư mục trong zip -> khó bảo trì và gây nhầm lẫn.
- Thiếu link download cho platform -> API `/download` trả lỗi `Skill chưa có link tải cho HĐH này`.
- Manifest JSON sai format -> CMS không lưu được hoặc API trả metadata thiếu.
