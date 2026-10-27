#!/usr/bin/env python3
"""Tạo / đổi token cho link CHỈ-ĐỌC ảnh kho (/xem/<token>) của chủ kho.

Token ghi vào KHO_WEB_SHARE_TOKEN trong .env, sau đó cần restart ứng dụng
để có hiệu lực. Đổi token = link cũ chết ngay lập tức.

    python scripts/tao_link_chi_doc.py                 # xem link hiện tại
    python scripts/tao_link_chi_doc.py --tao-moi       # tạo token mới
    python scripts/tao_link_chi_doc.py --tao-moi --restart
"""
import argparse
import os
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = Path(os.environ.get('KHO_WEB_ENV_FILE', ROOT / '.env'))
KEY = 'KHO_WEB_SHARE_TOKEN'
DOMAIN = os.environ.get('KHO_WEB_PUBLIC_URL', 'http://localhost:5000')


def doc_env(path=ENV_PATH):
    data = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, _, v = line.partition('=')
                data[k.strip()] = v.strip()
    return data


def ghi_token(token, path=ENV_PATH):
    lines = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    out, found = [], False
    for line in lines:
        if line.strip().startswith(KEY + '='):
            out.append(f'{KEY}={token}')
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f'{KEY}={token}')
    # File chứa bí mật: chỉ chủ sở hữu đọc được.
    tmp = path.with_suffix('.tmp')
    tmp.write_text('\n'.join(out) + '\n', encoding='utf-8')
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description='Tạo token cho link chỉ-đọc ảnh kho')
    parser.add_argument('--tao-moi', action='store_true', help='sinh token mới (link cũ mất hiệu lực)')
    parser.add_argument('--restart', action='store_true', help='restart kho-web.service sau khi ghi')
    parser.add_argument('--domain', default=DOMAIN)
    args = parser.parse_args()

    token = doc_env().get(KEY, '')
    if args.tao_moi or not token:
        token = secrets.token_urlsafe(32)
        ghi_token(token)
        print(f'Đã ghi token mới vào {ENV_PATH}')
    else:
        print(f'Token hiện tại (trong {ENV_PATH}):')
    print(f'Link chỉ-đọc: {args.domain}/xem/{token}')

    if args.restart:
        subprocess.run(['systemctl', '--user', 'restart', 'kho-web.service'], check=True)
        print('Đã restart kho-web.service')


if __name__ == '__main__':
    main()
