import json
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash
from .auth import login_required
from .db import get_db

bp = Blueprint('imports', __name__)


@bp.get('/nhap-kho')
@login_required
def index():
    db = get_db()
    products = db.execute('''
        SELECT p.*, c.name category_name
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.deleted_at IS NULL
        ORDER BY p.name
    ''').fetchall()
    suppliers = db.execute('SELECT * FROM suppliers ORDER BY name').fetchall()
    return render_template('imports/index.html', products=products, suppliers=suppliers)


@bp.post('/nhap-kho/xac-nhan')
@login_required
def confirm_import():
    """Xử lý nhập kho."""
    try:
        items = json.loads(request.form.get('items_json', '[]'))
    except (json.JSONDecodeError, TypeError):
        flash('Dữ liệu không hợp lệ', 'error')
        return redirect(url_for('imports.index'))

    if not items:
        flash('Chưa chọn sản phẩm nào', 'error')
        return redirect(url_for('imports.index'))

    supplier_id = request.form.get('supplier_id')
    note = request.form.get('note', '').strip()[:500]

    db = get_db()
    try:
        db.execute('BEGIN IMMEDIATE')

        import_code = f"NK-{__import__('datetime').datetime.now().strftime('%Y%m%d-%H%M')}"
        total_value = 0

        for item in items:
            product_id = item.get('product_id')
            quantity = item.get('quantity', 0)
            unit_price = item.get('unit_price', 0)

            if not product_id or quantity <= 0:
                continue

            # Lấy thông tin sản phẩm
            product = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
            if not product:
                continue

            # Tạo transaction nhập kho
            line_total = quantity * unit_price
            total_value += line_total

            db.execute('''
                INSERT INTO transactions (product_id, type, quantity, unit_price, total_amount, note, created_at)
                VALUES (?, 'import', ?, ?, ?, ?, ?)
            ''', (product_id, quantity, unit_price, line_total, f"{import_code} | {note}", __import__('datetime').datetime.now().isoformat()))

        db.commit()
        flash(f'Đã nhập kho thành công. Mã: {import_code}', 'success')
        return redirect(url_for('imports.index'))

    except Exception as e:
        db.rollback()
        flash(f'Lỗi khi nhập kho: {str(e)}', 'error')
        return redirect(url_for('imports.index'))
