#!/usr/bin/env python3
"""Tạo database + ảnh mẫu để chạy thử giao diện.

Toàn bộ dữ liệu là giả lập. Không dùng script này trên database thật.

    python scripts/seed_demo.py
    python scripts/seed_demo.py --database /tmp/demo.db --media /tmp/demo-media

Tài khoản mặc định:
    admin     / Admin@Demo2026
    nhanvien  / Staff@Demo2026

Sau khi tạo, chạy `python run_web.py` rồi mở http://127.0.0.1:5000.
"""
from __future__ import annotations

import argparse
import io
import os
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash

from scripts.init_db import init_db
from scripts.migrate_web_export import migrate_database
from webapp.services.export_service import cancel_export_order, confirm_export
from webapp.services.photo_storage import store_image

DEFAULT_DB = Path(os.environ.get('KHO_WEB_DATABASE', ROOT / 'data' / 'kho.db'))
DEFAULT_MEDIA = Path(os.environ.get('KHO_WEB_MEDIA_DIR', ROOT / 'data' / 'media'))
PHOTO_DIR = ROOT / 'demo' / 'photos'

ADMIN_PASSWORD = 'Admin@Demo2026'
STAFF_PASSWORD = 'Staff@Demo2026'

PRODUCTS = [
    ('Thùng carton nhỏ', 1, 'thùng', 4500, 6500, 160),
    ('Thùng carton vừa', 1, 'thùng', 7000, 10000, 120),
    ('Thùng carton lớn', 1, 'thùng', 12000, 17000, 80),
    ('Hộp giấy đựng tài liệu', 1, 'hộp', 15000, 22000, 65),
    ('Giấy in A4 mẫu', 2, 'ram', 55000, 70000, 42),
    ('Bút bi xanh mẫu', 2, 'hộp', 25000, 35000, 75),
    ('Sổ ghi chép mẫu', 2, 'quyển', 18000, 26000, 4),
    ('Bìa hồ sơ mẫu', 2, 'tập', 20000, 30000, 55),
    ('Băng keo trong', 3, 'cuộn', 8000, 12000, 130),
    ('Màng bọc hàng mẫu', 3, 'cuộn', 65000, 85000, 35),
    ('Túi đóng hàng mẫu', 3, 'gói', 30000, 45000, 6),
    ('Dây buộc kiện mẫu', 3, 'cuộn', 40000, 55000, 48),
]

PHOTOS = [
    ('pexels-5775099-kho-hang.jpg', 'Lối đi kho mẫu — ảnh minh họa Pexels / Handi Boyz LLC'),
    ('pexels-11835350-ke-hang.jpg', 'Kệ lưu trữ minh họa — ảnh minh họa Pexels / Antonius Natan'),
    ('pexels-27111449-dong-thung.jpg', 'Khu vực hàng đóng thùng — ảnh minh họa Pexels / Ryan Klaus'),
]


def seed(database=DEFAULT_DB, media=DEFAULT_MEDIA):
    database = Path(database)
    media = Path(media)
    if database.exists():
        raise SystemExit(
            f'Đã có database tại {database}. Xóa file này (và thư mục media mẫu) '
            'nếu muốn tạo lại dữ liệu demo.'
        )
    if media.exists() and any(media.iterdir()):
        raise SystemExit(f'Thư mục media {media} đang có dữ liệu; không ghi đè.')

    init_db(database)
    migrate_database(database, create_backup=False)
    media.mkdir(parents=True, exist_ok=True)

    today = date.today()
    now = datetime.now(timezone.utc)
    with sqlite3.connect(database) as conn:
        conn.execute('PRAGMA foreign_keys=ON')

        for user_id, username, password, display_name, role in (
            (1, 'admin', ADMIN_PASSWORD, 'Quản trị mẫu', 'admin'),
            (2, 'nhanvien', STAFF_PASSWORD, 'Nhân viên mẫu', 'staff'),
        ):
            conn.execute(
                '''INSERT INTO users(id,username,password_hash,display_name,role)
                   VALUES(?,?,?,?,?)''',
                (user_id, username, generate_password_hash(password), display_name, role),
            )

        conn.execute('DELETE FROM categories')
        for category_id, name in enumerate(('Bao bì', 'Văn phòng phẩm', 'Vật tư đóng gói'), 1):
            conn.execute(
                'INSERT INTO categories(id,name,description) VALUES(?,?,?)',
                (category_id, name, 'Danh mục giả lập phục vụ trình diễn'),
            )

        for supplier_id in range(1, 4):
            conn.execute(
                'INSERT INTO suppliers(id,name,email,address,note) VALUES(?,?,?,?,?)',
                (
                    supplier_id,
                    f'Nhà cung cấp mẫu {supplier_id:02d}',
                    f'supplier{supplier_id}@example.com',
                    f'Địa chỉ giả lập số {supplier_id}, Khu Demo',
                    'Dữ liệu mẫu; không phải doanh nghiệp thật',
                ),
            )

        for product_id, (name, category, unit, cost, price, stock) in enumerate(PRODUCTS, 1):
            conn.execute(
                '''INSERT INTO products(
                       id, sku, name, category_id, supplier_id, unit,
                       cost_price, sell_price, min_quantity, location, note, weight)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (
                    product_id,
                    f'DEMO-{product_id:03d}',
                    name,
                    category,
                    category,
                    unit,
                    cost,
                    price,
                    10,
                    f'Kệ {category}-{product_id:02d}',
                    'Mặt hàng giả lập, chỉ dùng để demo',
                    round(product_id * 0.15, 2),
                ),
            )
            conn.execute(
                '''INSERT INTO transactions(
                       product_id, type, quantity, unit_price, total_amount, note, created_at)
                   VALUES(?,'import',?,?,?,?,?)''',
                (
                    product_id,
                    stock,
                    cost,
                    stock * cost,
                    'Nhập kho mẫu ban đầu',
                    (now - timedelta(days=8)).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                ),
            )

    for i in range(1, 9):
        order = confirm_export(
            str(database),
            1 if i % 2 else 2,
            [
                {'product_id': 1 + i % 6, 'quantity': i + 1},
                {'product_id': 9, 'quantity': 2},
            ],
            {
                'customer_name': f'Khách hàng mẫu {i:02d}',
                'customer_phone': '',
                'delivery_address': f'Điểm giao giả lập {i:02d}, Khu Demo',
                'note': 'Phiếu trình diễn; không có giá trị giao dịch thực tế',
            },
            f'demo-order-{i:02d}',
            invoice_issued=i % 2 == 0,
        )
        if i == 8:
            cancel_export_order(str(database), order['order_code'], 1, 'Hủy thử nghiệm dữ liệu mẫu')

    with sqlite3.connect(database) as conn:
        for i, (filename, caption) in enumerate(PHOTOS):
            source = PHOTO_DIR / filename
            if not source.exists():
                continue
            taken = today - timedelta(days=i)
            stored = store_image(str(media), io.BytesIO(source.read_bytes()), taken)
            conn.execute(
                '''INSERT INTO photos(filename,thumb_filename,taken_on,caption,created_by)
                   VALUES(?,?,?,?,1)''',
                (stored.filename, stored.thumb_filename, str(taken), caption),
            )
        conn.execute('PRAGMA foreign_keys=ON')
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()

    credentials = database.parent / 'DANG_NHAP-DEMO.txt'
    credentials.write_text(
        'Tài khoản demo, chỉ dùng cho dữ liệu giả lập.\n\n'
        f'admin: {ADMIN_PASSWORD}\n'
        f'nhanvien: {STAFF_PASSWORD}\n',
        encoding='utf-8',
    )
    try:
        os.chmod(credentials, 0o600)
    except OSError:
        pass

    print(f'✅ Database demo: {database}')
    print(f'✅ Ảnh demo:      {media}')
    print(f'✅ Đăng nhập:     admin / {ADMIN_PASSWORD}')
    print(f'                 nhanvien / {STAFF_PASSWORD}')
    print(f'   (đã ghi vào {credentials})')
    return database


def main():
    parser = argparse.ArgumentParser(description='Tạo dữ liệu demo cho hệ thống kho')
    parser.add_argument('--database', type=Path, default=DEFAULT_DB)
    parser.add_argument('--media', type=Path, default=DEFAULT_MEDIA)
    args = parser.parse_args()
    seed(args.database, args.media)


if __name__ == '__main__':
    main()
