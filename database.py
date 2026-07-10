import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from config import DB_PATH, ADMIN_DEFAULT_PASSWORD, STAFF_DEFAULT_PASSWORD, COMPANY_DEFAULTS, LOW_STOCK_DEFAULT

SCHEMA_VERSION = 15

def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def query(sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchall()

def query_one(sql: str, params: Iterable[Any] = ()) -> Optional[Dict[str, Any]]:
    rows = query(sql, params)
    return rows[0] if rows else None

def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(sql, tuple(params))
        return int(cur.lastrowid or 0)

def make_hash(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 160_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"

def verify_hash(password: str, stored: str) -> bool:
    try:
        alg, salt, digest = stored.split("$", 2)
        if alg != "pbkdf2_sha256":
            return False
        test = make_hash(password, salt).split("$", 2)[2]
        return secrets.compare_digest(test, digest)
    except Exception:
        return False

def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin','staff')),
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                category TEXT,
                brand TEXT,
                model TEXT NOT NULL,
                color TEXT,
                ram TEXT,
                rom TEXT,
                condition TEXT,
                description TEXT,
                supplier TEXT,
                cost REAL NOT NULL DEFAULT 0,
                price REAL NOT NULL DEFAULT 0,
                offer_price REAL NOT NULL DEFAULT 0,
                is_serialized INTEGER NOT NULL DEFAULT 1,
                quantity INTEGER NOT NULL DEFAULT 0,
                low_stock INTEGER NOT NULL DEFAULT 3,
                status TEXT NOT NULL DEFAULT 'Available',
                image_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS suppliers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT COLLATE NOCASE UNIQUE NOT NULL,
                contact_person TEXT,
                phone TEXT,
                whatsapp TEXT,
                email TEXT,
                address TEXT,
                notes TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS product_units(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                unit_code TEXT NOT NULL,
                cost REAL NOT NULL DEFAULT 0,
                supplier TEXT,
                supplier_id INTEGER REFERENCES suppliers(id),
                purchase_batch_id INTEGER REFERENCES restock_batches(id),
                status TEXT NOT NULL DEFAULT 'Available',
                shop_id INTEGER,
                invoice_id INTEGER,
                wholesale_invoice_id INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(product_id, unit_code)
            );
            CREATE TABLE IF NOT EXISTS restock_batches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                sku TEXT NOT NULL,
                qty_added INTEGER NOT NULL,
                unit_cost REAL NOT NULL DEFAULT 0,
                old_qty INTEGER NOT NULL DEFAULT 0,
                new_qty INTEGER NOT NULL DEFAULT 0,
                old_average_cost REAL NOT NULL DEFAULT 0,
                new_average_cost REAL NOT NULL DEFAULT 0,
                supplier TEXT,
                supplier_id INTEGER REFERENCES suppliers(id),
                batch_code TEXT,
                note TEXT,
                stock_value_before REAL NOT NULL DEFAULT 0,
                stock_value_after REAL NOT NULL DEFAULT 0,
                created_by TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS customers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                whatsapp TEXT,
                email TEXT,
                address TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_no TEXT UNIQUE NOT NULL,
                customer_id INTEGER REFERENCES customers(id),
                customer_name TEXT NOT NULL,
                customer_phone TEXT,
                customer_whatsapp TEXT,
                customer_email TEXT,
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                extended_warranty_total REAL NOT NULL DEFAULT 0,
                grand_total REAL NOT NULL DEFAULT 0,
                paid_total REAL NOT NULL DEFAULT 0,
                balance REAL NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'Unpaid',
                payments_json TEXT NOT NULL DEFAULT '[]',
                general_warranty TEXT,
                general_warranty_days INTEGER NOT NULL DEFAULT 0,
                general_warranty_expire TEXT,
                note TEXT,
                pdf_path TEXT,
                status TEXT NOT NULL DEFAULT 'Active',
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS invoice_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id),
                unit_id INTEGER REFERENCES product_units(id),
                sku TEXT,
                product_name TEXT NOT NULL,
                unit_code TEXT,
                qty INTEGER NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                unit_cost REAL NOT NULL DEFAULT 0,
                regular_price REAL NOT NULL DEFAULT 0,
                catalog_offer_price REAL NOT NULL DEFAULT 0,
                offer_applied INTEGER NOT NULL DEFAULT 0,
                offer_saving REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                item_source TEXT NOT NULL DEFAULT 'Inventory',
                direct_supplier TEXT,
                buying_note TEXT,
                extended_warranty_name TEXT,
                extended_warranty_price REAL NOT NULL DEFAULT 0,
                extended_warranty_days INTEGER NOT NULL DEFAULT 0,
                extended_warranty_expire TEXT,
                general_warranty TEXT,
                general_warranty_days INTEGER NOT NULL DEFAULT 0,
                general_warranty_expire TEXT,
                warranty_note TEXT,
                line_total REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shops(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                contact_person TEXT,
                phone TEXT,
                whatsapp TEXT,
                email TEXT,
                address TEXT,
                credit_limit REAL NOT NULL DEFAULT 0,
                notes TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wholesale_invoices(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_no TEXT UNIQUE NOT NULL,
                shop_id INTEGER NOT NULL REFERENCES shops(id),
                shop_name TEXT NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                grand_total REAL NOT NULL DEFAULT 0,
                paid_total REAL NOT NULL DEFAULT 0,
                balance REAL NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'Unpaid',
                initial_payments_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'Open',
                note TEXT,
                pdf_path TEXT,
                created_by TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wholesale_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wholesale_invoice_id INTEGER NOT NULL REFERENCES wholesale_invoices(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id),
                unit_id INTEGER REFERENCES product_units(id),
                sku TEXT,
                product_name TEXT NOT NULL,
                unit_code TEXT,
                qty INTEGER NOT NULL DEFAULT 1,
                unit_cost REAL NOT NULL DEFAULT 0,
                selling_price REAL NOT NULL DEFAULT 0,
                line_total REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wholesale_payments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_no TEXT UNIQUE NOT NULL,
                shop_id INTEGER NOT NULL REFERENCES shops(id),
                amount REAL NOT NULL DEFAULT 0,
                payments_json TEXT NOT NULL DEFAULT '[]',
                note TEXT,
                allocations_json TEXT NOT NULL DEFAULT '[]',
                created_by TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                role TEXT,
                action TEXT NOT NULL,
                target TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sync_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        for table, additions in {
            "invoices": [("customer_whatsapp", "TEXT"), ("customer_email", "TEXT"), ("payments_json", "TEXT NOT NULL DEFAULT '[]'"), ("payment_status", "TEXT NOT NULL DEFAULT 'Unpaid'")],
            "wholesale_invoices": [("initial_payments_json", "TEXT NOT NULL DEFAULT '[]'"), ("payment_status", "TEXT NOT NULL DEFAULT 'Unpaid'")],
            "wholesale_payments": [("payments_json", "TEXT NOT NULL DEFAULT '[]'")],
            "customers": [("whatsapp", "TEXT"), ("email", "TEXT")],
            "products": [("supplier", "TEXT")],
            "invoice_items": [("general_warranty_days", "INTEGER NOT NULL DEFAULT 0"), ("warranty_note", "TEXT"), ("regular_price", "REAL NOT NULL DEFAULT 0"), ("catalog_offer_price", "REAL NOT NULL DEFAULT 0"), ("offer_applied", "INTEGER NOT NULL DEFAULT 0"), ("offer_saving", "REAL NOT NULL DEFAULT 0"), ("item_source", "TEXT NOT NULL DEFAULT 'Inventory'"), ("direct_supplier", "TEXT"), ("buying_note", "TEXT")],
            "product_units": [("supplier", "TEXT"), ("supplier_id", "INTEGER"), ("purchase_batch_id", "INTEGER")],
            "restock_batches": [("supplier_id", "INTEGER"), ("batch_code", "TEXT")],
        }.items():
            for c, d in additions:
                _add_column_if_missing(conn, table, c, d)
        # Normalize all historical supplier names without breaking the legacy
        # text columns used by older invoices, exports and backups.
        stamp = now_iso()
        conn.execute("""
            INSERT OR IGNORE INTO suppliers(name,active,created_at,updated_at)
            SELECT supplier,1,?,? FROM (
                SELECT TRIM(supplier) supplier FROM products
                UNION SELECT TRIM(supplier) FROM product_units
                UNION SELECT TRIM(supplier) FROM restock_batches
            ) WHERE supplier IS NOT NULL AND supplier<>''
        """, (stamp, stamp))
        conn.execute("""UPDATE product_units SET supplier_id=(SELECT s.id FROM suppliers s WHERE s.name=product_units.supplier COLLATE NOCASE) WHERE supplier_id IS NULL AND TRIM(COALESCE(supplier,''))<>''""")
        conn.execute("""UPDATE restock_batches SET supplier_id=(SELECT s.id FROM suppliers s WHERE s.name=restock_batches.supplier COLLATE NOCASE) WHERE supplier_id IS NULL AND TRIM(COALESCE(supplier,''))<>''""")
        conn.execute("UPDATE restock_batches SET batch_code='LEGACY-' || printf('%08d',id) WHERE TRIM(COALESCE(batch_code,''))='' ")
        # Historical units did not store a batch key. Link them when a single
        # unambiguous product/supplier/cost acquisition exists; otherwise keep
        # the field NULL rather than inventing inaccurate lineage.
        conn.execute("""
            UPDATE product_units
            SET purchase_batch_id=(
                SELECT MIN(r.id) FROM restock_batches r
                WHERE r.product_id=product_units.product_id
                  AND COALESCE(r.supplier_id,0)=COALESCE(product_units.supplier_id,0)
                  AND ABS(COALESCE(r.unit_cost,0)-COALESCE(product_units.cost,0))<0.000001
                HAVING COUNT(*)=1
            )
            WHERE purchase_batch_id IS NULL
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_restock_batch_code ON restock_batches(batch_code) WHERE batch_code IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_product_units_batch ON product_units(purchase_batch_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_product_units_supplier ON product_units(supplier_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_product_units_code_nocase ON product_units(unit_code COLLATE NOCASE)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_restock_product_date ON restock_batches(product_id,created_at)")
        # Required attribution is persisted for existing installations as well
        # as fresh databases. Preserve any customized footer and append once.
        footer_row = conn.execute("SELECT value FROM settings WHERE key='invoice_footer'").fetchone()
        if footer_row and "System by Hich web Development" not in str(footer_row.get("value") or ""):
            footer = str(footer_row.get("value") or "Thank you for choosing ICON MOBILE. Please keep this invoice for warranty claims.").strip()
            conn.execute("UPDATE settings SET value=?,updated_at=? WHERE key='invoice_footer'", (footer + " System by Hich web Development 0714112113.", now_iso()))
        conn.execute("""
            INSERT INTO settings(key,value,updated_at) VALUES('company_phone','070 144 2299',?)
            ON CONFLICT(key) DO UPDATE SET value='070 144 2299', updated_at=excluded.updated_at
        """, (now_iso(),))
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        seed_defaults(conn)

def seed_defaults(conn: sqlite3.Connection) -> None:
    stamp = now_iso()
    if not conn.execute("SELECT id FROM users WHERE username='admin'").fetchone():
        conn.execute("INSERT INTO users(username,role,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,?,?)", ("admin", "admin", make_hash(ADMIN_DEFAULT_PASSWORD), 1, stamp, stamp))
    if not conn.execute("SELECT id FROM users WHERE username='staff'").fetchone():
        conn.execute("INSERT INTO users(username,role,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,?,?)", ("staff", "staff", make_hash(STAFF_DEFAULT_PASSWORD), 1, stamp, stamp))
    defaults = dict(COMPANY_DEFAULTS)
    defaults["low_stock_default"] = str(LOW_STOCK_DEFAULT)
    defaults.setdefault("last_backup_at", "")
    for key, value in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings(key,value,updated_at) VALUES(?,?,?)", (key, str(value), stamp))

def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default

def set_setting(key: str, value: str) -> None:
    execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at", (key, str(value), now_iso()))

def log_audit(user: str, role: str, action: str, target: str = "", details: Any = "") -> None:
    if not isinstance(details, str):
        details = json.dumps(details, ensure_ascii=False, default=str)
    stamp = now_iso()
    execute("INSERT INTO audit_log(user,role,action,target,details,created_at) VALUES(?,?,?,?,?,?)", (user, role, action, target, details, stamp))
    execute("INSERT INTO sync_events(event_type,payload_json,created_at) VALUES(?,?,?)", (action, details or "{}", stamp))

init_db()
