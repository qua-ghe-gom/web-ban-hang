#!/usr/bin/env python3
"""Tạo người dùng web; mật khẩu nhập kín nếu không truyền từ API test."""
import argparse
import getpass
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

DEFAULT_DB = Path(__file__).resolve().parents[1] / 'data' / 'kho.db'


def create_user(db_path, username, display_name, role, password):
    username = username.strip()
    display_name = display_name.strip()
    if not username or not display_name or role not in {'admin', 'staff'}:
        raise ValueError('Thông tin người dùng không hợp lệ')
    if not password:
        raise ValueError('Mật khẩu không được để trống')
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('INSERT INTO users(username,password_hash,display_name,role) VALUES(?,?,?,?)',
                     (username, generate_password_hash(password), display_name, role))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError('Tên đăng nhập đã tồn tại') from exc
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Tạo tài khoản web kho hàng')
    parser.add_argument('--database', type=Path, default=DEFAULT_DB)
    parser.add_argument('--username', required=True)
    parser.add_argument('--display-name', required=True)
    parser.add_argument('--role', choices=['admin','staff'], default='staff')
    args = parser.parse_args()
    password = getpass.getpass('Mật khẩu: ')
    confirm = getpass.getpass('Nhập lại mật khẩu: ')
    if password != confirm:
        parser.error('Mật khẩu nhập lại không khớp')
    try:
        create_user(args.database, args.username, args.display_name, args.role, password)
    except ValueError as exc:
        parser.error(str(exc))
    print(f'Đã tạo người dùng {args.username}')

if __name__ == '__main__':
    main()
