#!/usr/bin/env python3
"""Versioned, transactional web-export migration; only runs when explicitly called."""
import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webapp.db import validate_legacy_schema

DEFAULT_DB = ROOT / 'data' / 'kho.db'
MIGRATIONS_DIR = ROOT / 'migrations'


def _discover_migrations():
    """Tất cả migration trong migrations/, sắp theo số thứ tự ở đầu tên file."""
    found = []
    for path in MIGRATIONS_DIR.glob('*.sql'):
        match = re.match(r'(\d+)_', path.name)
        if not match:
            raise RuntimeError(f'Tên migration không có số thứ tự: {path.name}')
        found.append((int(match.group(1)), path))
    if not found:
        raise RuntimeError(f'Không tìm thấy migration nào trong {MIGRATIONS_DIR}')
    found.sort()
    numbers = [number for number, _ in found]
    if len(set(numbers)) != len(numbers):
        raise RuntimeError(f'Số thứ tự migration bị trùng: {numbers}')
    return found


MIGRATIONS = _discover_migrations()
SCHEMA_VERSION = MIGRATIONS[-1][0]


def _check_integrity(conn):
    result = conn.execute('PRAGMA integrity_check').fetchone()
    if not result or result[0] != 'ok':
        raise RuntimeError(f"SQLite integrity_check thất bại: {result[0] if result else 'unknown'}")


def _backup_database(path):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ')
    backup = path.with_name(f'{path.name}.backup-{stamp}')
    suffix = 1
    while backup.exists():
        backup = path.with_name(f'{path.name}.backup-{stamp}-{suffix}')
        suffix += 1
    source = sqlite3.connect(path)
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    destination = sqlite3.connect(backup)
    try:
        source.backup(destination)
        _check_integrity(destination)
        destination.commit()
        backup.chmod(0o600)
        if (backup.stat().st_mode & 0o777) != 0o600:
            raise RuntimeError('Không thể giới hạn quyền truy cập file backup')
    except Exception:
        source.close()
        destination.close()
        backup.unlink(missing_ok=True)
        raise
    source.close()
    destination.close()
    return backup


def _statements(sql):
    statement = ''
    for line in sql.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            if statement.strip():
                yield statement
            statement = ''
    if statement.strip():
        raise RuntimeError('Tệp migration SQL không hoàn chỉnh')


def _apply_migration(conn, path):
    """Chạy 1 file migration. ADD COLUMN đã tồn tại được coi là đã áp dụng."""
    for statement in _statements(path.read_text(encoding='utf-8')):
        try:
            conn.execute(statement)
        except sqlite3.OperationalError as exc:
            if 'duplicate column name' in str(exc).lower():
                continue
            raise RuntimeError(f'Migration {path.name} thất bại: {exc}') from exc


def _export_orders_compatible(conn):
    columns = {row[1] for row in conn.execute('PRAGMA table_info(export_orders)')}
    required = {
        'id', 'order_code', 'idempotency_key', 'request_hash', 'customer_name',
        'customer_phone', 'delivery_address', 'note', 'status', 'created_by',
        'created_at', 'cancelled_at', 'cancelled_by', 'cancel_reason',
        'invoice_issued', 'invoice_issued_at', 'invoice_issued_by',
    }
    foreign_keys = {(row[3], row[2]) for row in conn.execute('PRAGMA foreign_key_list(export_orders)')}
    sql_row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='export_orders'").fetchone()
    sql = (sql_row[0] if sql_row else '').lower().replace(' ', '')
    return (required <= columns and
            {('created_by', 'users'), ('cancelled_by', 'users'), ('invoice_issued_by', 'users')} <= foreign_keys and
            "check(invoice_issuedin(0,1))" in sql and
            "check(statusin('completed','cancelled'))" in sql)


def _rebuild_export_orders(conn):
    existing = {row[1] for row in conn.execute('PRAGMA table_info(export_orders)')}
    conn.execute('''CREATE TABLE export_orders_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT UNIQUE NOT NULL,
        idempotency_key TEXT UNIQUE NOT NULL,
        request_hash TEXT NOT NULL,
        customer_name TEXT, customer_phone TEXT, delivery_address TEXT, note TEXT,
        status TEXT NOT NULL DEFAULT 'completed' CHECK(status IN ('completed','cancelled')),
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        cancelled_at TEXT, cancelled_by INTEGER, cancel_reason TEXT,
        invoice_issued INTEGER NOT NULL DEFAULT 0 CHECK(invoice_issued IN (0,1)),
        invoice_issued_at TEXT, invoice_issued_by INTEGER,
        FOREIGN KEY(created_by) REFERENCES users(id),
        FOREIGN KEY(cancelled_by) REFERENCES users(id),
        FOREIGN KEY(invoice_issued_by) REFERENCES users(id)
    )''')
    targets = [
        'id', 'order_code', 'idempotency_key', 'request_hash', 'customer_name',
        'customer_phone', 'delivery_address', 'note', 'status', 'created_by',
        'created_at', 'cancelled_at', 'cancelled_by', 'cancel_reason',
        'invoice_issued', 'invoice_issued_at', 'invoice_issued_by',
    ]
    defaults = {
        'request_hash': "'legacy:' || id",
        'status': "'completed'",
        'created_at': "strftime('%Y-%m-%dT%H:%M:%fZ','now')",
        'invoice_issued': '0',
    }
    expressions = [name if name in existing else defaults.get(name, 'NULL') for name in targets]
    conn.execute(f'''INSERT INTO export_orders_new({','.join(targets)})
                     SELECT {','.join(expressions)} FROM export_orders''')
    conn.execute('DROP TABLE export_orders')
    conn.execute('ALTER TABLE export_orders_new RENAME TO export_orders')


def migrate_database(db_path, create_backup=True):
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    backup = None
    try:
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute('BEGIN IMMEDIATE')
        _check_integrity(conn)
        validate_legacy_schema(conn)
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f'Phiên bản cơ sở dữ liệu {version} mới hơn ứng dụng')
        if create_backup:
            backup = _backup_database(path)
        has_orders = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='export_orders'").fetchone()
        if has_orders and not _export_orders_compatible(conn):
            _rebuild_export_orders(conn)
        for number, migration_path in MIGRATIONS:
            if number <= version:
                continue
            _apply_migration(conn, migration_path)
        conn.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        violations = conn.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError(f'foreign_key_check thất bại: {violations[:3]}')
        _check_integrity(conn)
        conn.commit()
        conn.execute('PRAGMA foreign_keys=ON')
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
    return backup


def main():
    parser = argparse.ArgumentParser(description='Migration web xuất kho an toàn')
    parser.add_argument('--database', type=Path, default=DEFAULT_DB)
    parser.add_argument('--no-backup', action='store_true', help='Chỉ dùng cho DB test/bản sao')
    args = parser.parse_args()
    backup = migrate_database(args.database, create_backup=not args.no_backup)
    print(f'Migration thành công: {args.database}')
    if backup:
        print(f'Backup: {backup}')


if __name__ == '__main__':
    main()
