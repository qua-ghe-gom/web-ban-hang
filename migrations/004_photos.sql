-- Migration 004: Bảng ảnh kho (tab Ảnh kho)
-- Created: 2026-09-03
-- Description: Mỗi dòng là một ảnh đã up kèm thông tin bán hàng.
-- filename/thumb_filename là đường dẫn TƯƠNG ĐỐI dưới MEDIA_DIR.
-- taken_on là ngày nghiệp vụ người dùng nhập (YYYY-MM-DD), created_at là mốc hệ thống UTC.

CREATE TABLE photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    thumb_filename TEXT NOT NULL,
    taken_on TEXT NOT NULL,
    caption TEXT,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    quantity INTEGER,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at TEXT
);
CREATE INDEX idx_photos_taken_on ON photos(taken_on);
