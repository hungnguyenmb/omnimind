# Sprint 6 - Release Checklist & Rollback Playbook

Ngày cập nhật: `2026-03-05`

Tài liệu này chốt 3 hạng mục đã triển khai theo yêu cầu Sprint 6:
- Item 1: kiểm thử decompile/reverse surface.
- Item 5: chaos test runtime Telegram/Codex.
- Item 6: checklist phát hành + quy trình rollback.

## 1) Công cụ kiểm thử đã có

### 1.1 Decompile surface check (Item 1)
- Script: `scripts/security/test_decompile_surface.py`
- Mục tiêu:
  - Phát hiện file `.py` bị lộ trong artifact phát hành.
  - Quét nhanh mẫu token/secret lộ trực tiếp trong artifact.

Ví dụ chạy:
```bash
cd projects/omnimind
python3 scripts/security/test_decompile_surface.py \
  --artifact release-artifacts/OmniMind-windows-v1.2.0.zip
```

### 1.2 Runtime chaos checks (Item 5)
- Script: `scripts/security/run_runtime_chaos_checks.py`
- Mục tiêu:
  - Verify bot chịu lỗi `409 conflict`, payload JSON lỗi.
  - Verify retry Telegram transport.
  - Verify parser directive không crash khi payload hỏng.
  - Verify process lock chống chạy trùng poller.
  - Verify map lỗi runtime về thông điệp thân thiện.

Ví dụ chạy:
```bash
cd projects/omnimind
python3 scripts/security/run_runtime_chaos_checks.py
```

### 1.3 Vị trí report
Cả 2 script đều ghi report vào:
- `projects/omnimind/release-artifacts/security-reports/`

---

## 2) Security release checklist (Item 6)

Trước khi publish bản mới:

1. Build artifact release hardened (zip/installer).
2. Chạy decompile surface check:
   - `test_decompile_surface.py` phải `Status: PASSED`.
3. Chạy runtime chaos checks:
   - `run_runtime_chaos_checks.py` phải không có scenario fail.
4. Chạy verify dữ liệu nhạy cảm local:
   - `python3 scripts/verify_sensitive_storage.py`
5. Smoke test chức năng chính:
   - Kích hoạt license.
   - Tải/cài OmniMind CLI.
   - Bật bot Telegram, gửi 2-3 tin liên tiếp.
   - Cài 1 skill free, 1 skill paid (nếu có môi trường test).
6. Lưu hash artifact + report bảo mật vào release note nội bộ.

Gate phát hành:
- Nếu Item 1 fail -> chặn phát hành.
- Nếu Item 5 fail >= 1 scenario -> chặn phát hành.

---

## 3) Rollback playbook

### 3.1 Trigger rollback
Rollback ngay khi có một trong các dấu hiệu:
- Bot mất ổn định diện rộng (treo poller, conflict liên tục).
- Luồng thanh toán/entitlement sai trạng thái.
- Artifact mới bị phát hiện lộ mã nguồn hoặc token.

### 3.2 Quy trình rollback chuẩn
1. Trên CMS: tắt release mới (`Active = false`) để chặn tải bản lỗi.
2. Trên backend: rollback về commit/tag ổn định gần nhất.
3. Trên CMS frontend: deploy lại `dist` bản ổn định tương ứng backend.
4. Restart dịch vụ và kiểm tra health endpoint/API chính.
5. Chạy smoke test tối thiểu:
   - activate license,
   - Telegram bot receive/reply,
   - tải một skill.
6. Ghi lại incident log:
   - thời gian bắt đầu/kết thúc,
   - root cause sơ bộ,
   - phạm vi ảnh hưởng,
   - hành động khắc phục tiếp theo.

### 3.3 Sau rollback
1. Giữ release lỗi ở trạng thái inactive.
2. Tạo hotfix branch.
3. Chạy lại Item 1 + Item 5 trước khi mở lại rollout.

---

## 4) Residual risk còn lại (ngắn gọn)

1. Decompile check hiện là heuristic (chưa thay thế pentest chuyên sâu).
2. Chaos test hiện tập trung vào luồng runtime cốt lõi, chưa bao phủ toàn bộ API third-party.
3. Cần duy trì cadence chạy checklist mỗi lần release để tránh drift.
