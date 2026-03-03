# Monitoring và Rollback Checklist

Tài liệu vận hành nhanh cho stack OmniMind (license-server + license-dashboard + app client).

## 1. Mục tiêu

- Theo dõi sớm lỗi thanh toán/webhook/deploy.
- Có checklist rollback rõ ràng để giảm downtime.
- Đảm bảo sau rollback hệ thống vẫn xử lý giao dịch an toàn.

## 2. Chỉ số cần theo dõi

- `transactions_24h`: tổng giao dịch 24h, tỉ lệ `SUCCESS/PENDING/FAILED`.
- `overdue_pending_count`: số giao dịch `PENDING` quá 30 phút.
- `webhook_24h.unmatched`: số webhook không match được `payment_content`.
- `webhook_24h.amount_mismatch`: số webhook lệch số tiền.
- `audits_24h.error_events`: số event audit lỗi trong 24h.

Nguồn API: `GET /api/v1/admin/omnimind/monitoring/summary`.

## 3. Checklist rollback khi có sự cố

1. Tắt release mới trên CMS (set inactive) để dừng phát sinh lỗi mới.
2. Kiểm tra tab Monitoring:
   - pending quá hạn,
   - unmatched webhook,
   - amount mismatch,
   - audit error.
3. Đối soát từng giao dịch nghi vấn qua `payment_content` + `provider_transaction_id` với log SePay.
4. Nếu webhook bị miss:
   - replay webhook từ SePay (nếu có),
   - hoặc xử lý bù trạng thái transaction thủ công (có audit).
5. Redeploy backend/CMS về bản ổn định gần nhất.
6. Chạy smoke test sau rollback:
   - tạo order mới,
   - thanh toán thử,
   - poll trạng thái order,
   - xác nhận entitlement cập nhật đúng.
7. Mở lại release mới theo canary (từng phần trăm traffic) thay vì full.

## 4. Log tập trung

- App client ghi log runtime tại:
  - macOS: `~/Library/Application Support/OmniMind/logs/omnimind_app.log`
  - Windows: `%LOCALAPPDATA%/OmniMind/logs/omnimind_app.log`
- Nên thu thập thêm backend log và webhook log vào cùng hệ thống quan sát (ELK/Loki/DataDog nếu có).

