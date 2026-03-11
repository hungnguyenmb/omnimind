# OmniMind Skill Packaging + VPS Upload Runbook

Tài liệu này dành cho team/AI agent để đóng gói và publish skill đúng chuẩn lên hệ thống OmniMind.

Phạm vi:
- Skill source: `projects/omnimind-skills`
- Backend: `projects/license-server`
- CMS frontend: `projects/license-dashboard`
- VPS runtime: `116.118.44.16`

---

## 1) Mục tiêu đầu ra

Sau khi làm xong, cần đạt đủ 4 điều kiện:
1. Artifact skill (`.zip/.tar`) tồn tại trên server tại `skill-artifacts`.
2. Bản ghi skill tồn tại trong bảng `marketplace_skills` (qua CMS hoặc admin API).
3. API resolve download trả đúng link:
   - `GET /api/v1/omnimind/skills/:id/download`
4. App OmniMind cài được skill mà không lỗi định dạng file.

---

## 2) Chuẩn bị local

## 2.1 Thư mục quan trọng
- Workspace: `/Users/admin/hungnm/work/freelancer/project/antigravity-workspace`
- Skill repo: `projects/omnimind-skills`
- Backend repo: `projects/license-server`
- Dashboard repo: `projects/license-dashboard`

## 2.2 Điều kiện trước khi đóng gói
Mỗi skill phải có cấu trúc tối thiểu:

```text
<skill-id>/
└── SKILL.md
```

`skill-id` nên dùng `kebab-case`.

---

## 3) Đóng gói skill

## 3.1 Đóng gói toàn bộ skill

```bash
cd /Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind-skills
./package_skills.sh
```

Output nằm tại:
- `projects/omnimind-skills/dist/*.zip`

## 3.2 Kiểm tra nhanh artifact trước khi publish

```bash
unzip -t dist/<skill-id>.zip
unzip -l dist/<skill-id>.zip | head -n 30
```

Kỳ vọng:
- Không báo lỗi CRC.
- Có file `SKILL.md` trong zip.

---

## 4) Upload artifact vào backend

## 4.1 Copy artifact sang backend local

```bash
cd /Users/admin/hungnm/work/freelancer/project/antigravity-workspace
cp projects/omnimind-skills/dist/<skill-id>.zip projects/license-server/skill-artifacts/
```

## 4.2 Deploy backend-only để sync artifact lên VPS

Dùng script chuẩn:

```bash
~/.codex/skills/license-vps-deploy/scripts/deploy_license_stack.sh --no-frontend --no-migration
```

Script này sẽ:
- Sync file backend chính.
- Sync thư mục `projects/license-server/skill-artifacts` lên VPS.
- Build/restart container backend.

---

## 5) Tạo/cập nhật metadata skill (CMS hoặc API)

## 5.1 Cách 1 (khuyến nghị): dùng CMS
Vào CMS -> `Marketplace Skills` -> tạo hoặc sửa skill:
- `id`, `name`, `description`, `skill_type`, `version`
- `manifest_json.downloads` phải có URL tải theo OS

Ví dụ URL tốt (trỏ thẳng API artifacts):

```text
https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/<skill-id>.zip
```

## 5.2 Cách 2: gọi Admin API

1) Đăng nhập admin để lấy token.
2) Gọi API tạo skill:

```bash
curl -X POST "https://license.vinhyenit.com/api/v1/admin/omnimind/skills" \
  -H "Authorization: Bearer <ADMIN_JWT>" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "office-meeting-notes",
    "name": "Office Meeting Notes",
    "description": "Tom tat bien ban hop",
    "skill_type": "KNOWLEDGE",
    "price": 0,
    "author": "OmniMind",
    "version": "1.0.0",
    "is_vip": false,
    "manifest_json": {
      "metadata_version": "1.0",
      "short_description": "Tom tat bien ban",
      "detail_description": "Trich xuat decisions/action items",
      "downloads": {
        "darwin": {"url": "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office-meeting-notes.zip"},
        "win32": {"url": "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office-meeting-notes.zip"},
        "linux": {"url": "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/office-meeting-notes.zip"}
      }
    }
  }'
```

---

## 6) Cách kết nối VPS và thư mục cần vào

## 6.1 SSH vào VPS

```bash
ssh -i ~/.ssh/antigravity_key root@116.118.44.16
```

## 6.2 Các thư mục quan trọng trên VPS

```bash
cd /opt/docker/antigravity/license-server
ls
# backend  frontend
```

- Backend code + docker compose: `/opt/docker/antigravity/license-server/backend`
- CMS static dist: `/opt/docker/antigravity/license-server/frontend/dist`

## 6.3 Kiểm tra container

```bash
docker ps | egrep "antigravity-license-server|antigravity-postgres"
docker logs --tail 100 antigravity-license-server
```

---

## 7) Cách vào database để kiểm tra skill

Container DB mặc định đang dùng trong script deploy:
- `antigravity-postgres`
- DB: `db_license`
- User: `antigravity_admin`

## 7.1 Vào psql

```bash
docker exec -it antigravity-postgres psql -U antigravity_admin -d db_license
```

## 7.2 Query kiểm tra nhanh

```sql
-- Danh sách skill mới nhất
SELECT id, name, version, skill_type, is_vip, created_at
FROM marketplace_skills
ORDER BY created_at DESC
LIMIT 20;

-- Kiểm tra skill cụ thể
SELECT id, name, manifest_json
FROM marketplace_skills
WHERE id = 'office-meeting-notes';

-- Quyền đã cấp cho license
SELECT skill_id, license_key, purchased_at
FROM purchased_skills
ORDER BY purchased_at DESC
LIMIT 20;
```

Thoát:

```sql
\q
```

---

## 8) Verify publish sau khi upload

## 8.1 Verify artifact URL

```bash
curl -I "https://license.vinhyenit.com/api/v1/omnimind/skills/artifacts/<skill-id>.zip"
```

Kỳ vọng:
- HTTP 200
- `Content-Type: application/zip`

## 8.2 Verify danh sách skill public có phân trang

```bash
curl "https://license.vinhyenit.com/api/v1/omnimind/skills?page=1&per_page=50&os_name=darwin"
```

## 8.3 Verify resolve download

```bash
curl "https://license.vinhyenit.com/api/v1/omnimind/skills/<skill-id>/download?os_name=darwin&license_key=<LICENSE_KEY>"
```

Kỳ vọng:
- `success: true`
- Có `url` trỏ tới zip/tar hợp lệ

---

## 9) Quy trình chuẩn cho agent (checklist)

1. Validate source skill (`SKILL.md`, id, cấu trúc).
2. Chạy `package_skills.sh`.
3. Test zip (`unzip -t`).
4. Copy zip vào `projects/license-server/skill-artifacts/`.
5. Deploy backend-only bằng script `license-vps-deploy`.
6. Tạo/sửa metadata qua CMS hoặc admin API.
7. Verify 3 API: list, download-resolve, artifact.
8. Smoke test cài skill trên app OmniMind.
9. Ghi log release: skill id, version, artifact file, thời điểm deploy.

---

## 10) Lỗi thường gặp và cách xử lý nhanh

1. `HTTP 404 Cannot GET /api/v1/omnimind/skills/:id/download`
- Backend chưa deploy bản mới hoặc route lỗi.
- Khắc phục: redeploy backend + check `docker logs antigravity-license-server`.

2. `Gói skill không đúng định dạng zip/tar`
- URL trả HTML/JSON thay vì file.
- Khắc phục: kiểm tra `downloads.url`, kiểm tra `curl -I` artifact URL.

3. Skill đã upload artifact nhưng app không thấy
- Metadata chưa tạo trong `marketplace_skills` hoặc `downloads` sai OS key.
- Khắc phục: sửa skill ở CMS và verify API list.

4. App tải được nhưng cài fail vì thiếu `SKILL.md`
- Zip sai cấu trúc.
- Khắc phục: đóng gói lại, verify bằng `unzip -l`.

---

## 11) Lệnh deploy nhanh (copy/paste)

```bash
# 1) package skill
cd /Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind-skills
./package_skills.sh

# 2) copy artifact sang backend repo
cd /Users/admin/hungnm/work/freelancer/project/antigravity-workspace
cp projects/omnimind-skills/dist/<skill-id>.zip projects/license-server/skill-artifacts/

# 3) deploy backend only
~/.codex/skills/license-vps-deploy/scripts/deploy_license_stack.sh --no-frontend --no-migration

# 4) verify public skills API
curl "https://license.vinhyenit.com/api/v1/omnimind/skills?page=1&per_page=50&os_name=darwin"
```

