# Đưa repo lên GitHub

Thư mục này đã có sẵn `.gitignore`, README, CI. Chưa có commit nào.

```bash
cd kho-hang-github

git init -b main
git add .
git status                 # kiểm tra không có .env, data/, media/, backups/
git commit -m "Khoi tao he thong quan ly kho hang"

# Tạo repo trống trên GitHub trước, rồi:
git remote add origin https://github.com/<TEN_BAN>/<TEN_REPO>.git
git push -u origin main
```

Nếu dùng SSH:

```bash
git remote add origin git@github.com:<TEN_BAN>/<TEN_REPO>.git
```

## Kiểm tra trước khi push

```bash
git ls-files | grep -E '(^|/)(data|media|backups|\.env)' && echo "CÓ FILE KHÔNG NÊN COMMIT" || echo "OK"
```

Các file **không bao giờ** được commit:

- `.env`, `.kho-web.env` — chứa secret key/token.
- `data/` — database, ảnh kho, backup thật.
- `media/`, `backups/` — dữ liệu thật.
- `.venv/`, `__pycache__/`.

Nếu đã lỡ commit secret, hãy đổi secret/token ngay và xoá file khỏi lịch sử
Git (BFG Repo-Cleaner hoặc `git filter-repo`), không chỉ xoá ở commit mới.
