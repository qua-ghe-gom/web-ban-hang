# Sao lưu & khôi phục

## Trên giao diện

Mục **Backup** (chỉ tài khoản admin) tạo một cặp file cùng thời điểm:

| File | Nội dung |
| --- | --- |
| `data/backups/kho.db-<YYYYmmdd-HHMMSS>` | Toàn bộ database SQLite |
| `data/backups/anh-kho-<YYYYmmdd-HHMMSS>.zip` | Toàn bộ thư mục `data/media` |

Khôi phục theo mốc sẽ trả cả database lẫn ảnh về đúng thời điểm đó. Trước khi
ghi đè, ứng dụng tự tạo thêm một cặp file `before-restore` để có thể lấy lại
trạng thái vừa bị thay thế.

> Khôi phục mốc cũ sẽ làm mất dữ liệu/ảnh phát sinh sau mốc đó. Cặp file
> `before-restore` vẫn giữ lại trạng thái trước khi khôi phục.

## Dọn backup cũ

```bash
python scripts/don_backup.py --xem-truoc   # xem trước, chưa xoá
python scripts/don_backup.py               # xoá theo quy tắc
python scripts/don_backup.py --sao-luu     # tạo backup mới rồi mới dọn
```

Quy tắc:

1. Giữ tất cả backup trong 7 ngày gần nhất.
2. Cũ hơn 7 ngày: giữ bản mới nhất của mỗi tháng làm mốc.
3. Zip ảnh: giữ 2 bản mới nhất nhưng khác ngày.
4. Chỉ xoá file khớp đúng mẫu tên backup, không đụng file lạ.

## Sao lưu ra ngoài máy chủ

Nút tải trong trang Backup tải được từng file DB hoặc ZIP ảnh. Nên định kỳ tải
về máy khác hoặc đồng bộ `data/backups/` lên nơi lưu trữ ngoài (S3, Google
Drive, ổ cứng...). Backup nằm cùng máy chủ không được coi là backup ngoài.

## Khôi phục thủ công

Dừng ứng dụng trước khi thay file:

```bash
systemctl --user stop kho-web.service
cp data/backups/kho.db-20261027-115136 data/kho.db
# nếu cần khôi phục ảnh:
unzip -o data/backups/anh-kho-20261027-115136.zip -d data/media
systemctl --user start kho-web.service
```
