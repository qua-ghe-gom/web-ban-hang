# Kiến trúc hệ thống

## Thành phần

```
Trình duyệt
   │  HTML server-rendered + JS nhẹ (không SPA, không build frontend)
   ▼
Flask app (webapp/)
   ├── auth        đăng nhập, session, chống dò mật khẩu
   ├── dashboard   KPI, hàng sắp hết, phiếu gần đây
   ├── inventory   tìm/chọn hàng, giỏ phiếu xuất
   ├── exports     tạo phiếu, xem chi tiết, huỷ, đánh dấu hoá đơn
   ├── products    CRUD sản phẩm, xoá mềm/thùng rác
   ├── photos      upload ảnh, nén, gallery theo ngày
   ├── print       phiếu in
   ├── backup      sao lưu/khôi phục DB + ảnh
   └── share       link chỉ-đọc ảnh cho chủ kho
   │
   ├── SQLite  data/kho.db
   └── File    data/media/anh_kho/YYYY/MM/
```

## Luồng xuất kho

1. Người dùng chọn mặt hàng và số lượng ở `/xuat-kho`; giỏ hàng nằm ở
   `session` thông qua `webapp/inventory.py` và `static/js/export-cart.js`.
2. Bấm **Tiếp tục** → `/xuat-kho/review` hiển thị lại phiếu, kiểm tra tồn kho.
3. Xác nhận → `confirm_export()` mở transaction SQLite `BEGIN IMMEDIATE`,
   kiểm tra lại tồn kho, ghi `export_orders`, `export_order_items` và
   `transactions`. Trigger `trg_update_quantity` cập nhật tồn kho.
4. Mỗi yêu cầu có `idempotency_key` để bấm hai lần không tạo hai phiếu.
5. Phiếu đã tạo có thể huỷ (trả hàng về kho bằng giao dịch bù) hoặc đánh dấu
   đã xuất hoá đơn; lịch sử thay đổi hoá đơn được ghi append-only.

## Dữ liệu

- `products`, `transactions`: schema gốc, tồn kho luôn suy ra từ giao dịch.
- `users`: tài khoản web, mật khẩu hash bằng Werkzeug.
- `export_orders`, `export_order_items`: phiếu xuất và snapshot tên/SKU/đơn vị
  tại thời điểm xuất.
- `invoice_status_events`: lịch sử bật/tắt trạng thái hoá đơn.
- `photos`: metadata ảnh; file thật lưu dưới `data/media`.

Migration nằm trong `migrations/`, chạy bằng `scripts/migrate_web_export.py`.
Script tự kiểm tra `PRAGMA integrity_check`, tạo backup trước khi đổi schema và
ghi `PRAGMA user_version`.

## Bảo mật

- CSRF token cho mọi request POST; so sánh constant-time.
- Session HttpOnly, SameSite=Lax, hết hạn 8 giờ, không gia hạn mỗi request.
- Sai mật khẩu 5 lần → khoá tài khoản 30 phút; giới hạn thêm theo IP+tài khoản.
- Cookie `Secure` khi `KHO_WEB_HTTPS=1`.
- Ảnh chỉ phục vụ sau đăng nhập qua route Flask, không map static trực tiếp.
- Link chỉ-đọc dùng token so sánh constant-time, giới hạn số lần thử, trả 404
  khi sai để không xác nhận đường dẫn tồn tại.
- Response có `Content-Security-Policy`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
