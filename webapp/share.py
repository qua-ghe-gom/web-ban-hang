"""Link chỉ-đọc cho chủ kho: /xem/<token>/…

Chủ kho chỉ cần mở link là xem được gallery ảnh kho (theo ngày, có sản phẩm /
số lượng / ghi chú), KHÔNG cần đăng nhập và KHÔNG sửa được gì: blueprint này
chỉ đăng ký route GET, mọi route ghi dữ liệu vẫn nằm sau @login_required.

Token nằm ở biến môi trường KHO_WEB_SHARE_TOKEN. Đổi token = link cũ chết ngay.
Sai token trả 404 (không phải 403) để không xác nhận "đường dẫn có tồn tại".
"""
import re
import secrets
from collections import OrderedDict
from threading import Lock
from time import monotonic

from flask import (Blueprint, abort, current_app, render_template, request,
                   send_from_directory)

from .db import get_db
from .photos import day_context, gallery_context

bp = Blueprint('share', __name__)

# Ảnh kho nằm dưới media/anh_kho/; chặn mọi đường dẫn khác trong MEDIA_DIR.
_MEDIA_PREFIX = 'anh_kho/'


class TokenAttemptLimiter:
    """Đếm số lần sai token theo IP (chống dò link), an toàn với nhiều thread."""

    def __init__(self, limit=20, window_seconds=3600, max_keys=2048):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._entries = OrderedDict()
        self._lock = Lock()

    def _prune(self, now):
        for key in [k for k, (started, _) in self._entries.items()
                    if now - started >= self.window_seconds]:
            self._entries.pop(key, None)

    def is_limited(self, ip):
        now = monotonic()
        with self._lock:
            self._prune(now)
            return self._entries.get((ip or '')[:64], (now, 0))[1] >= self.limit

    def record_failure(self, ip):
        now = monotonic()
        key = (ip or '')[:64]
        with self._lock:
            self._prune(now)
            started, count = self._entries.pop(key, (now, 0))
            self._entries[key] = (started, count + 1)
            while len(self._entries) > self.max_keys:
                self._entries.popitem(last=False)

    @property
    def key_count(self):
        with self._lock:
            return len(self._entries)


def _token_ok(token):
    expected = current_app.config.get('SHARE_TOKEN') or ''
    if not expected or not token:
        return False
    return secrets.compare_digest(str(token), expected)


@bp.before_request
def guard():
    token = (request.view_args or {}).get('token', '')
    limiter = current_app.extensions.get('share_token_limiter')
    ip = request.remote_addr or ''
    if limiter is not None and limiter.is_limited(ip):
        abort(429)
    if not _token_ok(token):
        if limiter is not None:
            limiter.record_failure(ip)
        current_app.logger.warning('[Share] Token không hợp lệ từ %s — %s', ip, request.path)
        abort(404)


@bp.after_request
def noindex(response):
    # Link riêng cho chủ kho: đừng để máy tìm kiếm index, đừng cache ở proxy.
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    response.headers['Cache-Control'] = 'private, max-age=300'
    return response


@bp.get('/xem/<token>')
def index(token):
    ctx = gallery_context(get_db(), request.args.get('thang'), request.args.get('page'))
    return render_template('share/index.html', token=token, **ctx)


@bp.get('/xem/<token>/ngay/<ngay>')
def day_view(token, ngay):
    ctx = day_context(get_db(), ngay)
    if ctx is None:
        abort(404)
    return render_template('share/day.html', token=token, **ctx)


@bp.get('/xem/<token>/anh/<int:photo_id>')
def detail(token, photo_id):
    db = get_db()
    photo = db.execute('''
        SELECT p.*, pr.name product_name
        FROM photos p LEFT JOIN products pr ON pr.id = p.product_id
        WHERE p.id = ?
    ''', (photo_id,)).fetchone()
    if photo is None:
        abort(404)
    prev_id = db.execute('SELECT id FROM photos WHERE taken_on = ? AND id < ? '
                         'ORDER BY id DESC LIMIT 1',
                         (photo['taken_on'], photo['id'])).fetchone()
    next_id = db.execute('SELECT id FROM photos WHERE taken_on = ? AND id > ? '
                         'ORDER BY id ASC LIMIT 1',
                         (photo['taken_on'], photo['id'])).fetchone()
    pos = db.execute('SELECT COUNT(*) pos, '
                     '(SELECT COUNT(*) FROM photos WHERE taken_on = :d) cnt '
                     'FROM photos WHERE taken_on = :d AND id <= :id',
                     {'d': photo['taken_on'], 'id': photo['id']}).fetchone()
    return render_template('share/detail.html', token=token, photo=photo,
                           prev_id=prev_id['id'] if prev_id else None,
                           next_id=next_id['id'] if next_id else None,
                           pos=pos['pos'], cnt=pos['cnt'])


@bp.get('/xem/<token>/media/<path:relpath>')
def media(token, relpath):
    if not relpath.startswith(_MEDIA_PREFIX):
        abort(404)
    # send_from_directory tự chặn path traversal (../) ra ngoài MEDIA_DIR
    return send_from_directory(current_app.config['MEDIA_DIR'], relpath, conditional=True)
