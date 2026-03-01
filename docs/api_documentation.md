# Tài Liệu API - OmniMind Backend

Tài liệu này mô tả các API đang có thật trong server hiện tại.

> Cập nhật theo source code ngày `2026-03-01`.
>
> Nguồn đối chiếu:
> - `projects/license-server/src/index.js`
> - `projects/license-server/src/omnimind_routes.js`
>
> Domain production: `https://license.vinhyenit.com`
> 
> Base local: `http://localhost:8050`

---

## 1. Quy ước chung

- Response format: JSON.
- `Content-Type`: `application/json` cho request có body.
- API Admin bắt buộc header:

```http
X-API-KEY: <API_KEY>
```

---

## 2. Public API - OmniMind Client

## 2.1 Verify License (OmniMind)

**Endpoint**

```http
POST /api/v1/omnimind/licenses/verify
```

**Body**

```json
{
  "license_key": "AG-XXXX",
  "hwid": "abc123...",
  "os_name": "Darwin",
  "os_version": "14.5"
}
```

**Response 200**

```json
{
  "success": true,
  "message": "Kích hoạt thành công!",
  "token": "<jwt>",
  "plan": "Standard",
  "expires_at": "2026-06-15T23:59:59.000Z"
}
```

**Các mã lỗi chính**
- `400`: thiếu `license_key` hoặc `hwid`
- `401`: license không tồn tại
- `402`: license hết hạn
- `403`: license không active hoặc HWID sai máy

---

## 2.2 Check App Version

**Endpoint**

```http
GET /api/v1/omnimind/app/version
```

**Response 200 (ví dụ)**

```json
{
  "latest_version": "1.2.0",
  "version_name": "Phoenix Update",
  "is_critical": false,
  "download_url": "https://.../payload.zip",
  "release_date": "2026-02-28T10:00:00.000Z",
  "changelogs": [
    { "change_type": "feat", "content": "..." }
  ]
}
```

---

## 2.3 Get Codex Releases

**Endpoint**

```http
GET /api/v1/omnimind/codex/releases
```

**Response 200 (hiện tại)**

```json
{
  "version": "1.5.0",
  "prerequisites": {
    "python": ">=3.9",
    "node": ">=18.0"
  },
  "platforms": {
    "darwin": {
      "url": "https://github.com/.../codex-macos-arm64.zip",
      "method": "zip_extract"
    },
    "win32": {
      "url": "https://github.com/.../codex-windows-x64.zip",
      "method": "zip_extract"
    }
  }
}
```

---

## 2.4 List Marketplace Skills

**Endpoint**

```http
GET /api/v1/omnimind/skills
```

**Query params**
- `page` (default `1`)
- `per_page` (default `20`)
- `q` (search theo tên/mô tả)
- `license_key` (để tính ownership)
- `os_name` hoặc `platform` (`darwin|win32|linux`)

**Response 200 (rút gọn)**

```json
{
  "total": 5,
  "page": 1,
  "per_page": 20,
  "platform": "darwin",
  "has_active_license": false,
  "skills": [
    {
      "id": "office-meeting-notes",
      "name": "Office Meeting Notes",
      "description": "...",
      "skill_type": "PRODUCTIVITY",
      "price": 0,
      "author": "OmniMind Team",
      "version": "1.0.0",
      "is_vip": false,
      "icon": "📝",
      "badge": "FREE",
      "color": "#0EA5E9",
      "download_url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip",
      "is_owned": true,
      "requires_purchase": false
    }
  ]
}
```

---

## 2.5 Get Skill Manifest

**Endpoint**

```http
GET /api/v1/omnimind/skills/:id/manifest
```

**Response 200**

```json
{
  "skill_id": "office-meeting-notes",
  "name": "Office Meeting Notes",
  "version": "1.0.0",
  "icon": "📝",
  "downloads": {
    "darwin": { "url": "https://..." }
  }
}
```

---

## 2.6 Resolve Skill Download URL

**Endpoint**

```http
GET /api/v1/omnimind/skills/:id/download
```

**Query params**
- `os_name` hoặc `platform`
- `license_key` (bắt buộc nếu skill paid/VIP theo rule)

**Response 200**

```json
{
  "success": true,
  "skill_id": "office-meeting-notes",
  "name": "Office Meeting Notes",
  "version": "1.0.0",
  "platform": "darwin",
  "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip",
  "checksum": "",
  "file_name": "",
  "size": null
}
```

**Các mã lỗi chính**
- `400`: skill chưa có link cho platform
- `403`: chưa đủ quyền tải (license/purchase)
- `404`: skill không tồn tại

---

## 2.7 Purchase/Grant Skill cho License

**Endpoint**

```http
POST /api/v1/omnimind/skills/:id/purchase
```

**Body**

```json
{
  "license_key": "AG-XXXX"
}
```

**Response 200**

```json
{
  "success": true,
  "message": "Đã cấp quyền skill thành công."
}
```

---

## 2.8 List Purchased Skills theo License

**Endpoint**

```http
GET /api/v1/omnimind/licenses/:license_key/skills
```

**Response 200**

```json
{
  "success": true,
  "skills": [
    {
      "skill_id": "office-meeting-notes",
      "purchased_at": "2026-03-01T12:10:00.000Z",
      "name": "Office Meeting Notes",
      "version": "1.0.0"
    }
  ]
}
```

---

## 3. Admin API - OmniMind Marketplace/CMS

## 3.1 Versions

### GET /api/v1/admin/omnimind/versions
Lấy danh sách app versions.

### POST /api/v1/admin/omnimind/versions
Tạo/cập nhật version và changelog.

Body mẫu:

```json
{
  "version_id": "1.2.0",
  "version_name": "Phoenix Update",
  "is_critical": false,
  "download_url": "https://...",
  "changelogs": [
    { "type": "feat", "content": "..." }
  ]
}
```

---

## 3.2 Skills CRUD

### GET /api/v1/admin/omnimind/skills
Lấy toàn bộ skill marketplace.

### POST /api/v1/admin/omnimind/skills
Tạo mới hoặc upsert skill theo `id`.

Body mẫu:

```json
{
  "id": "office-meeting-notes",
  "name": "Office Meeting Notes",
  "description": "...",
  "skill_type": "PRODUCTIVITY",
  "price": 0,
  "author": "OmniMind Team",
  "version": "1.0.0",
  "is_vip": false,
  "manifest_json": {
    "icon": "📝",
    "short_description": "...",
    "downloads": {
      "darwin": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" },
      "win32": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" },
      "linux": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" }
    }
  }
}
```

### PATCH /api/v1/admin/omnimind/skills/:id
Cập nhật một phần field skill (`name`, `description`, `skill_type`, `price`, `author`, `version`, `manifest_json`, `is_vip`).

### DELETE /api/v1/admin/omnimind/skills/:id
Xóa skill và xóa record trong `purchased_skills` liên quan.

### POST /api/v1/admin/omnimind/skills/:id/grant
Cấp quyền skill cho một license.

Body:

```json
{
  "license_key": "AG-XXXX"
}
```

---

## 3.3 Devices

### GET /api/v1/admin/omnimind/devices
Lấy danh sách thiết bị đã bind license (`license_devices` join `licenses`).

---

## 4. Admin API - License Core (đang dùng trong CMS)

Các endpoint này nằm trong `src/index.js` và đang được CMS gọi trực tiếp:

- `GET /api/v1/admin/licenses`
- `POST /api/v1/admin/licenses`
- `POST /api/v1/admin/licenses/reset`
- `PATCH /api/v1/admin/licenses/:id`

Ngoài ra có public endpoint cũ:

- `GET /api/v1/auth/handshake`
- `POST /api/v1/license/validate`

---

## 5. Danh sách API đã tạo cho Skill Marketplace (tóm tắt)

### Public
- `GET /api/v1/omnimind/skills`
- `GET /api/v1/omnimind/skills/:id/manifest`
- `GET /api/v1/omnimind/skills/:id/download`
- `POST /api/v1/omnimind/skills/:id/purchase`
- `GET /api/v1/omnimind/licenses/:license_key/skills`

### Admin
- `GET /api/v1/admin/omnimind/skills`
- `POST /api/v1/admin/omnimind/skills`
- `PATCH /api/v1/admin/omnimind/skills/:id`
- `DELETE /api/v1/admin/omnimind/skills/:id`
- `POST /api/v1/admin/omnimind/skills/:id/grant`

