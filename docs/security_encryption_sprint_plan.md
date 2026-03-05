# OmniMind Security & Encryption Sprint Plan

## Mục tiêu
Triển khai bảo vệ dữ liệu theo từng lớp: dữ liệu local, config động, mã nguồn client và vòng đời khóa/token; giảm rủi ro lộ thông tin khi phát hành app desktop.

## Sprint 1: Kiểm kê dữ liệu nhạy cảm + chốt biên backend/client (2-3 ngày)
- Mục tiêu: Xác định chính xác dữ liệu nào cần mã hóa, dữ liệu nào phải xử lý hoàn toàn ở backend.
- Việc làm:
  - Audit `src/engine`, `src/ui`, `license-server`, `license-dashboard`.
  - Lập danh mục secrets/config/rules.
  - Liệt kê hardcode cần loại bỏ khỏi client.
- Output:
  - `data-classification.md`.
  - Danh sách hardcode cần cleanup.
- Done khi:
  - Không còn secret hệ thống nằm trong app client.

## Sprint 2: Mã hóa dữ liệu nhạy cảm local trong app (3-4 ngày)
- Mục tiêu: Mã hóa tại chỗ các dữ liệu nhạy cảm phía người dùng.
- Việc làm:
  - Mã hóa `telegram_token`, vault entries, token local trước khi lưu SQLite.
  - Chuẩn hóa key derivation theo máy.
  - Thêm migration cho dữ liệu cũ.
- Output:
  - DB migration + lớp `encrypt/decrypt` dùng chung.
  - Cơ chế fallback đọc dữ liệu cũ.
- Done khi:
  - Đọc trực tiếp SQLite không thấy plain text token/password.

## Sprint 3: Bảo vệ kênh cấu hình động từ backend (2-3 ngày)
- Mục tiêu: Tránh app dùng config giả hoặc config bị can thiệp.
- Việc làm:
  - Ký payload config/release (matrix, checksum, feature flags) ở backend.
  - App verify chữ ký trước khi áp dụng.
  - Giảm dần fallback hardcode local.
- Output:
  - API trả config có chữ ký.
  - Logic verify chữ ký trong app.
- Done khi:
  - App từ chối config sai chữ ký.

## Sprint 4: Bảo vệ mã nguồn client khi phát hành (3-5 ngày)
- Mục tiêu: Giảm khả năng reverse code Python.
- Việc làm:
  - Áp dụng obfuscation cho module nhạy cảm (ví dụ PyArmor).
  - Chuyển phát hành từ zip sang installer `.exe`.
  - Tách symbol/debug khỏi bản phát hành.
- Output:
  - Pipeline build mới cho Windows/macOS.
  - Artefact installer dùng cho phát hành.
- Done khi:
  - Không còn phát hành zip lộ trực tiếp cấu trúc runtime.
  - Có pipeline release hardened riêng (workflow + script local).

### Ghi chú triển khai
- Script build hardened: `scripts/release/build_hardened.py`
- Workflow release hardened: `.github/workflows/release-hardened.yml`
- Installer template Windows: `installer/windows/OmniMind.iss`

## Sprint 5: Quản lý khóa + vòng đời token (2-3 ngày)
- Mục tiêu: Có cơ chế rotate/revoke an toàn.
- Việc làm:
  - Key versioning.
  - Token TTL ngắn + refresh flow.
  - Revoke endpoint + audit log truy cập config/secret.
- Output:
  - Tài liệu policy khóa/token.
  - Playbook rotate key.
- Done khi:
  - Rotate key không cần cập nhật app.

## Sprint 6: Hardening vận hành + kiểm thử tấn công (3-4 ngày)
- Mục tiêu: Chốt mức an toàn trước rollout.
- Việc làm:
  - Test decompile.
  - Test MITM config.
  - Test tamper installer.
  - Test mất key/rollback.
- Output:
  - Security checklist phát hành.
  - Báo cáo residual risk.
- Done khi:
  - Pass checklist phát hành bảo mật.

### Trạng thái triển khai (2026-03-05)
- Hoàn thành Item 1 (decompile/reverse surface):
  - `scripts/security/test_decompile_surface.py`
- Hoàn thành Item 5 (chaos runtime Telegram/Codex):
  - `scripts/security/run_runtime_chaos_checks.py`
- Hoàn thành Item 6 (release checklist + rollback playbook):
  - `docs/sprint6_release_checklist_and_rollback_playbook.md`
