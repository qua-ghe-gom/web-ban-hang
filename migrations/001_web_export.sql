CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'staff' CHECK(role IN ('admin','staff')),
    is_active INTEGER NOT NULL DEFAULT 1,
    failed_login_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS export_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code TEXT UNIQUE NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    request_hash TEXT NOT NULL,
    customer_name TEXT,
    customer_phone TEXT,
    delivery_address TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('completed','cancelled')),
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    cancelled_at TEXT,
    cancelled_by INTEGER,
    cancel_reason TEXT,
    invoice_issued INTEGER NOT NULL DEFAULT 0 CHECK(invoice_issued IN (0,1)),
    invoice_issued_at TEXT,
    invoice_issued_by INTEGER,
    FOREIGN KEY(created_by) REFERENCES users(id),
    FOREIGN KEY(cancelled_by) REFERENCES users(id),
    FOREIGN KEY(invoice_issued_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS export_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    product_name_snapshot TEXT NOT NULL,
    sku_snapshot TEXT NOT NULL,
    unit_snapshot TEXT NOT NULL,
    stock_before INTEGER NOT NULL,
    stock_after INTEGER NOT NULL,
    transaction_id INTEGER NOT NULL UNIQUE,
    FOREIGN KEY(export_order_id) REFERENCES export_orders(id),
    FOREIGN KEY(product_id) REFERENCES products(id),
    FOREIGN KEY(transaction_id) REFERENCES transactions(id),
    UNIQUE(export_order_id, product_id)
);

CREATE TABLE IF NOT EXISTS invoice_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_order_id INTEGER NOT NULL,
    old_status INTEGER NOT NULL CHECK(old_status IN (0,1)),
    new_status INTEGER NOT NULL CHECK(new_status IN (0,1)),
    actor_id INTEGER NOT NULL,
    changed_at TEXT NOT NULL,
    reason TEXT,
    FOREIGN KEY(export_order_id) REFERENCES export_orders(id),
    FOREIGN KEY(actor_id) REFERENCES users(id)
);

CREATE TRIGGER IF NOT EXISTS trg_invoice_events_no_update
BEFORE UPDATE ON invoice_status_events BEGIN
    SELECT RAISE(ABORT, 'invoice status events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_invoice_events_no_delete
BEFORE DELETE ON invoice_status_events BEGIN
    SELECT RAISE(ABORT, 'invoice status events are append-only');
END;

CREATE INDEX IF NOT EXISTS idx_export_orders_created_at ON export_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_export_items_order ON export_order_items(export_order_id);
CREATE INDEX IF NOT EXISTS idx_invoice_events_order ON invoice_status_events(export_order_id, id);
