import os
import secrets
from datetime import timedelta
from flask import Flask, abort, render_template, request, session
from werkzeug.exceptions import RequestEntityTooLarge

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_mapping(
        APP_NAME=os.environ.get('KHO_WEB_APP_NAME', 'Kho hàng'),
        DATABASE=os.environ.get('KHO_WEB_DATABASE', os.path.join(DATA_DIR, 'kho.db')),
        MEDIA_DIR=os.environ.get('KHO_WEB_MEDIA_DIR', os.path.join(DATA_DIR, 'media')),
        SECRET_KEY=os.environ.get('KHO_WEB_SECRET_KEY'),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('KHO_WEB_HTTPS') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
        # 50 ảnh/lần + overhead multipart; không vượt trần 100MB/request
        # của Cloudflare free nên đặt 95MB
        MAX_CONTENT_LENGTH=95 * 1024 * 1024,
        # Quota tổng dung lượng ảnh kho (media/anh_kho: ảnh gốc + thumbnail)
        MEDIA_QUOTA_BYTES=1024 * 1024 * 1024,
        LOGIN_RATE_LIMIT=8,
        LOGIN_RATE_WINDOW_SECONDS=600,
        LOGIN_RATE_MAX_KEYS=2048,
        # Link chỉ-đọc cho chủ kho (/xem/<token>). Bỏ trống = tắt hẳn.
        SHARE_TOKEN=os.environ.get('KHO_WEB_SHARE_TOKEN'),
        SHARE_TOKEN_RATE_LIMIT=20,
        SHARE_TOKEN_RATE_WINDOW_SECONDS=3600,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config.get('SECRET_KEY'):
        raise RuntimeError('KHO_WEB_SECRET_KEY is required')

    from . import db
    db.init_app(app)
    if app.config['DATABASE'] != ':memory:' and os.path.exists(app.config['DATABASE']):
        startup_db = db.connect(app.config['DATABASE'])
        try:
            db.validate_legacy_schema(startup_db)
        finally:
            startup_db.close()
    from .auth import LoginRateLimiter, bp as auth_bp
    app.extensions['login_rate_limiter'] = LoginRateLimiter(
        app.config['LOGIN_RATE_LIMIT'], app.config['LOGIN_RATE_WINDOW_SECONDS'],
        app.config['LOGIN_RATE_MAX_KEYS'])
    from . import share
    app.extensions['share_token_limiter'] = share.TokenAttemptLimiter(
        app.config['SHARE_TOKEN_RATE_LIMIT'],
        app.config['SHARE_TOKEN_RATE_WINDOW_SECONDS'])
    from .inventory import bp as inventory_bp
    from .exports import bp as exports_bp
    from .dashboard import bp as dashboard_bp
    from . import imports, photos, products, print, backup
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(exports_bp)
    # app.register_blueprint(imports.bp)  # Disabled - nhập kho tạm thời disable
    app.register_blueprint(products.bp)
    app.register_blueprint(photos.bp)
    app.register_blueprint(print.bp)
    app.register_blueprint(backup.bp)
    app.register_blueprint(share.bp)

    @app.get('/robots.txt')
    def robots():
        # Kho nội bộ: không cho máy tìm kiếm thu thập bất kỳ đường dẫn nào.
        return app.response_class('User-agent: *\nDisallow: /\n', mimetype='text/plain')

    @app.before_request
    def csrf_protect():
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            # Body vượt MAX_CONTENT_LENGTH: chặn ngay bằng 413 thay vì để
            # parse form âm thầm trả rỗng rồi báo CSRF 400 khó hiểu.
            if request.content_length and request.content_length > app.config['MAX_CONTENT_LENGTH']:
                abort(413)
            try:
                supplied = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            except RequestEntityTooLarge:
                abort(413)
            if not supplied or not secrets.compare_digest(supplied, session.get('_csrf_token', '')):
                abort(400, description='CSRF token không hợp lệ')

    @app.context_processor
    def csrf_context():
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_urlsafe(32)
        return {'csrf_token': session['_csrf_token']}

    @app.template_filter('number_format')
    def number_format(value):
        if value is None:
            return '0'
        return '{:,.0f}'.format(value)

    @app.template_filter('vn_time')
    def vn_time(value, fmt='%d/%m/%Y %H:%M'):
        from .tz import format_vn
        return format_vn(value, fmt)

    @app.context_processor
    def utility_functions():
        return dict(min=min, max=max, app_name=app.config['APP_NAME'])

    # Không để người dùng rơi vào trang lỗi trắng của Flask giữa lúc làm phiếu:
    # nói rõ chuyện gì xảy ra, cần làm gì, và có đường quay lại.
    ERROR_COPY = {
        400: ('Phiếu chưa hợp lệ', 'Kiểm tra lại số lượng và mặt hàng rồi thử lại. Phiếu đang soạn vẫn còn.'),
        403: ('Không có quyền', 'Việc này chỉ quản trị viên làm được. Liên hệ quản trị nếu bạn cần thao tác.'),
        404: ('Không tìm thấy', 'Đường dẫn hoặc phiếu này không tồn tại. Có thể phiếu đã bị đổi mã.'),
        409: ('Phiếu đã được ghi', 'Yêu cầu này đã xử lý trước đó. Mở lịch sử để xem phiếu vừa tạo.'),
        413: ('Dữ liệu quá lớn', 'Bớt số mặt hàng trong phiếu rồi gửi lại.'),
        503: ('Hệ thống đang bận', 'Cơ sở dữ liệu đang có việc ghi khác. Chờ vài giây rồi bấm lại.'),
    }

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(503)
    def handle_http_error(error):
        title, hint = ERROR_COPY.get(error.code, ('Đã xảy ra lỗi', 'Thử lại hoặc liên hệ quản trị.'))
        if error.code == 413 and request.path.startswith('/anh-kho'):
            title, hint = 'Ảnh gửi lên quá lớn', 'Mỗi ảnh tối đa 95MB, mỗi lần tối đa 50 ảnh và tổng dung lượng khoảng 90MB. Bớt bớt ảnh hoặc nén ảnh rồi gửi lại.'
        detail = getattr(error, 'description', '') or title
        return render_template('error.html', title=title, detail=detail, hint=hint), error.code

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        # img-src cần blob: cho ảnh xem trước khi up (URL.createObjectURL)
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; form-action 'self'; frame-ancestors 'none'"
        return response
    return app
