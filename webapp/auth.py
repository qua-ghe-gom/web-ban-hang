from datetime import datetime, timedelta, timezone
from functools import wraps
from collections import OrderedDict
from threading import Lock
from time import monotonic
from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from .db import get_db

bp = Blueprint('auth', __name__)
DUMMY_PASSWORD_HASH = 'scrypt:32768:8:1$I8m1YUpSjx8R6SEt$170b36ac3fa0d271743d89f965c49f6a9b8ade51a66252ee89929635ed0c095ee7ee5edeaa91db09d3b25a2d59ea33e5a812c40e9f120fb65d9ef8791a032d5b'
# Sai 5 lần là khoá 30 phút; đủ dài để dò mật khẩu hàng loạt không có lợi.
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 30


class LoginRateLimiter:
    """Small in-process limiter shared safely by Waitress worker threads."""
    def __init__(self, limit=10, window_seconds=300, max_keys=2048):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._entries = OrderedDict()
        self._lock = Lock()

    def _prune(self, now):
        expired = [key for key, (started, _) in self._entries.items()
                   if now - started >= self.window_seconds]
        for key in expired:
            self._entries.pop(key, None)

    def _keys(self, ip, account):
        bounded_ip = (ip or '')[:64]
        bounded_account = (account or '')[:128].casefold()
        # 2 lớp: cặp IP+tài khoản (một máy dò một tài khoản) và tài khoản
        # (nhiều IP cùng dò một tài khoản). KHÔNG có khoá chỉ-theo-IP vì web
        # chạy sau proxy/Cloudflare dùng chung IP — một kẻ phá hoại sẽ khoá
        # luôn mọi người dùng thật.
        return (('ip_account', bounded_ip, bounded_account), ('account', bounded_account))

    def is_limited(self, ip, account):
        now = monotonic()
        with self._lock:
            self._prune(now)
            return any(self._entries.get(key, (now, 0))[1] >= self.limit
                       for key in self._keys(ip, account))

    def record_failure(self, ip, account):
        now = monotonic()
        with self._lock:
            self._prune(now)
            for key in self._keys(ip, account):
                started, count = self._entries.pop(key, (now, 0))
                self._entries[key] = (started, count + 1)
            while len(self._entries) > self.max_keys:
                self._entries.popitem(last=False)

    @property
    def key_count(self):
        with self._lock:
            return len(self._entries)

@bp.before_app_request
def load_user():
    user_id = session.get('user_id')
    expires = session.get('auth_expires_at')
    if user_id:
        try:
            expired = not expires or datetime.fromisoformat(expires) <= datetime.now(timezone.utc)
        except (TypeError, ValueError):
            expired = True
        if expired:
            session.clear()
            user_id = None
    g.user = get_db().execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone() if user_id else None
    if user_id and (g.user is None or not g.user['is_active']):
        session.clear()
        g.user = None


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login', next=request.path))
        return view(**kwargs)
    return wrapped

@bp.route('/login', methods=('GET','POST'))
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
        now = datetime.now(timezone.utc)
        limiter = current_app.extensions['login_rate_limiter']
        rate_limited = limiter.is_limited(request.remote_addr, username)
        locked = False
        if user and user['locked_until']:
            try:
                locked = datetime.fromisoformat(user['locked_until']) > now
            except ValueError:
                locked = True
            if not locked:
                # Hết hạn khóa thì xóa luôn bộ đếm, nếu không thì count vẫn >=5
                # và mỗi lần gõ sai tiếp theo lại khóa thêm 15 phút mãi mãi.
                db.execute('UPDATE users SET failed_login_count=0,locked_until=NULL WHERE id=?', (user['id'],))
                db.commit()
                user = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        password_valid = check_password_hash(user['password_hash'] if user else DUMMY_PASSWORD_HASH, password)
        valid = bool(user and user['is_active'] and not locked and not rate_limited and password_valid)
        if valid:
            db.execute('UPDATE users SET failed_login_count=0,locked_until=NULL,last_login_at=? WHERE id=?', (now.isoformat(),user['id']))
            db.commit()
            csrf = session.get('_csrf_token')
            session.clear()
            session['_csrf_token'] = csrf
            session['user_id'] = user['id']
            session.permanent = True
            session['auth_expires_at'] = (now + current_app.permanent_session_lifetime).isoformat()
            return redirect(url_for('inventory.index'))
        if user and not locked:
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute('''UPDATE users SET failed_login_count=failed_login_count+1,
                    locked_until=CASE WHEN failed_login_count+1>=? THEN ? ELSE locked_until END
                    WHERE id=?''', (MAX_FAILED_LOGINS,
                                    (now + timedelta(minutes=LOCK_MINUTES)).isoformat(),
                                    user['id']))
                db.commit()
            except Exception:
                db.rollback()
                raise
        limiter.record_failure(request.remote_addr, username)
        # Ghi log để soi lại khi bị dò mật khẩu (journalctl --user -u kho-web).
        current_app.logger.warning('[Login] Sai mật khẩu: user=%r ip=%s agent=%r',
                                   username[:64], request.remote_addr,
                                   (request.headers.get('User-Agent') or '')[:80])
        flash('Tên đăng nhập hoặc mật khẩu không đúng', 'error')
        if rate_limited:
            return render_template('auth/login.html'), 429
    return render_template('auth/login.html')

@bp.post('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
