import os
import re
import shutil
import sqlite3
import zipfile
from datetime import datetime
from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, send_from_directory, url_for)
from .auth import login_required

bp = Blueprint('backup', __name__)

# 1 bản backup = 1 cặp file cùng mốc thời gian: kho.db-<ts> (dữ liệu) +
# anh-kho-<ts>.zip (toàn bộ ảnh trong MEDIA_DIR). Khôi phục/xóa luôn thao
# tác theo cặp để DB và ảnh không lệch nhau.
_SET_TS_RE = re.compile(r'\d{8}-\d{6}\Z')
_DB_FILE_RE = re.compile(r'kho\.db-(\d{8}-\d{6})\Z')
_ZIP_FILE_RE = re.compile(r'anh-kho-(\d{8}-\d{6})\.zip\Z')
# File tải về được — whitelist chặt, không nhận tên lạ từ URL
_DOWNLOADABLE_RE = re.compile(r'(kho\.db-\d{8}-\d{6}|anh-kho-\d{8}-\d{6}\.zip)\Z')
# File an toàn/bản cũ (before-restore, backup kiểu legacy) — chỉ cho xóa
_OTHER_FILE_RE = re.compile(
    r'(kho\.db\.backup-[\w.-]+|kho\.db\.before-restore-[\w.-]+|anh-kho-before-restore-[\w.-]+\.zip)\Z')


def _db_path():
    """DB đang dùng thật, không hardcode — nếu không thì test và mọi cài đặt
    khác đường dẫn sẽ sao lưu/khôi phục sai file."""
    return current_app.config['DATABASE']


def _backup_dir():
    path = os.path.join(os.path.dirname(os.path.abspath(_db_path())), 'backups')
    os.makedirs(path, exist_ok=True)
    return path


def _media_dir():
    return current_app.config['MEDIA_DIR']


def _zip_media(zip_path, media):
    """Đóng gói toàn bộ media/ vào zip. Ảnh JPEG đã nén sẵn nên dùng ZIP_STORED
    cho nhanh — deflate chỉ mất thời gian, chẳng tiết kiệm được bao nhiêu."""
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as z:
        if os.path.isdir(media):
            for root, _dirs, files in os.walk(media):
                for name in files:
                    full = os.path.join(root, name)
                    z.write(full, os.path.relpath(full, media))


def _validate_db_backup(path):
    """Kiểm tra file backup DB trước khi ghi đè dữ liệu đang chạy."""
    source = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('File backup DB bị hỏng')
        tables = {row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = {'products', 'transactions', 'export_orders', 'users'} - tables
        if missing:
            raise RuntimeError(f"File backup thiếu bảng: {', '.join(sorted(missing))}")
    finally:
        source.close()


def _validate_zip_paths(path):
    """Chặn zip-slip: tên file trong zip không được absolute hoặc có `..`."""
    with zipfile.ZipFile(path) as z:
        bad = [n for n in z.namelist() if n.startswith('/') or '..' in n.split('/')]
    if bad:
        raise RuntimeError(f'Zip chứa đường dẫn không an toàn: {bad[:2]}')


@bp.get('/sao-luu')
@login_required
def index():
    if g.user['role'] != 'admin':
        return redirect(url_for('dashboard.index'))

    backup_dir = _backup_dir()
    sets = {}
    other = []
    for f in sorted(os.listdir(backup_dir)):
        path = os.path.join(backup_dir, f)
        if not os.path.isfile(path):
            continue
        stat = os.stat(path)
        item = {'filename': f, 'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}
        m_db = _DB_FILE_RE.fullmatch(f)
        m_zip = _ZIP_FILE_RE.fullmatch(f)
        if m_db:
            sets.setdefault(m_db.group(1), {})['db'] = item
        elif m_zip:
            sets.setdefault(m_zip.group(1), {})['zip'] = item
        else:
            other.append(item)

    rows = []
    for ts in sorted(sets, reverse=True):
        pair = sets[ts]
        first = pair.get('db') or pair.get('zip')
        rows.append({'ts': ts, 'db': pair.get('db'), 'zip': pair.get('zip'),
                     'created': first['created']})
    return render_template('backup/index.html', sets=rows, other=other)


@bp.post('/sao-luu/tao-moi')
@login_required
def create_backup():
    if g.user['role'] != 'admin':
        return redirect(url_for('dashboard.index'))

    try:
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_dir = _backup_dir()

        # Dùng Online Backup API, không copy file. Copy file trên DB đang chạy
        # (nhất là ở chế độ WAL) có thể ra bản sao hỏng.
        db_name = f'kho.db-{stamp}'
        db_path = os.path.join(backup_dir, db_name)
        source = sqlite3.connect(_db_path())
        destination = sqlite3.connect(db_path)
        try:
            source.backup(destination)
            if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Bản sao lưu không toàn vẹn')
        finally:
            destination.close()
            source.close()
        os.chmod(db_path, 0o600)

        zip_name = f'anh-kho-{stamp}.zip'
        zip_path = os.path.join(backup_dir, zip_name)
        _zip_media(zip_path, _media_dir())
        os.chmod(zip_path, 0o600)

        flash(f'Đã sao lưu: {db_name} + {zip_name}', 'success')
    except Exception as e:
        flash(f'Lỗi sao lưu: {str(e)}', 'error')

    return redirect(url_for('backup.index'))


@bp.post('/sao-luu/khoi-phuc/<ts>')
@login_required
def restore_backup(ts):
    if g.user['role'] != 'admin':
        return redirect(url_for('dashboard.index'))

    if not _SET_TS_RE.fullmatch(ts or ''):
        abort(404)
    backup_dir = _backup_dir()
    db_backup = os.path.join(backup_dir, f'kho.db-{ts}')
    zip_backup = os.path.join(backup_dir, f'anh-kho-{ts}.zip')
    if not os.path.exists(db_backup):
        flash('Không tìm thấy bản backup DB của mốc này', 'error')
        return redirect(url_for('backup.index'))

    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    live = None
    source = None
    try:
        _validate_db_backup(db_backup)
        if os.path.exists(zip_backup):
            _validate_zip_paths(zip_backup)

        # Chụp lại DB hiện tại trước khi đè — hỏng giữa chừng còn đường lùi
        safety_db = os.path.join(backup_dir, f'kho.db.before-restore-{stamp}')
        live = sqlite3.connect(_db_path())
        safety = sqlite3.connect(safety_db)
        try:
            live.backup(safety)
        finally:
            safety.close()
        os.chmod(safety_db, 0o600)

        # Ghi thẳng vào DB đang chạy bằng Online Backup API. Không dừng
        # service: chính service này đang xử lý request, `systemctl stop`
        # sẽ giết tiến trình trước khi khôi phục xong.
        source = sqlite3.connect(f'file:{db_backup}?mode=ro', uri=True)
        source.backup(live)
        os.chmod(_db_path(), 0o600)

        if os.path.exists(zip_backup):
            # DB quay về mốc cũ thì media cũng phải đúng mốc cũ: dọn ảnh
            # hiện tại rồi giải nén bản trong zip (ảnh hiện tại đã được chụp
            # vào zip before-restore phía dưới trước khi dọn)
            media = _media_dir()
            safety_zip = os.path.join(backup_dir, f'anh-kho-before-restore-{stamp}.zip')
            _zip_media(safety_zip, media)
            os.chmod(safety_zip, 0o600)
            shutil.rmtree(os.path.join(media, 'anh_kho'), ignore_errors=True)
            with zipfile.ZipFile(zip_backup) as z:
                z.extractall(media)

        flash(f'Đã khôi phục mốc {ts} (DB + ảnh). Bản trước khi khôi phục: '
              f'kho.db.before-restore-{stamp}', 'success')
    except Exception as e:
        flash(f'Lỗi khôi phục: {str(e)}. Dữ liệu hiện tại còn nguyên ở bản '
              f'before-restore nếu có.', 'error')
    finally:
        if source is not None:
            source.close()
        if live is not None:
            live.close()

    return redirect(url_for('backup.index'))


@bp.post('/sao-luu/xoa/<ts>')
@login_required
def delete_backup(ts):
    if g.user['role'] != 'admin':
        return redirect(url_for('dashboard.index'))

    if not _SET_TS_RE.fullmatch(ts or ''):
        abort(404)
    backup_dir = _backup_dir()
    removed = []
    for name in (f'kho.db-{ts}', f'anh-kho-{ts}.zip'):
        path = os.path.join(backup_dir, name)
        if os.path.exists(path):
            os.remove(path)
            removed.append(name)
    if removed:
        flash(f'Đã xóa: {", ".join(removed)}', 'success')
    else:
        flash('Không tìm thấy backup để xóa', 'error')
    return redirect(url_for('backup.index'))


@bp.post('/sao-luu/xoa-file/<filename>')
@login_required
def delete_loose_file(filename):
    """Xóa file rời (bản before-restore, backup legacy) — chỉ xóa, không khôi phục."""
    if g.user['role'] != 'admin':
        return redirect(url_for('dashboard.index'))

    if not _OTHER_FILE_RE.fullmatch(filename or ''):
        abort(404)
    path = os.path.join(_backup_dir(), filename)
    if os.path.exists(path):
        os.remove(path)
        flash(f'Đã xóa: {filename}', 'success')
    else:
        flash('File không tồn tại', 'error')
    return redirect(url_for('backup.index'))


@bp.get('/sao-luu/tai/<filename>')
@login_required
def download_backup(filename):
    if g.user['role'] != 'admin':
        return redirect(url_for('dashboard.index'))

    if not _DOWNLOADABLE_RE.fullmatch(filename or ''):
        abort(404)
    return send_from_directory(_backup_dir(), filename, conditional=True, as_attachment=True)
