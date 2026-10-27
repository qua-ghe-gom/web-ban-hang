"""Tab Ảnh kho: up ảnh bán hàng, xem gallery theo tháng, sửa, xóa.

Quyền: mọi user đăng nhập đều thao tác được — hệ thống hiện chỉ có tài khoản
admin; khi có staff riêng mới cân nhắc tách quyền.
"""
import os
import re
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, send_from_directory, url_for)

from .auth import login_required
from .db import get_db
from .services.photo_storage import (NotAnImage, delete_stored_files, store_image,
                                     media_usage_bytes, stored_file_bytes)
from .tz import VN_TZ

bp = Blueprint('photos', __name__)

DAYS_PER_PAGE = 30
MAX_FILES_PER_UPLOAD = 50
_MONTH_RE = re.compile(r'\d{4}-\d{2}\Z')
_DAY_RE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')


class InvalidField(ValueError):
    pass


def gallery_context(db, month_raw, page_raw):
    """Dữ liệu gallery theo tháng — dùng chung cho trang quản trị và link chỉ-đọc.

    Trả dict để render thẳng vào template: days, covers, months, month, page,
    pages, total, sold.
    """
    month = (month_raw or '').strip()
    if not _MONTH_RE.fullmatch(month or ''):
        month = ''
    where, params = ('WHERE strftime("%Y-%m", p.taken_on) = ?', [month]) if month else ('', [])
    try:
        page = int(page_raw if page_raw not in (None, '') else 1)
    except (TypeError, ValueError):
        page = 1

    totals = db.execute(f'SELECT COUNT(*) cnt, COALESCE(SUM(quantity),0) sold '
                        f'FROM photos p {where}', params).fetchone()
    day_total = db.execute(f'SELECT COUNT(DISTINCT p.taken_on) FROM photos p {where}',
                           params).fetchone()[0]
    pages = max(1, -(-day_total // DAYS_PER_PAGE))
    page = min(max(1, page), pages)
    # Gom theo ngày: 1 ngày = 1 card, cover là ảnh up ĐẦU TIÊN trong ngày (MIN id)
    days = db.execute(f'''
        SELECT p.taken_on, COUNT(*) cnt, COALESCE(SUM(p.quantity),0) sold, MIN(p.id) cover_id
        FROM photos p {where}
        GROUP BY p.taken_on
        ORDER BY p.taken_on DESC
        LIMIT ? OFFSET ?
    ''', [*params, DAYS_PER_PAGE, (page - 1) * DAYS_PER_PAGE]).fetchall()
    covers = {}
    if days:
        ids = [d['cover_id'] for d in days]
        marks = ','.join('?' * len(ids))
        for row in db.execute(f'SELECT id, thumb_filename, caption FROM photos WHERE id IN ({marks})', ids):
            covers[row['id']] = row
    months = [row[0] for row in db.execute(
        'SELECT DISTINCT strftime("%Y-%m", taken_on) m FROM photos ORDER BY m DESC')]
    return dict(days=days, covers=covers, months=months, month=month, page=page,
                pages=pages, total=totals['cnt'], sold=totals['sold'])


def day_context(db, ngay):
    """1 ngày = danh sách ảnh + số ảnh + tổng đã bán + ngày trước/sau.

    Trả None nếu ngày sai định dạng hoặc không có ảnh nào.
    """
    if not _DAY_RE.fullmatch(ngay or ''):
        return None
    photos = db.execute('''
        SELECT p.id, p.thumb_filename, p.caption, p.quantity, pr.name product_name
        FROM photos p LEFT JOIN products pr ON pr.id = p.product_id
        WHERE p.taken_on = ?
        ORDER BY p.id ASC
    ''', (ngay,)).fetchall()
    if not photos:
        return None
    agg = db.execute('SELECT COUNT(*) cnt, COALESCE(SUM(quantity),0) sold '
                     'FROM photos WHERE taken_on = ?', (ngay,)).fetchone()
    prev_day = db.execute('SELECT MAX(taken_on) d FROM photos WHERE taken_on < ?', (ngay,)).fetchone()[0]
    next_day = db.execute('SELECT MIN(taken_on) d FROM photos WHERE taken_on > ?', (ngay,)).fetchone()[0]
    return dict(ngay=ngay, photos=photos, cnt=agg['cnt'], sold=agg['sold'],
                prev_day=prev_day, next_day=next_day)


@bp.get('/anh-kho')
@login_required
def index():
    ctx = gallery_context(get_db(), request.args.get('thang'), request.args.get('page'))
    return render_template('photos/index.html', **ctx)


@bp.get('/anh-kho/ngay/<ngay>')
@login_required
def day_view(ngay):
    ctx = day_context(get_db(), ngay)
    if ctx is None:
        abort(404)
    return render_template('photos/day.html', **ctx)


@bp.get('/media/<path:relpath>')
@login_required
def media(relpath):
    # send_from_directory tự chặn path traversal (../) ngoài MEDIA_DIR
    return send_from_directory(current_app.config['MEDIA_DIR'], relpath, conditional=True)


def _parse_taken_on(raw):
    """Ngày nghiệp vụ dạng dd/mm/yy. Bỏ trống = hôm nay theo giờ Việt Nam (đúng ngày làm việc của kho)."""
    raw = (raw or '').strip()
    if not raw:
        return datetime.now(VN_TZ).date()
    try:
        return datetime.strptime(raw, '%d/%m/%y').date()
    except ValueError:
        raise InvalidField('Ngày không hợp lệ (cần dạng dd/mm/yy)') from None


def _quantity():
    raw = (request.form.get('quantity') or '').strip().replace(',', '')
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        raise InvalidField('Số lượng phải là số nguyên') from None
    if not 1 <= value <= 1_000_000:
        raise InvalidField('Số lượng phải từ 1 đến 1.000.000')
    return value


def _product_id(db):
    raw = (request.form.get('product_id') or '').strip()
    if not raw:
        return None
    try:
        pid = int(raw)
    except ValueError:
        raise InvalidField('Sản phẩm không hợp lệ') from None
    if db.execute('SELECT 1 FROM products WHERE id=? AND deleted_at IS NULL', (pid,)).fetchone() is None:
        raise InvalidField('Sản phẩm không tồn tại hoặc đã bị xóa')
    return pid


def _form_metadata(db):
    """Đọc các ô dùng chung cho mọi ảnh trong lần gửi. raise InvalidField."""
    return {
        'taken_on': _parse_taken_on(request.form.get('taken_on')),
        'product_id': _product_id(db),
        'quantity': _quantity(),
        'caption': (request.form.get('caption') or '').strip()[:500] or None,
    }


@bp.get('/anh-kho/up')
@login_required
def upload_form():
    products = get_db().execute(
        'SELECT id, name FROM products WHERE deleted_at IS NULL ORDER BY name').fetchall()
    today = datetime.now(VN_TZ).strftime('%d/%m/%y')
    return render_template('photos/upload.html', products=products, today=today)


@bp.post('/anh-kho/up')
@login_required
def upload():
    files = [f for f in request.files.getlist('images') if f and f.filename]
    if not files:
        flash('Vui lòng chọn ít nhất một ảnh', 'error')
        return redirect(url_for('photos.upload_form'))
    if len(files) > MAX_FILES_PER_UPLOAD:
        flash(f'Tối đa {MAX_FILES_PER_UPLOAD} ảnh mỗi lần gửi', 'error')
        return redirect(url_for('photos.upload_form'))

    db = get_db()
    try:
        meta = _form_metadata(db)
    except InvalidField as exc:
        flash(str(exc), 'error')
        return redirect(url_for('photos.upload_form'))

    media_dir = current_app.config['MEDIA_DIR']
    quota = current_app.config.get('MEDIA_QUOTA_BYTES', 1024 ** 3)  # 1GB
    stored = []
    failed = 0
    quota_hit = False
    try:
        db.execute('BEGIN IMMEDIATE')
        # Quota chặn cứng 1GB tính trên dung lượng file ĐÃ LƯU (gốc + thumb).
        # Kho đã đầy thì dừng luôn, không đọc ảnh vô ích; còn chưa đầy thì
        # lưu được bao nhiêu nhận bấy nhiêu, phần vượt quota bỏ qua.
        usage = media_usage_bytes(media_dir)
        added = 0
        quota_hit = usage >= quota
        remaining = [] if quota_hit else files
        for f in remaining:
            try:
                saved = store_image(media_dir, f, meta['taken_on'])
            except NotAnImage:
                failed += 1
                continue
            sizes = stored_file_bytes(media_dir, saved)
            if usage + added + sizes > quota:
                # Ảnh này đẩy kho vượt 1GB — bỏ nó, và bỏ toàn bộ phần còn lại
                delete_stored_files(media_dir, saved.filename, saved.thumb_filename)
                quota_hit = True
                break
            db.execute('''
                INSERT INTO photos (filename, thumb_filename, taken_on, caption, product_id, quantity, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (saved.filename, saved.thumb_filename, meta['taken_on'].isoformat(),
                  meta['caption'], meta['product_id'], meta['quantity'], g.user['id']))
            added += sizes
            stored.append(saved)
        db.commit()
    except Exception:
        # DB rollback thì file đã ghi cũng phải đi theo, không để rác trên disk
        db.rollback()
        delete_stored_files(media_dir, *[p.filename for p in stored],
                            *[p.thumb_filename for p in stored])
        flash('Lỗi khi lưu ảnh, thử lại', 'error')
        return redirect(url_for('photos.upload_form'))

    if stored and quota_hit:
        flash(f'Đã lưu {len(stored)} ảnh — kho ảnh đạt giới hạn 1GB, phần còn lại bỏ qua', 'error')
    elif quota_hit:
        flash('Kho ảnh đã đạt giới hạn tổng dung lượng 1GB — xóa ảnh cũ rồi gửi lại', 'error')
    elif stored and failed:
        flash(f'Đã lưu {len(stored)} ảnh, bỏ qua {failed} ảnh không đọc được', 'success')
    elif stored:
        flash(f'Đã lưu {len(stored)} ảnh', 'success')
    else:
        flash('Không có ảnh nào hợp lệ — chỉ nhận JPEG/PNG/HEIC thông thường', 'error')
    return redirect(url_for('photos.index'))


def _get_photo(db, photo_id):
    return db.execute('''
        SELECT p.*, pr.name product_name, u.display_name created_by_name
        FROM photos p
        LEFT JOIN products pr ON pr.id = p.product_id
        LEFT JOIN users u ON u.id = p.created_by
        WHERE p.id = ?
    ''', (photo_id,)).fetchone()


def _neighbors(db, photo):
    """Ảnh trước/sau trong CÙNG NGÀY, theo đúng thứ tự up (id)."""
    prev_row = db.execute('SELECT id FROM photos WHERE taken_on = ? AND id < ? '
                          'ORDER BY id DESC LIMIT 1',
                          (photo['taken_on'], photo['id'])).fetchone()
    next_row = db.execute('SELECT id FROM photos WHERE taken_on = ? AND id > ? '
                          'ORDER BY id ASC LIMIT 1',
                          (photo['taken_on'], photo['id'])).fetchone()
    return (prev_row['id'] if prev_row else None, next_row['id'] if next_row else None)


@bp.get('/anh-kho/<int:photo_id>')
@login_required
def detail(photo_id):
    db = get_db()
    photo = _get_photo(db, photo_id)
    if photo is None:
        abort(404)
    prev_id, next_id = _neighbors(db, photo)
    pos = db.execute('SELECT COUNT(*) pos, '
                     '(SELECT COUNT(*) FROM photos WHERE taken_on = :d) cnt '
                     'FROM photos WHERE taken_on = :d AND id <= :id',
                     {'d': photo['taken_on'], 'id': photo['id']}).fetchone()
    return render_template('photos/detail.html', photo=photo,
                           prev_id=prev_id, next_id=next_id,
                           pos=pos['pos'], cnt=pos['cnt'])


@bp.get('/anh-kho/<int:photo_id>/sua')
@login_required
def edit_form(photo_id):
    db = get_db()
    photo = _get_photo(db, photo_id)
    if photo is None:
        abort(404)
    products = db.execute('SELECT id, name FROM products WHERE deleted_at IS NULL ORDER BY name').fetchall()
    return render_template('photos/edit.html', photo=photo, products=products)


@bp.post('/anh-kho/<int:photo_id>/sua')
@login_required
def edit(photo_id):
    db = get_db()
    photo = _get_photo(db, photo_id)
    if photo is None:
        abort(404)
    try:
        meta = _form_metadata(db)
    except InvalidField as exc:
        flash(str(exc), 'error')
        return redirect(url_for('photos.edit_form', photo_id=photo_id))
    db.execute('''UPDATE photos SET taken_on=?, caption=?, product_id=?, quantity=?,
                  updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?''',
               (meta['taken_on'].isoformat(), meta['caption'], meta['product_id'],
                meta['quantity'], photo_id))
    db.commit()
    flash('Đã cập nhật ảnh', 'success')
    return redirect(url_for('photos.detail', photo_id=photo_id))


@bp.post('/anh-kho/<int:photo_id>/xoa')
@login_required
def delete(photo_id):
    db = get_db()
    photo = db.execute('SELECT * FROM photos WHERE id=?', (photo_id,)).fetchone()
    if photo is None:
        abort(404)
    try:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM photos WHERE id=?', (photo_id,))
        db.commit()
    except Exception:
        db.rollback()
        flash('Lỗi khi xóa ảnh', 'error')
        return redirect(url_for('photos.index'))
    # DB xong mới tới file; file thiếu không sao (idempotent)
    delete_stored_files(current_app.config['MEDIA_DIR'], photo['filename'], photo['thumb_filename'])
    flash('Đã xóa ảnh', 'success')
    return redirect(url_for('photos.index'))
