from flask import Blueprint, g, redirect, render_template, url_for
from .auth import login_required
from .db import get_db
from .tz import VN_OFFSET

bp = Blueprint('dashboard', __name__)


@bp.get('/dashboard')
@login_required
def index():
    db = get_db()

    # KPI Cards. Sản phẩm trong thùng rác (deleted_at) không được tính vào số liệu,
    # và phiếu đã hủy (status='cancelled') không tính là phiếu xuất.
    stats = {}

    # Tổng sản phẩm
    stats['total_products'] = db.execute(
        'SELECT COUNT(*) as cnt FROM products WHERE deleted_at IS NULL').fetchone()['cnt']

    # Tổng tồn kho
    stats['total_quantity'] = db.execute(
        'SELECT SUM(quantity) as cnt FROM products WHERE deleted_at IS NULL').fetchone()['cnt'] or 0

    # Sản phẩm sắp hết
    stats['low_stock'] = db.execute(
        'SELECT COUNT(*) as cnt FROM products WHERE deleted_at IS NULL AND quantity < min_quantity').fetchone()['cnt']

    # Giá trị tồn kho (giá vốn)
    stats['total_value'] = db.execute(
        'SELECT SUM(quantity * cost_price) as val FROM products WHERE deleted_at IS NULL').fetchone()['val'] or 0

    # Phiếu xuất hôm nay — created_at lưu UTC, quy đổi sang giờ VN (UTC+7)
    stats['today_exports'] = db.execute(
        f"""SELECT COUNT(*) as cnt FROM export_orders
            WHERE status != 'cancelled'
              AND DATE(created_at, '{VN_OFFSET}') = DATE('now', '{VN_OFFSET}')"""
    ).fetchone()['cnt']

    # Sản phẩm bán chạy tháng này (top 5) — theo tháng giờ VN
    top_products = db.execute(f'''
        SELECT p.name, p.sku, SUM(eoi.quantity) as total_sold
        FROM export_order_items eoi
        JOIN export_orders eo ON eo.id = eoi.export_order_id
        JOIN products p ON p.id = eoi.product_id
        WHERE eo.status != 'cancelled'
          AND strftime('%Y-%m', eo.created_at, '{VN_OFFSET}') = strftime('%Y-%m', 'now', '{VN_OFFSET}')
        GROUP BY p.id
        ORDER BY total_sold DESC
        LIMIT 5
    ''').fetchall()

    # Sản phẩm sắp hết (danh sách)
    low_stock_products = db.execute('''
        SELECT sku, name, quantity, min_quantity, unit
        FROM products
        WHERE deleted_at IS NULL AND quantity < min_quantity
        ORDER BY quantity ASC
        LIMIT 10
    ''').fetchall()

    # Hoạt động gần đây
    recent_orders = db.execute('''
        SELECT eo.order_code, eo.customer_name, eo.created_at, eo.status, u.display_name
        FROM export_orders eo
        JOIN users u ON u.id = eo.created_by
        ORDER BY eo.created_at DESC
        LIMIT 5
    ''').fetchall()

    return render_template('dashboard/index.html',
                          stats=stats,
                          top_products=top_products,
                          low_stock_products=low_stock_products,
                          recent_orders=recent_orders)


@bp.get('/')
def root():
    return redirect(url_for('dashboard.index') if g.user else url_for('auth.login'))
