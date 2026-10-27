"""Đọc file .env đơn giản, không cần thêm thư viện ngoài."""
import os
from pathlib import Path


def load_dotenv(path):
    """Nạp các cặp KEY=VALUE trong file .env vào os.environ.

    Không ghi đè biến đã có sẵn (ưu tiên cấu hình của môi trường/systemd).
    Hỗ trợ dòng trống, dòng comment, tiền tố `export ` và giá trị trong nháy.
    """
    path = Path(path)
    if not path.is_file():
        return False
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, separator, value = line.partition('=')
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
    return True
