import sqlite3
from flask import current_app, g


def connect(path):
    conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=5000')
    return conn


def validate_legacy_schema(conn):
    required = {
        'products': {'id', 'quantity', 'updated_at'},
        'transactions': {'id', 'product_id', 'type', 'quantity'},
    }
    for table, columns in required.items():
        actual = {row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
        if not columns <= actual:
            raise RuntimeError(f'Cấu trúc cơ sở dữ liệu không tương thích: {table}')
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name='trg_update_quantity'").fetchone()
    sql = ' '.join((row[0] if row else '').lower().split())
    fragments = (
        'after insert on transactions', 'new.type', "='import'", "='export'", "='adjust'",
        'quantity+new.quantity', 'quantity-new.quantity', 'then new.quantity',
        'where id=new.product_id',
    )
    compact = sql.replace(' ', '')
    if not row or any(fragment.replace(' ', '') not in compact for fragment in fragments):
        raise RuntimeError('Cấu trúc cơ sở dữ liệu không tương thích: trg_update_quantity')


def get_db():
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'])
    return g.db


def close_db(_error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
