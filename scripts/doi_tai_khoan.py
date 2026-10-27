#!/usr/bin/env python3
"""Đổi tên đăng nhập và/hoặc mật khẩu của một tài khoản web.

Ví dụ:
    # đổi tên đăng nhập (mật khẩu hỏi kín)
    .venv/bin/python scripts/doi_tai_khoan.py --id 1 --ten-dang-nhap admin

    # đổi mật khẩu, lấy từ stdin để không lộ trong lịch sử shell
    printf '%s' 'mat-khau-moi' | .venv/bin/python scripts/doi_tai_khoan.py --id 1 --mat-khau-stdin

Script cũng mở khoá tài khoản (failed_login_count = 0, locked_until = NULL).
"""
import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from werkzeug.security import generate_password_hash

DEFAULT_DB = Path(__file__).resolve().parents[1] / 'data' / 'kho.db'
MIN_PASSWORD_LEN = 12


def doi_tai_khoan(db_path, user_id, ten_dang_nhap=None, mat_khau=None):
    if mat_khau is not None and len(mat_khau) < MIN_PASSWORD_LEN:
        raise ValueError(f'Mật khẩu phải từ {MIN_PASSWORD_LEN} ký tự')
    if ten_dang_nhap is not None:
        ten_dang_nhap = ten_dang_nhap.strip()
        if not ten_dang_nhap:
            raise ValueError('Tên đăng nhập không được để trống')
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute('SELECT id, username FROM users WHERE id=?', (user_id,)).fetchone()
        if row is None:
            raise ValueError(f'Không có tài khoản id={user_id}')
        sets, params = ['failed_login_count=0', 'locked_until=NULL'], []
        if ten_dang_nhap is not None:
            sets.append('username=?')
            params.append(ten_dang_nhap)
        if mat_khau is not None:
            sets.append('password_hash=?')
            params.append(generate_password_hash(mat_khau))
        params.append(user_id)
        try:
            conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", params)
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError('Tên đăng nhập đã có người dùng') from exc
        return row[1], conn.execute('SELECT username FROM users WHERE id=?', (user_id,)).fetchone()[0]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Đổi tên đăng nhập / mật khẩu web kho')
    parser.add_argument('--database', type=Path, default=DEFAULT_DB)
    parser.add_argument('--id', type=int, default=1, help='id tài khoản (mặc định 1)')
    parser.add_argument('--ten-dang-nhap', help='tên đăng nhập mới')
    parser.add_argument('--mat-khau-stdin', action='store_true',
                        help='đọc mật khẩu mới từ stdin (cho script/CI)')
    args = parser.parse_args()

    mat_khau = None
    if args.mat_khau_stdin:
        mat_khau = sys.stdin.read().strip()
    elif not args.ten_dang_nhap:
        mat_khau = getpass.getpass('Mật khẩu mới: ')
        if mat_khau != getpass.getpass('Nhập lại: '):
            parser.error('Mật khẩu nhập lại không khớp')

    try:
        cu, moi = doi_tai_khoan(args.database, args.id, args.ten_dang_nhap, mat_khau)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'Đã cập nhật tài khoản id={args.id}: {cu} → {moi}'
          + (', mật khẩu mới đã đặt' if mat_khau else ''))


if __name__ == '__main__':
    main()
