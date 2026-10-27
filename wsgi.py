"""Entrypoint WSGI cho production (Waitress, Gunicorn, PythonAnywhere...).

    waitress-serve --listen=0.0.0.0:8000 wsgi:application

File .env cạnh project được nạp trước khi tạo app. Trên host khác, có thể đặt
biến môi trường trực tiếp thay vì dùng .env.
"""
from pathlib import Path

from webapp.env import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')

from webapp import create_app  # noqa: E402

application = create_app()
