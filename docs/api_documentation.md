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
  "checksum_sha256": "5e2611e630394f9a31042ad044c4f708f497b36643cdd3be93cfd0f147ae59c6",
  "package_size_bytes": 396000000,
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
      "skill_type": "KNOWLEDGE",
      "price": 0,
      "effective_price": 0,
      "author": "OmniMind Team",
      "version": "1.0.0",
      "is_vip": false,
      "icon": "📝",
      "badge": "FREE",
      "color": "#0EA5E9",
      "category": "office",
      "tags": ["office", "meeting"],
      "required_capabilities": ["screen_capture"],
      "metadata_version": "1.0",
      "downloads": {
        "darwin": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" }
      },
      "download_url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip",
      "is_owned": true,
      "requires_purchase": false,
      "pricing": {
        "currency": "VND",
        "base_price": 0,
        "effective_price": 0,
        "discount_amount": 0,
        "discount_percent": null,
        "override_price": null,
        "pricing_source": "base_price",
        "override_id": null,
        "override_note": ""
      }
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
  "metadata_version": "1.0",
  "icon": "📝",
  "required_capabilities": [],
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
  "size": null,
  "pricing": {
    "currency": "VND",
    "base_price": 49000,
    "effective_price": 39000,
    "discount_amount": 10000,
    "discount_percent": null,
    "override_price": 39000,
    "pricing_source": "override_price",
    "override_id": 12,
    "override_note": "Khuyến mãi đầu tháng"
  }
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

**Response 402 (skill trả phí, cần thanh toán SePay)**

```json
{
  "success": false,
  "code": "PAYMENT_REQUIRED",
  "message": "Skill trả phí. Vui lòng thanh toán để tiếp tục.",
  "payment": {
    "id": "txn_1740900000000_ab12cd34",
    "type": "SKILL",
    "item_id": "office-email-assistant",
    "license_key": "AG-XXXX",
    "amount": 39000,
    "currency": "VND",
    "status": "PENDING",
    "provider": "SEPAY",
    "payment_content": "OMOFFICEAB12CD34",
    "qr_url": "https://img.vietqr.io/image/VCB-0123456789-qr_only.png?...",
    "expires_at": "2026-03-03T12:00:00.000Z"
  },
  "pricing": {
    "currency": "VND",
    "base_price": 49000,
    "effective_price": 39000
  }
}
```

Ghi chú:
- `amount` luôn được backend snapshot từ `price` + override đang active tại thời điểm tạo order.
- Client không được gửi giá lên server.

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

## 2.9 Payment Order Status

**Endpoint**

```http
GET /api/v1/omnimind/payments/orders/:id
```

**Query params**
- `license_key` (bắt buộc)

**Response 200**

```json
{
  "success": true,
  "order": {
    "id": "txn_1740900000000_ab12cd34",
    "status": "PENDING",
    "amount": 39000,
    "currency": "VND",
    "payment_content": "OMOFFICEAB12CD34",
    "qr_url": "https://img.vietqr.io/image/..."
  }
}
```

---

## 2.10 SePay Webhook

**Endpoint**

```http
POST /api/v1/omnimind/payments/webhooks/sepay
```

**Header bắt buộc**

```http
Authorization: Apikey <SEPAY_API_KEY>
```

**Mô tả**
- Nhận callback từ SePay.
- Match transaction theo `payment_content` (`code` ưu tiên, fallback `content`) + `transferAmount`.
- Idempotent theo `sepay_id`.
- Match thành công sẽ chuyển `transactions.status = SUCCESS` và cấp quyền skill.

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
  "checksum_sha256": "5e2611e630394f9a31042ad044c4f708f497b36643cdd3be93cfd0f147ae59c6",
  "package_size_bytes": 396000000,
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
  "skill_type": "KNOWLEDGE",
  "price": 0,
  "author": "OmniMind Team",
  "version": "1.0.0",
  "is_vip": false,
  "manifest_json": {
    "metadata_version": "1.0",
    "icon": "📝",
    "badge": "FREE",
    "color": "#0EA5E9",
    "category": "office",
    "tags": ["office", "meeting"],
    "short_description": "...",
    "detail_description": "...",
    "required_capabilities": ["screen_capture"],
    "downloads": {
      "darwin": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" },
      "win32": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" },
      "linux": { "url": "https://license.vinhyenit.com/skills/office_meeting_notes.zip" }
    }
  }
}
```

Validation quan trọng:
- `skill_type` chỉ nhận `KNOWLEDGE` hoặc `TOOL`.
- `manifest_json` phải là object JSON hợp lệ.
- `manifest_json.downloads` phải có ít nhất một URL hợp lệ trong `darwin|win32|linux`.

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

### GET /api/v1/admin/omnimind/payments/config
Lấy cấu hình thanh toán SePay (masked API key).

### PUT /api/v1/admin/omnimind/payments/config
Cập nhật cấu hình thanh toán:
- `bank_code`
- `bank_account`
- `bank_account_name`
- `qr_base_url`
- `sepay_api_key`

### GET /api/v1/admin/omnimind/pricing/overrides
Lấy danh sách giá override/discount cho skill.

### POST /api/v1/admin/omnimind/pricing/overrides
Tạo rule giá:
- `skill_id` (bắt buộc)
- `override_price` hoặc `discount_percent`
- `starts_at`, `ends_at`, `is_active`, `note`

### DELETE /api/v1/admin/omnimind/pricing/overrides/:id
Xoá override giá theo ID.

### GET /api/v1/admin/omnimind/payments/transactions
Xem lịch sử giao dịch SePay đã tạo.

### GET /api/v1/admin/omnimind/payments/users/history
Xem lịch sử thanh toán theo từng license/user:
- Tổng số giao dịch
- Số lượng success/pending/failed
- Tổng doanh thu success
- Giao dịch đầu tiên/gần nhất

Query:
- `limit` (max 500, default 100)
- `search` (lọc theo `license_key`, `item_id`, `payment_content`)

### GET /api/v1/admin/omnimind/monitoring/summary
API monitoring tập trung cho vận hành:
- `transactions_24h`
- `transactions_7d`
- `overdue_pending_count`
- `webhook_24h`
- `audits_24h`

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
- `GET /api/v1/omnimind/payments/orders/:id`
- `POST /api/v1/omnimind/payments/webhooks/sepay`

### Admin
- `GET /api/v1/admin/omnimind/skills`
- `POST /api/v1/admin/omnimind/skills`
- `PATCH /api/v1/admin/omnimind/skills/:id`
- `DELETE /api/v1/admin/omnimind/skills/:id`
- `POST /api/v1/admin/omnimind/skills/:id/grant`
- `GET /api/v1/admin/omnimind/payments/config`
- `PUT /api/v1/admin/omnimind/payments/config`
- `GET /api/v1/admin/omnimind/pricing/overrides`
- `POST /api/v1/admin/omnimind/pricing/overrides`
- `DELETE /api/v1/admin/omnimind/pricing/overrides/:id`
- `GET /api/v1/admin/omnimind/payments/transactions`
