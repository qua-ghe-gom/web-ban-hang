from flask import Blueprint, jsonify, render_template, request
from .auth import login_required
from .db import get_db

bp = Blueprint('inventory', __name__)

def query_products():
    q = request.args.get('q','').strip()
    category = request.args.get('category','').strip()
    stock = request.args.get('stock','').strip()
    sort = request.args.get('sort','name')
    sql = '''SELECT p.*, c.name category_name FROM products p
             LEFT JOIN categories c ON c.id=p.category_id WHERE p.quantity>0 AND p.deleted_at IS NULL'''
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR p.sku LIKE ? OR COALESCE(p.note,'') LIKE ? OR COALESCE(p.location,'') LIKE ?)"
        params += [f'%{q}%'] * 4
    if category:
        sql += ' AND p.category_id=?'; params.append(category)
    if stock == 'low':
        sql += ' AND p.quantity<p.min_quantity'
    order = {'name':'p.name COLLATE NOCASE','quantity_asc':'p.quantity ASC','quantity_desc':'p.quantity DESC'}.get(sort,'p.name COLLATE NOCASE')
    sql += ' ORDER BY ' + order
    return get_db().execute(sql, params).fetchall()

@bp.get('/xuat-kho')
@login_required
def index():
    products = query_products()
    categories = get_db().execute('SELECT * FROM categories ORDER BY name').fetchall()
    return render_template('inventory/index.html', products=products, categories=categories)

@bp.get('/api/products')
@login_required
def products_api():
    return jsonify(products=[dict(row) for row in query_products()])
