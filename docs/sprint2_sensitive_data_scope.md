# Sprint 2 Scope - Sensitive Local Data Encryption

## Scope chốt
Sprint 2 chỉ mã hoá 3 nhóm dữ liệu nhạy cảm local:

1. `app_configs.telegram_token`
2. `app_configs.license_jwt`
3. `vault_resources.credentials`

Các cột/chat memory khác (`conversation_messages`, `memory_summaries`, `memory_facts`) giữ nguyên plaintext trong Sprint 2.

## Format mã hoá
- Dữ liệu nhạy cảm được lưu theo prefix: `enc:v1:<ciphertext>`.
- Nếu bản cũ còn plaintext/token cũ, app sẽ migrate khi khởi động.

## Mục tiêu kiểm chứng
- Không còn plaintext trực tiếp cho 3 nhóm dữ liệu trong SQLite sau migration.
- App vẫn đọc/ghi bình thường qua `ConfigManager` và `VaultManager`.

## Cách verify nhanh
Chạy script:

```bash
python3 scripts/verify_sensitive_storage.py
```

Kết quả mong muốn:
- Exit code `0`.
- `telegram_token`, `license_jwt` hiển thị `ENCRYPTED` hoặc `EMPTY/NOT_SET`.
- `vault_resources.credentials` không còn record `PLAINTEXT`.

Nếu thấy `PLAINTEXT`:
1. Mở app OmniMind 1 lần để migration tự chạy.
2. Chạy lại script verify.
