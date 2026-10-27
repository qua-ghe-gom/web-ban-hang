#!/usr/bin/env python3
"""Dọn backup cũ của kho.

Quy tắc (cố tình bảo thủ — backup là thứ không nên mất):

1. Mọi file backup **mới hơn 7 ngày** ⇒ giữ nguyên.
2. Cũ hơn 7 ngày ⇒ giữ **1 bản mới nhất cho mỗi tháng** làm mốc, xoá phần còn lại.
3. Riêng file zip ảnh (`anh-kho-*.zip`) ⇒ giữ **2 bản mới nhất**, xoá phần còn lại.
4. Chỉ xoá file khớp đúng mẫu tên backup; không đụng file lạ trong thư mục.

    don_backup.py --xem-truoc     # chỉ in ra
    don_backup.py                 # xoá thật
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path

GIU_NGAY = 7          # giữ tất cả backup trong N ngày gần nhất
GIU_ZIP = 2           # số bản zip ảnh giữ lại
MONG_MOI = 31         # bản mới nhất mỗi tháng giữ thêm bao nhiêu ngày (mốc)

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'
THU_MUC = [str(DATA_DIR / 'backups'), str(DATA_DIR)]
MAU_DB = re.compile(r'^kho\.db(-|\.backup-)(\d{8})-(\d{4,6})Z?$')
MAU_ZIP = re.compile(r'^anh-kho-\d{8}-\d{6}\.zip$')


def _ngay_trong_ten(ten: str, duong_dan: str) -> dt.date:
    m = re.search(r'(\d{8})-(\d{4,6})', ten)
    if m:
        try:
            return dt.datetime.strptime(m.group(1), '%Y%m%d').date()
        except ValueError:
            pass
    return dt.date.fromtimestamp(os.path.getmtime(duong_dan))


def _thu_thap():
    """Trả (ds_db, ds_zip): [(đường_dẫn, ngày_tên, ngày_sửa, cỡ)]"""
    ds_db, ds_zip = [], []
    for thu_muc in THU_MUC:
        if not os.path.isdir(thu_muc):
            continue
        for ten in sorted(os.listdir(thu_muc)):
            p = os.path.join(thu_muc, ten)
            if not os.path.isfile(p):
                continue
            if MAU_ZIP.match(ten) and thu_muc.endswith('backups'):
                ds_zip.append((p, _ngay_trong_ten(ten, p), os.path.getmtime(p),
                               os.path.getsize(p)))
            elif MAU_DB.match(ten):
                ds_db.append((p, _ngay_trong_ten(ten, p), os.path.getmtime(p),
                              os.path.getsize(p)))
    return ds_db, ds_zip


def _quyet_dinh(ds, giu_them):
    """ds: [(p, ngay_ten, mtime, co)] -> (giu, xoa). giu_them: set đường dẫn luôn giữ."""
    hom_nay = dt.date.today()
    moc = hom_nay - dt.timedelta(days=GIU_NGAY)
    giu, xoa = [], []
    for p, ngay, _mt, co in ds:
        if ngay >= moc or p in giu_them:
            giu.append((p, ngay, co, 'trong 7 ngày qua' if ngay >= moc else 'mốc theo tháng'))
    # bản mới nhất mỗi tháng (trong số còn lại) giữ thêm
    con_lai = [x for x in ds if (x[0], x[1], x[3]) not in
               [(g[0], g[1], g[2]) for g in giu]]
    thang_giu = {}
    for p, ngay, _mt, co in con_lai:
        k = (ngay.year, ngay.month)
        if k not in thang_giu or ngay > thang_giu[k][1]:
            thang_giu[k] = (p, ngay, co)
    for p, ngay, co in thang_giu.values():
        giu.append((p, ngay, co, 'mốc theo tháng'))
    da_giu = {g[0] for g in giu}
    for p, ngay, _mt, co in ds:
        if p not in da_giu:
            xoa.append((p, ngay, co))
    return giu, xoa


def sao_luu() -> tuple[str, str]:
    """Tạo 1 bản backup DB + 1 zip ảnh mới nhất rồi trả đường dẫn."""
    import shutil
    import zipfile
    goc = str(DATA_DIR)
    ts = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    os.makedirs(os.path.join(goc, 'backups'), exist_ok=True)
    db_moi = os.path.join(goc, 'backups', f'kho.db-{ts}')
    shutil.copy2(os.path.join(goc, 'kho.db'), db_moi)
    zip_moi = os.path.join(goc, 'backups', f'anh-kho-{ts}.zip')
    so_file = 0
    with zipfile.ZipFile(zip_moi, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for thu_muc, _dirs, files in os.walk(os.path.join(goc, 'media', 'anh_kho')):
            for f in files:
                p = os.path.join(thu_muc, f)
                z.write(p, os.path.relpath(p, goc)); so_file += 1
    print(f'💾 Sao lưu: {db_moi} ({os.path.getsize(db_moi)/1024:.0f} KB)')
    print(f'💾 Sao lưu: {zip_moi} ({so_file} file ảnh, {os.path.getsize(zip_moi)/1024/1024:.1f} MB)')
    return db_moi, zip_moi


def main() -> int:
    ap = argparse.ArgumentParser(description='Dọn backup cũ của kho (giữ mốc theo tháng).')
    ap.add_argument('--xem-truoc', action='store_true', help='chỉ in ra, không xoá')
    ap.add_argument('--sao-luu', action='store_true',
                    help='tạo backup DB + zip ảnh mới TRƯỚC khi dọn (dùng cho timer)')
    a = ap.parse_args()

    if a.sao_luu:
        sao_luu()

    ds_db, ds_zip = _thu_thap()
    giu_db, xoa_db = _quyet_dinh(ds_db, set())
    # zip: giữ N bản mới nhất, nhưng KHÁC NGÀY nhau (chạy 2 lần trong ngày không để 2 bản trùng)
    zip_sap = sorted(ds_zip, key=lambda x: (x[1], x[2]), reverse=True)
    giu_zip, da_giu_ngay = [], set()
    for p, n, _m, c in zip_sap:
        if len(giu_zip) >= GIU_ZIP:
            break
        if n in da_giu_ngay:
            continue
        da_giu_ngay.add(n)
        giu_zip.append((p, n, c, f'{GIU_ZIP} bản mới nhất, khác ngày'))
    giu_zip_path = {g[0] for g in giu_zip}
    xoa_zip = [(p, n, c) for p, n, _m, c in zip_sap if p not in giu_zip_path]

    def in_nhom(tieu_de, ds, ghi_chu_idx=3):
        print(f'\n{tieu_de} ({len(ds)})')
        for x in ds:
            p, ngay, co = x[0], x[1], x[2]
            them = f'  ← {x[ghi_chu_idx]}' if len(x) > 3 and x[3] else ''
            print(f'  {ngay}  {co/1024:8.0f} KB  {p}{them}')

    in_nhom('GIỮ LẠI — backup database', giu_db)
    in_nhom('XOÁ — backup database', xoa_db)
    in_nhom('GIỮ LẠI — zip ảnh', giu_zip)
    in_nhom('XOÁ — zip ảnh', xoa_zip)

    tong_xoa = sum(x[2] for x in xoa_db) + sum(x[2] for x in xoa_zip)
    tong_giu = sum(x[2] for x in giu_db) + sum(x[2] for x in giu_zip)
    print(f'\nGiữ {len(giu_db) + len(giu_zip)} file ({tong_giu/1024/1024:.1f} MB) · '
          f'xoá {len(xoa_db) + len(xoa_zip)} file ({tong_xoa/1024/1024:.1f} MB)')

    if a.xem_truoc:
        print('👀 Xem trước, chưa xoá gì.')
        return 0
    for p, _n, _c in xoa_db + xoa_zip:
        os.remove(p)
    print(f'🗑️  Đã xoá {len(xoa_db) + len(xoa_zip)} file, giải phóng {tong_xoa/1024/1024:.1f} MB')
    return 0


if __name__ == '__main__':
    sys.exit(main())
