import json
import secrets
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from .auth import login_required
from .db import get_db
from .services.export_service import (ExportBusy, ExportConflict, ExportError, cancel_export_order, confirm_export,
                                      get_order, update_invoice_status, validate_review)

bp = Blueprint('exports', __name__)
FIELDS = ('customer_name','customer_phone','delivery_address','note')

def _payload():
    try:
        items = json.loads(request.form.get('items_json','[]'))
    except json.JSONDecodeError as exc:
        raise ExportError('Dữ liệu phiếu không hợp lệ') from exc
    metadata = {name: request.form.get(name,'').strip()[:500] or None for name in FIELDS}
    return items, metadata

@bp.post('/xuat-kho/review')
@login_required
def review():
    try:
        items, metadata = _payload()
        products = validate_review(get_db(), items)
    except ExportError as exc:
        abort(400, description=str(exc))
    return render_template('exports/review.html', products=products, items_json=json.dumps(items),
                           metadata=metadata, idempotency_key=secrets.token_urlsafe(32),
                           invoice_issued=request.form.get('invoice_issued') == '1')

@bp.post('/xuat-kho/confirm')
@login_required
def confirm():
    try:
        items, metadata = _payload()
        order = confirm_export(current_app.config['DATABASE'], g.user['id'], items, metadata,
                               request.form.get('idempotency_key',''), request.form.get('invoice_issued') == '1')
    except ExportConflict as exc:
        abort(409, description=str(exc))
    except ExportBusy as exc:
        abort(503, description=str(exc))
    except ExportError as exc:
        abort(400, description=str(exc))
    return redirect(url_for('exports.success', code=order['order_code']))

@bp.get('/phieu-xuat/<code>/thanh-cong')
@login_required
def success(code):
    order = get_order(get_db(), code)
    if not order: abort(404)
    return render_template('exports/success.html', order=order)

@bp.get('/phieu-xuat/<code>')
@login_required
def detail(code):
    order = get_order(get_db(), code)
    if not order: abort(404)
    return render_template('exports/detail.html', order=order)

@bp.post('/phieu-xuat/<code>/hoa-don')
@login_required
def update_invoice(code):
    if g.user['role'] != 'admin':
        abort(403)
    db = get_db()
    order = db.execute('SELECT id,status FROM export_orders WHERE order_code=?',(code,)).fetchone()
    if not order: abort(404)
    if order['status'] == 'cancelled':
        flash('Phiếu đã hủy, không thể đổi trạng thái hóa đơn', 'error')
        return redirect(url_for('exports.detail', code=code))
    issued = request.form.get('invoice_issued') == '1'
    update_invoice_status(db, order['id'], issued, g.user['id'], request.form.get('reason'))
    flash('Đã cập nhật trạng thái hóa đơn', 'success')
    return redirect(url_for('exports.detail', code=code))

@bp.get('/lich-su')
@login_required
def history():
    q = request.args.get('q','').strip()
    sql = '''SELECT o.*,u.display_name created_by_name,COUNT(DISTINCT i.id) item_count
      FROM export_orders o JOIN users u ON u.id=o.created_by
      LEFT JOIN export_order_items i ON i.export_order_id=o.id WHERE 1=1'''
    params = []
    if q:
        sql += ''' AND (o.order_code LIKE ? OR COALESCE(o.customer_name,'') LIKE ? OR EXISTS(
          SELECT 1 FROM export_order_items si WHERE si.export_order_id=o.id AND (si.product_name_snapshot LIKE ? OR si.sku_snapshot LIKE ?)))'''
        params += [f'%{q}%'] * 4
    sql += ' GROUP BY o.id ORDER BY o.created_at DESC,o.id DESC LIMIT 100'
    orders = get_db().execute(sql, params).fetchall()
    return render_template('exports/history.html', orders=orders, q=q)


@bp.post('/phieu-xuat/<code>/huy')
@login_required
def cancel_order(code):
    # Chỉ admin mới hủy được
    if g.user['role'] != 'admin':
        abort(403)
    reason = (request.form.get('reason') or '').strip()[:500] or None
    try:
        cancel_export_order(current_app.config['DATABASE'], code, g.user['id'], reason)
        flash(f'Đã hủy phiếu {code} và trả hàng về kho', 'success')
    except ExportBusy as exc:
        abort(503, description=str(exc))
    except ExportError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('exports.detail', code=code))
