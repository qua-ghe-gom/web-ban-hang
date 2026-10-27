#!/usr/bin/env python3
"""Khởi tạo database SQLite của hệ thống quản lý kho hàng.

Chỉ tạo schema gốc (categories, suppliers, products, transactions) và trigger
tồn kho. Các bảng của web (users, export_orders, photos...) được tạo tiếp bằng
`scripts/migrate_web_export.py`.

    python scripts/init_db.py
    python scripts/init_db.py --database /duong/dan/kho.db
"""
import argparse
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get('KHO_WEB_DATABASE', ROOT / 'data' / 'kho.db'))


def init_db(db_path=DEFAULT_DB):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                address TEXT,
                note TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category_id INTEGER,
                supplier_id INTEGER,
                unit TEXT DEFAULT 'cái',
                cost_price REAL DEFAULT 0,
                sell_price REAL DEFAULT 0,
                quantity INTEGER DEFAULT 0,
                min_quantity INTEGER DEFAULT 10,
                location TEXT,
                image_path TEXT,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                weight REAL DEFAULT 0,
                FOREIGN KEY (category_id) REFERENCES categories(id),
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('import', 'export', 'adjust')),
                quantity INTEGER NOT NULL,
                unit_price REAL,
                total_amount REAL,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_product ON transactions(product_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(created_at)")

        c.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_update_quantity
            AFTER INSERT ON transactions
            FOR EACH ROW
            BEGIN
                UPDATE products
                SET quantity = CASE
                    WHEN NEW.type = 'import' THEN quantity + NEW.quantity
                    WHEN NEW.type = 'export' THEN quantity - NEW.quantity
                    WHEN NEW.type = 'adjust' THEN NEW.quantity
                END,
                updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.product_id;
            END
        """)

        categories = [
            ('Quần áo', 'Các sản phẩm may mặc'),
            ('Điện tử', 'Thiết bị điện tử'),
            ('Gia dụng', 'Đồ gia dụng'),
            ('Thực phẩm', 'Thực phẩm, đồ uống'),
            ('Khác', 'Loại khác'),
        ]
        c.executemany("INSERT OR IGNORE INTO categories (name, description) VALUES (?, ?)", categories)

        conn.commit()
        return db_path
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Khởi tạo database kho hàng')
    parser.add_argument('--database', type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    path = init_db(args.database)
    print(f'✅ Đã khởi tạo database tại: {path}')
    print(f'   File size: {path.stat().st_size} bytes')
    print('   Bước tiếp theo: python scripts/migrate_web_export.py')


if __name__ == '__main__':
    main()
