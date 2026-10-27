import sqlite3
import hashlib
import json
import re
from datetime import datetime, timezone
from ..db import connect, validate_legacy_schema

class ExportError(ValueError):
    pass


class ExportConflict(ExportError):
    pass


class ExportBusy(ExportError):
    pass


MAX_ORDER_LINES = 100
METADATA_FIELDS = ('customer_name', 'customer_phone', 'delivery_address', 'note')


def _utc_now():
    return datetime.now(timezone.utc)


def _valid_items(items):
    if not isinstance(items, list) or not items:
        raise ExportError('Phiếu chưa có mặt hàng')
    if len(items) > MAX_ORDER_LINES:
        raise ExportError(f'Phiếu không được vượt quá {MAX_ORDER_LINES} mặt hàng')
    seen = set(); normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ExportError('Dữ liệu mặt hàng không hợp lệ')
        product_id, quantity = item.get('product_id'), item.get('quantity')
        if isinstance(product_id, bool) or not isinstance(product_id, int) or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ExportError('Số lượng hoặc sản phẩm không hợp lệ')
        if product_id in seen:
            raise ExportError('Mặt hàng bị trùng')
        seen.add(product_id); normalized.append((product_id, quantity))
    return normalized


def validate_review(conn, items):
    normalized = _valid_items(items)
    result = []
    for product_id, qty in normalized:
        p = conn.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
        if not p:
            raise ExportError('Sản phẩm không tồn tại')
        if p['quantity'] < qty:
            raise ExportError(f"{p['name']} chỉ còn {p['quantity']} {p['unit']}")
        row = dict(p); row['export_quantity'] = qty; row['stock_after'] = p['quantity'] - qty
        result.append(row)
    return result


def _next_code(conn, now=None):
    prefix = (now or _utc_now()).strftime('PXK-%Y%m%d-')
    suffixes = []
    for row in conn.execute('SELECT order_code FROM export_orders WHERE order_code LIKE ?', (prefix+'%',)):
        match = re.fullmatch(re.escape(prefix) + r'(\d+)', row[0])
        if match:
            suffixes.append(int(match.group(1)))
    seq = max(suffixes, default=0) + 1
    if seq > 9999:
        raise ExportError('Quá nhiều phiếu xuất trong ngày (hơn 9999), không thể tạo mã mới')
    return f'{prefix}{seq:04d}'


def _request_hash(user_id, normalized, metadata, invoice_issued):
    if not isinstance(metadata, dict):
        raise ExportError('Thông tin phiếu không hợp lệ')
    canonical = {
        'creator': user_id,
        'items': sorted(({'product_id': p, 'quantity': q} for p, q in normalized),
                        key=lambda item: item['product_id']),
        'metadata': {key: metadata.get(key) for key in METADATA_FIELDS},
        'invoice_issued': bool(invoice_issued),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(encoded).hexdigest()


_ORDER_SELECT = '''SELECT o.*,u.display_name created_by_name,iu.display_name invoice_by_name,
        cu.display_name cancelled_by_name FROM export_orders o
    JOIN users u ON u.id=o.created_by
    LEFT JOIN users iu ON iu.id=o.invoice_issued_by
    LEFT JOIN users cu ON cu.id=o.cancelled_by WHERE '''


def get_order(conn, code_or_id):
    if isinstance(code_or_id, int):
        order = conn.execute(_ORDER_SELECT + 'o.id=?', (code_or_id,)).fetchone()
    else:
        order = conn.execute(_ORDER_SELECT + 'o.order_code=?', (code_or_id,)).fetchone()
    if not order: return None
    data = dict(order)
    data['items'] = [dict(r) for r in conn.execute('''SELECT i.*, t.unit_price, t.total_amount
        FROM export_order_items i JOIN transactions t ON t.id=i.transaction_id
        WHERE i.export_order_id=? ORDER BY i.id''', (order['id'],))]
    return data


def confirm_export(db_path, user_id, items, metadata, idempotency_key, invoice_issued=False):
    if not idempotency_key or len(idempotency_key) > 200:
        raise ExportError('Mã chống lặp không hợp lệ')
    normalized = _valid_items(items)
    request_hash = _request_hash(user_id, normalized, metadata, invoice_issued)
    conn = connect(db_path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        try:
            validate_legacy_schema(conn)
        except RuntimeError as exc:
            raise ExportError('Cấu trúc dữ liệu kho không tương thích') from exc
        existing = conn.execute('SELECT id,created_by,request_hash FROM export_orders WHERE idempotency_key=?',(idempotency_key,)).fetchone()
        if existing:
            if existing['created_by'] != user_id or existing['request_hash'] != request_hash:
                raise ExportConflict('Mã chống lặp đã được dùng cho một yêu cầu khác')
            result = get_order(conn, existing['id']); conn.commit(); return result
        products = []
        for product_id, qty in normalized:
            p = conn.execute('SELECT * FROM products WHERE id=?',(product_id,)).fetchone()
            if not p: raise ExportError('Sản phẩm không tồn tại')
            if p['quantity'] < qty: raise ExportError(f"{p['name']} chỉ còn {p['quantity']} {p['unit']}")
            products.append((p,qty))
        now_value = _utc_now()
        code = _next_code(conn, now_value)
        now = now_value.isoformat(timespec='seconds')
        inv = 1 if invoice_issued else 0
        cursor = conn.execute('''INSERT INTO export_orders(order_code,idempotency_key,request_hash,customer_name,customer_phone,delivery_address,note,created_by,created_at,invoice_issued,invoice_issued_at,invoice_issued_by)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (code,idempotency_key,request_hash,metadata.get('customer_name'),metadata.get('customer_phone'),metadata.get('delivery_address'),metadata.get('note'),user_id,now,inv,now if inv else None,user_id if inv else None))
        order_id = cursor.lastrowid
        if inv:
            conn.execute('''INSERT INTO invoice_status_events(export_order_id,old_status,new_status,actor_id,changed_at)
                            VALUES(?,0,1,?,?)''', (order_id, user_id, now))
        for p, qty in products:
            # Re-check quantity right before insert. BEGIN IMMEDIATE đã giữ write-lock
            # toàn DB nên không writer nào chen vào giữa được (SQLite không có FOR UPDATE).
            p_refreshed = conn.execute('SELECT quantity FROM products WHERE id=?',(p['id'],)).fetchone()
            if not p_refreshed or p_refreshed['quantity'] < qty:
                raise ExportError(f"{p['name']} chỉ còn {p_refreshed['quantity'] if p_refreshed else 0} {p['unit']}")
            stock_before = p_refreshed['quantity']
            note = f"{code}" + (f" | {metadata.get('customer_name')}" if metadata.get('customer_name') else '')
            tx = conn.execute("""INSERT INTO transactions(product_id,type,quantity,unit_price,total_amount,note,created_at)
                               VALUES(?,'export',?,?,?,?,?)""",
                              (p['id'],qty,p['sell_price'],qty*p['sell_price'],note,now))
            stock_after = conn.execute('SELECT quantity FROM products WHERE id=?',(p['id'],)).fetchone()[0]
            if stock_after != stock_before - qty:
                raise ExportError('Cấu trúc dữ liệu kho không tương thích')
            conn.execute('''INSERT INTO export_order_items(export_order_id,product_id,quantity,product_name_snapshot,sku_snapshot,unit_snapshot,stock_before,stock_after,transaction_id)
             VALUES(?,?,?,?,?,?,?,?,?)''',(order_id,p['id'],qty,p['name'],p['sku'],p['unit'],stock_before,stock_after,tx.lastrowid))
        conn.commit()
        return get_order(conn, order_id)
    except sqlite3.IntegrityError as exc:
        conn.rollback(); raise ExportError('Không thể tạo phiếu') from exc
    except sqlite3.OperationalError as exc:
        conn.rollback()
        if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
            raise ExportBusy('Cơ sở dữ liệu đang bận, vui lòng thử lại với cùng mã chống lặp') from exc
        raise ExportError('Không thể truy cập cơ sở dữ liệu') from exc
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


def update_invoice_status(conn, order_id, issued, actor_id, reason=None):
    now = _utc_now().isoformat(timespec='seconds')
    try:
        conn.execute('BEGIN IMMEDIATE')
        order = conn.execute('SELECT invoice_issued FROM export_orders WHERE id=?', (order_id,)).fetchone()
        if not order:
            conn.rollback()
            return False
        old = int(order['invoice_issued'])
        new = 1 if issued else 0
        if old != new:
            conn.execute('''UPDATE export_orders SET invoice_issued=?,invoice_issued_at=?,invoice_issued_by=?
                            WHERE id=?''', (new, now if new else None, actor_id if new else None, order_id))
            conn.execute('''INSERT INTO invoice_status_events
                            (export_order_id,old_status,new_status,actor_id,changed_at,reason)
                            VALUES(?,?,?,?,?,?)''', (order_id, old, new, actor_id, now, reason))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def cancel_export_order(db_path, order_code, actor_id, reason=None):
    """Hủy phiếu xuất và trả hàng về kho.

    Không xóa dữ liệu: phiếu, mặt hàng, giao dịch gốc và lịch sử hóa đơn đều giữ
    nguyên để tra cứu. Hàng được trả về kho bằng giao dịch bù type='import' để
    trigger trg_update_quantity tự cộng lại tồn kho — nhờ vậy products.quantity
    luôn khớp với sổ giao dịch.
    """
    conn = connect(db_path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        try:
            validate_legacy_schema(conn)
        except RuntimeError as exc:
            raise ExportError('Cấu trúc dữ liệu kho không tương thích') from exc

        order = conn.execute('SELECT * FROM export_orders WHERE order_code=?', (order_code,)).fetchone()
        if not order:
            raise ExportError('Không tìm thấy phiếu xuất')
        if order['status'] == 'cancelled':
            raise ExportError(f'Phiếu {order_code} đã được hủy trước đó')

        order_id = order['id']
        now = _utc_now().isoformat(timespec='seconds')
        items = conn.execute('''SELECT i.product_id,i.quantity,t.unit_price,t.total_amount
            FROM export_order_items i JOIN transactions t ON t.id=i.transaction_id
            WHERE i.export_order_id=? ORDER BY i.id''', (order_id,)).fetchall()
        if not items:
            raise ExportError('Phiếu xuất không có mặt hàng để trả về kho')

        note = f'Hủy {order_code}' + (f' | {reason}' if reason else '')
        for item in items:
            conn.execute("""INSERT INTO transactions(product_id,type,quantity,unit_price,total_amount,note,created_at)
                            VALUES(?,'import',?,?,?,?,?)""",
                         (item['product_id'], item['quantity'], item['unit_price'], item['total_amount'], note, now))

        conn.execute('''UPDATE export_orders SET status='cancelled',cancelled_at=?,cancelled_by=?,cancel_reason=?
                        WHERE id=?''', (now, actor_id, reason, order_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ExportError('Không thể hủy phiếu') from exc
    except sqlite3.OperationalError as exc:
        conn.rollback()
        if 'locked' in str(exc).lower() or 'busy' in str(exc).lower():
            raise ExportBusy('Cơ sở dữ liệu đang bận, vui lòng thử lại') from exc
        raise ExportError('Không thể truy cập cơ sở dữ liệu') from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
