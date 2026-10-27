# Triển khai production

Ví dụ dưới đây dùng Waitress + systemd user service trên Linux. Thay
`/home/USER/kho-hang` bằng đường dẫn thật.

## 1. Cài đặt

```bash
cd /home/USER/kho-hang
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # dán vào KHO_WEB_SECRET_KEY
chmod 600 .env
```

Trong `.env`, đặt `KHO_WEB_HTTPS=1` nếu chạy sau reverse proxy HTTPS.

## 2. Database

Với database mới:

```bash
.venv/bin/python scripts/init_db.py
.venv/bin/python scripts/migrate_web_export.py
.venv/bin/python scripts/create_user.py --username admin --display-name "Quản trị" --role admin
```

Với database đã có, chỉ cần chạy migration (script tự tạo backup trước khi đổi
schema):

```bash
.venv/bin/python scripts/migrate_web_export.py
```

## 3. systemd

`~/.config/systemd/user/kho-web.service`:

```ini
[Unit]
Description=Kho hang web
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/USER/kho-hang
EnvironmentFile=/home/USER/kho-hang/.env
ExecStart=/home/USER/kho-hang/.venv/bin/waitress-serve --listen=127.0.0.1:8000 --threads=4 wsgi:application
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/USER/kho-hang/data

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now kho-web.service
systemctl --user status kho-web.service
journalctl --user -u kho-web.service -n 100 --no-pager
```

Nếu dùng Nginx/Caddy, trỏ reverse proxy tới `127.0.0.1:8000` và bật HTTPS.
Chỉ đặt `KHO_WEB_HTTPS=1` khi HTTPS đã hoạt động, nếu không cookie đăng nhập sẽ
không được gửi.

## 4. Kiểm tra sau triển khai

- Mở trang đăng nhập, đăng nhập bằng tài khoản admin.
- Vào **Sản phẩm** và **Xuất kho** thử tạo một phiếu nhỏ.
- Vào **Backup**, bấm tạo backup và kiểm tra cặp file trong `data/backups/`.
- Kiểm tra `data/` là thư mục duy nhất cần quyền ghi.
- Không commit `.env`, `data/`, `backups/` lên Git.
