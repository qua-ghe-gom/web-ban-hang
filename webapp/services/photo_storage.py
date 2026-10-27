"""Decode, nén và lưu file ảnh cho tab Ảnh kho.

Tách khỏi blueprint để test được phần xử lý ảnh mà không cần Flask,
blueprint chỉ còn lo form/flash/redirect. Ảnh gốc KHÔNG giữ lại — bản gốc
còn trên điện thoại người chụp, giữ lại thì disk phình 10 lần.
"""
import io
import os
import uuid
from dataclasses import dataclass
from datetime import date

from PIL import Image, ImageOps

MAX_FILE_BYTES = 95 * 1024 * 1024   # cap từng file; cap toàn request do Flask
MAX_PIXELS = 2000
THUMB_PIXELS = 480
FULL_QUALITY = 82
THUMB_QUALITY = 80


class NotAnImage(ValueError):
    """File gửi lên không decode được bằng Pillow (sai định dạng, file hỏng)."""


@dataclass
class StoredPhoto:
    filename: str        # tương đối dưới MEDIA_DIR: 'anh_kho/YYYY/MM/<uuid>.jpg'
    thumb_filename: str


def _flatten_to_rgb(img):
    """JPEG không có kênh alpha. convert('RGB') ngu sẽ ra nền đen nên ghép
    ảnh có alpha lên nền trắng; palette (P) phải qua RGBA trước để giữ màu trong suốt đúng."""
    if img.mode == 'P':
        img = img.convert('RGBA')
    if img.mode == 'RGB':
        return img
    if 'A' in img.getbands():
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    return img.convert('RGB')


def store_image(media_dir, file_storage, taken_on: date) -> StoredPhoto:
    """Decode + nén + lưu 2 file. raise NotAnImage nếu không phải ảnh."""
    data = file_storage.read()
    if not data:
        raise NotAnImage('File rỗng')
    if len(data) > MAX_FILE_BYTES:
        raise NotAnImage('Ảnh lớn hơn 95MB')
    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # buộc decode ngay — file hỏng/giả bị chặn tại đây
    except Exception as exc:  # UnidentifiedImageError, OSError, DecompressionBombError…
        raise NotAnImage('File không phải ảnh hợp lệ') from exc

    # Ảnh điện thoại lưu hướng chụp trong EXIF; phải xoay theo EXIF TRƯỚC khi
    # nén lại (việc lưu mới qua Pillow xóa sạch EXIF, kể cả GPS).
    img = ImageOps.exif_transpose(img)
    img = _flatten_to_rgb(img)
    img.thumbnail((MAX_PIXELS, MAX_PIXELS), Image.LANCZOS)

    month_dir = os.path.join('anh_kho', f'{taken_on.year:04d}', f'{taken_on.month:02d}')
    os.makedirs(os.path.join(media_dir, month_dir), exist_ok=True)
    name = uuid.uuid4().hex
    filename = os.path.join(month_dir, f'{name}.jpg')
    thumb_filename = os.path.join(month_dir, f'{name}_t.jpg')

    img.save(os.path.join(media_dir, filename), 'JPEG', quality=FULL_QUALITY, optimize=True)
    thumb = img.copy()
    thumb.thumbnail((THUMB_PIXELS, THUMB_PIXELS), Image.LANCZOS)
    thumb.save(os.path.join(media_dir, thumb_filename), 'JPEG', quality=THUMB_QUALITY, optimize=True)
    return StoredPhoto(filename=filename.replace(os.sep, '/'),
                       thumb_filename=thumb_filename.replace(os.sep, '/'))


def delete_stored_files(media_dir, *relative_paths):
    """Xóa file ảnh. Thiếu file không phải lỗi — xóa phải làm được 2 lần."""
    for rel in relative_paths:
        if not rel:
            continue
        try:
            os.remove(os.path.join(media_dir, rel.replace('/', os.sep)))
        except FileNotFoundError:
            pass


def media_usage_bytes(media_dir) -> int:
    """Tổng dung lượng file đã lưu dưới MEDIA_DIR/anh_kho (gốc + thumbnail).

    Dùng cho quota tổng dung lượng ảnh kho; thư mục chưa tồn tại = 0.
    """
    total = 0
    root = os.path.join(media_dir, 'anh_kho')
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass  # file biến mất giữa chừng — bỏ qua, đếm thiếu an toàn hơn đếm thừa
    return total


def stored_file_bytes(media_dir, saved: StoredPhoto) -> int:
    """Dung lượng đĩa của 1 ảnh vừa lưu (gốc + thumbnail). Thiếu file tính 0."""
    total = 0
    for rel in (saved.filename, saved.thumb_filename):
        try:
            total += os.path.getsize(os.path.join(media_dir, rel.replace('/', os.sep)))
        except OSError:
            pass
    return total
