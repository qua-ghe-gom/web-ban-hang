from flask import Blueprint, redirect, render_template, url_for
from .auth import login_required
from .db import get_db
from .services.export_service import get_order

bp = Blueprint('print', __name__)


@bp.get('/phieu-xuat/<code>/in')
@login_required
def print_order(code):
    order = get_order(get_db(), code)
    if not order:
        return redirect(url_for('exports.history'))
    return render_template('print/order.html', order=order)
