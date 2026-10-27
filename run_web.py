#!/usr/bin/env python3
"""Chạy server phát triển của hệ thống quản lý kho hàng.

    python run_web.py

Mặc định mở http://127.0.0.1:5000. Cấu hình trong .env (xem .env.example).
Với production, dùng Waitress + wsgi.py thay vì Flask dev server.
"""
import os
from pathlib import Path

from webapp.env import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')

from webapp import create_app  # noqa: E402

app = create_app()


if __name__ == '__main__':
    host = os.environ.get('KHO_WEB_HOST', '127.0.0.1')
    port = int(os.environ.get('KHO_WEB_PORT', '5000'))
    debug = os.environ.get('KHO_WEB_DEBUG') == '1'
    app.run(host=host, port=port, debug=debug)
