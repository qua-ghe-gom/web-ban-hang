# Hướng dẫn sử dụng nhanh

Tài liệu này dành cho bản GitHub. Bản này **không kèm database** — chạy
`seed_demo.py` một lần để tạo dữ liệu mẫu và tài khoản demo.

## 1. Cài đặt

Yêu cầu Python 3.10+ (khuyến nghị 3.13).

```bash
cd kho-hang-github

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Mở `.env`, dán chuỗi vừa tạo vào:

```env
KHO_WEB_SECRET_KEY=<chuỗi vừa tạo>
```

Các dòng còn lại có thể giữ mặc định.

## 2. Tạo dữ liệu mẫu

```bash
python scripts/seed_demo.py
```

Lệnh này tạo:

- `data/kho.db` — database mẫu.
- `data/media/anh_kho/` — 3 ảnh Pexels + thumbnail.
- `data/DANG_NHAP-DEMO.txt` — tài khoản demo.

Nếu `data/kho.db` đã tồn tại, script sẽ từ chối chạy để tránh ghi đè. Muốn tạo
lại từ đầu:

```bash
rm -rf data/kho.db data/media data/backups
python scripts/seed_demo.py
```

## 3. Chạy web

```bash
python run_web.py
```

Mở http://127.0.0.1:5000.

Nếu cổng 5000 đang bận, sửa `KHO_WEB_PORT` trong `.env` hoặc chạy:

```bash
KHO_WEB_PORT=5001 python run_web.py
```

## 4. Tài khoản demo

| Tài khoản | Mật khẩu | Quyền |
| --- | --- | --- |
| `admin` | `Admin@Demo2026` | Quản trị |
| `nhanvien` | `Staff@Demo2026` | Nhân viên |

Đây là tài khoản giả lập, chỉ dùng cho dữ liệu mẫu. Không dùng mật khẩu này
cho hệ thống thật.

## 5. Các màn hình chính

| Màn hình | Việc dùng |
| --- | --- |
| **Dashboard** | Xem tổng sản phẩm, tồn kho, hàng sắp hết, phiếu gần đây |
| **Xuất kho** | Tìm hàng, chọn số lượng, thêm vào phiếu, xem lại và xác nhận |
| **Sản phẩm** | Thêm/sửa/xoá mềm sản phẩm; admin xem thùng rác |
| **Ảnh kho** | Up ảnh, xem theo ngày, sửa chú thích/xoá ảnh |
| **Lịch sử** | Xem lại phiếu xuất, in phiếu, huỷ phiếu, đánh dấu hoá đơn |
| **Backup** | Tạo cặp backup DB + ZIP ảnh; khôi phục theo mốc (admin) |

## 6. Đổi mật khẩu / tạo tài khoản khác

Đổi mật khẩu tài khoản id=1:

```bash
printf '%s' 'mat-khau-moi-tu-12-ky-tu' | python scripts/doi_tai_khoan.py --id 1 --mat-khau-stdin
```

Tạo tài khoản mới:

```bash
python scripts/create_user.py --username nhanvien2 --display-name "Nhân viên 2" --role staff
```

## 7. Lỗi thường gặp

| Lỗi | Cách xử lý |
| --- | --- |
| `KHO_WEB_SECRET_KEY is required` | Chưa điền `KHO_WEB_SECRET_KEY` trong `.env` |
| Trang đăng nhập báo sai tài khoản | Chưa chạy `python scripts/seed_demo.py` |
| `Address already in use` | Đổi `KHO_WEB_PORT` trong `.env` |
| Upload ảnh lỗi | Chưa cài Pillow: `pip install -r requirements.txt` |

## 8. Lưu ý

- Bản GitHub chỉ có dữ liệu mẫu, không có database/ảnh/tài khoản thật.
- Không commit `.env`, `data/`, `media/`, `backups/` lên Git.
- Hướng dẫn đưa repo lên GitHub: `docs/DAY_LEN_GITHUB.md`.
- Triển khai production: `docs/TRIEN_KHAI.md`.
