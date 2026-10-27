import re
import sqlite3
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from .auth import login_required
from .db import get_db

bp = Blueprint('products', __name__)


class InvalidField(ValueError):
    pass


def _number(field, label, default, integer=False):
    """Đọc một ô số từ form. Form gửi chuỗi nên phải tự kiểm tra —
    SQLite có kiểu lỏng, chuỗi 'abc' sẽ nằm luôn trong cột số và làm sai mọi
    phép tính về sau."""
    raw = (request.form.get(field) or '').strip().replace(',', '')
    if not raw:
        return default
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        raise InvalidField(f'{label} phải là số') from None
    if value < 0:
        raise InvalidField(f'{label} không được âm')
    return value


def _next_sku(db, name):
    """Sinh SKU theo số lớn nhất đang dùng, không theo số lượng bản ghi —
    đếm bản ghi sẽ trùng SKU ngay sau khi có sản phẩm bị xóa."""
    prefix = ''.join(word[0] for word in name.split()[:3]).upper() or 'SP'
    suffixes = [0]
    for row in db.execute('SELECT sku FROM products WHERE sku LIKE ?', (f'{prefix}%',)):
        match = re.fullmatch(re.escape(prefix) + r'(\d+)', row['sku'] or '')
        if match:
            suffixes.append(int(match.group(1)))
    return f'{prefix}{max(suffixes) + 1:04d}'


@bp.get('/san-pham')
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
    categories = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    suppliers = db.execute('SELECT * FROM suppliers ORDER BY name').fetchall()
    return render_template('products/index.html', products=products, categories=categories, suppliers=suppliers)


@bp.post('/san-pham/tao-moi')
@login_required
def create():
    if g.user['role'] != 'admin':
        abort(403)

    name = request.form.get('name', '').strip()
    sku = request.form.get('sku', '').strip()
    category_id = request.form.get('category_id')
    supplier_id = request.form.get('supplier_id')
    unit = request.form.get('unit', 'cái').strip() or 'cái'
    location = request.form.get('location', '').strip()
    note = request.form.get('note', '').strip()

    if not name:
        flash('Vui lòng nhập tên sản phẩm', 'error')
        return redirect(url_for('products.index'))
    try:
        cost_price = _number('cost_price', 'Giá vốn', 0)
        sell_price = _number('sell_price', 'Giá bán', 0)
        quantity = _number('quantity', 'Số lượng', 0, integer=True)
        min_quantity = _number('min_quantity', 'Số lượng tối thiểu', 10, integer=True)
    except InvalidField as exc:
        flash(str(exc), 'error')
        return redirect(url_for('products.index'))

    db = get_db()
    try:
        db.execute('BEGIN IMMEDIATE')

        if not sku:
            sku = _next_sku(db, name)

        db.execute('''
            INSERT INTO products (sku, name, category_id, supplier_id, unit, cost_price, sell_price,
                                  quantity, min_quantity, location, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (sku, name, category_id or None, supplier_id or None, unit, cost_price, sell_price,
              quantity, min_quantity, location or None, note or None))
        db.commit()
        flash(f'Đã tạo sản phẩm: {name} ({sku})', 'success')
    except sqlite3.IntegrityError:
        flash(f'SKU đã tồn tại: {sku}', 'error')
        db.rollback()

    return redirect(url_for('products.index'))


@bp.post('/san-pham/<int:id>/cap-nhat')
@login_required
def update(id):
    if g.user['role'] != 'admin':
        abort(403)

    name = request.form.get('name', '').strip()
    sku = request.form.get('sku', '').strip()
    category_id = request.form.get('category_id')
    supplier_id = request.form.get('supplier_id')
    unit = request.form.get('unit', 'cái').strip() or 'cái'
    location = request.form.get('location', '').strip()
    note = request.form.get('note', '').strip()

    if not name:
        flash('Vui lòng nhập tên sản phẩm', 'error')
        return redirect(url_for('products.index'))
    if not sku:
        flash('Vui lòng nhập SKU', 'error')
        return redirect(url_for('products.index'))
    try:
        cost_price = _number('cost_price', 'Giá vốn', 0)
        sell_price = _number('sell_price', 'Giá bán', 0)
        min_quantity = _number('min_quantity', 'Số lượng tối thiểu', 10, integer=True)
    except InvalidField as exc:
        flash(str(exc), 'error')
        return redirect(url_for('products.index'))

    db = get_db()
    try:
        db.execute('''
            UPDATE products
            SET name=?, sku=?, category_id=?, supplier_id=?, unit=?, cost_price=?, sell_price=?,
                min_quantity=?, location=?, note=?
            WHERE id=? AND deleted_at IS NULL
        ''', (name, sku, category_id or None, supplier_id or None, unit, cost_price, sell_price,
              min_quantity, location or None, note or None, id))
        db.commit()
        flash('Đã cập nhật sản phẩm', 'success')
    except sqlite3.IntegrityError:
        flash('SKU đã tồn tại', 'error')
        db.rollback()

    return redirect(url_for('products.index'))


@bp.post('/san-pham/<int:id>/xoa')
@login_required
def delete(id):
    if g.user['role'] != 'admin':
        abort(403)

    db = get_db()
    try:
        db.execute('BEGIN IMMEDIATE')

        # Soft delete - chỉ đánh dấu deleted_at (UTC, giống mọi mốc thời gian khác)
        db.execute("UPDATE products SET deleted_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?", (id,))
        db.commit()
        flash('Đã xóa sản phẩm (vào thùng rác)', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Lỗi khi xóa: {str(e)}', 'error')

    return redirect(url_for('products.index'))


@bp.post('/san-pham/<int:id>/khoi-phuc')
@login_required
def restore(id):
    if g.user['role'] != 'admin':
        abort(403)

    db = get_db()
    try:
        db.execute('UPDATE products SET deleted_at=NULL WHERE id=?', (id,))
        db.commit()
        flash('Đã khôi phục sản phẩm', 'success')
    except Exception as e:
        flash(f'Lỗi khi khôi phục: {str(e)}', 'error')

    return redirect(url_for('products.trash'))


@bp.get('/thung-rac')
@login_required
def trash():
    if g.user['role'] != 'admin':
        abort(403)

    db = get_db()
    products = db.execute('''
        SELECT p.*, c.name category_name
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE p.deleted_at IS NOT NULL
        ORDER BY p.deleted_at DESC
    ''').fetchall()
    return render_template('products/trash.html', products=products)


@bp.post('/san-pham/<int:id>/xoa-vinh-vien')
@login_required
def permanent_delete(id):
    if g.user['role'] != 'admin':
        abort(403)

    db = get_db()
    try:
        db.execute('BEGIN IMMEDIATE')

        # Chỉ xóa vĩnh viễn được thứ đã nằm trong thùng rác
        product = db.execute('SELECT deleted_at FROM products WHERE id=?', (id,)).fetchone()
        if product is None:
            db.rollback()
            flash('Không tìm thấy sản phẩm', 'error')
            return redirect(url_for('products.trash'))
        if product['deleted_at'] is None:
            db.rollback()
            flash('Sản phẩm chưa ở trong thùng rác', 'error')
            return redirect(url_for('products.trash'))

        has_tx = db.execute('SELECT COUNT(*) as cnt FROM transactions WHERE product_id=?', (id,)).fetchone()['cnt']
        if has_tx > 0:
            db.rollback()
            flash('Không thể xóa vĩnh viễn sản phẩm đã có giao dịch', 'error')
            return redirect(url_for('products.trash'))

        db.execute('DELETE FROM products WHERE id=?', (id,))
        db.commit()
        flash('Đã xóa vĩnh viễn sản phẩm', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Lỗi khi xóa: {str(e)}', 'error')

    return redirect(url_for('products.trash'))
