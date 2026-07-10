import csv
import json
import os
import shutil
import sqlite3
import secrets
import string
import subprocess
import sys
import webbrowser
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from config import BACKUP_DIR, DB_PATH, INVOICE_DIR, LOW_STOCK_DEFAULT, SYNC_PASSWORD
from database import get_conn, query, query_one, execute, now_iso, verify_hash, make_hash, log_audit, get_setting, set_setting


def n(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(str(value).replace(",", "").strip())
    except Exception:
        return 0.0


def i(value: Any) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return 0


def clean(value: Any) -> str:
    return str(value or "").strip()


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def date_add(days: int) -> str:
    days = i(days)
    if days <= 0:
        return ""
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def parse_json(value: Any, default: Any = None) -> Any:
    if default is None:
        default = []
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return default


def warranty_days(label: str, manual_days: Any = 0) -> int:
    label_l = clean(label).lower()
    if "manual" in label_l or "custom" in label_l:
        return max(0, i(manual_days))
    if "no" in label_l:
        return 0
    if "14" in label_l:
        return 14
    if "7" in label_l:
        return 7
    if "1 month" in label_l:
        return 30
    if "3 month" in label_l:
        return 90
    if "6 month" in label_l:
        return 180
    if "3 year" in label_l or "36 month" in label_l:
        return 1095
    if "2 year" in label_l or "24 month" in label_l:
        return 730
    if "1 year" in label_l or "12 month" in label_l:
        return 365
    return max(0, i(manual_days))


def generate_internal_ids(qty: int, reserved: Optional[List[str]] = None) -> List[str]:
    """Generate globally unique human-friendly IDs such as ABC1234."""
    count=max(0,i(qty)); used={clean(x).casefold() for x in (reserved or []) if clean(x)}; result=[]
    for _ in range(count):
        for _attempt in range(500):
            code="".join(secrets.choice(string.ascii_uppercase) for _ in range(3))+"".join(secrets.choice(string.digits) for _ in range(4))
            if code.casefold() in used: continue
            if query_one("SELECT id FROM product_units WHERE lower(unit_code)=lower(?) LIMIT 1",(code,)): continue
            used.add(code.casefold()); result.append(code); break
        else:
            raise RuntimeError("Could not generate a unique internal item ID")
    return result


def normalize_phone(phone: str) -> str:
    p = "".join(ch for ch in clean(phone) if ch.isdigit() or ch == "+")
    if p.startswith("+"):
        p = p[1:]
    if p.startswith("0") and len(p) == 10:
        p = get_setting("whatsapp_country_code", "94") + p[1:]
    return p


def money(value: Any) -> str:
    return f"Rs. {n(value):,.0f}"


def product_display_name(p: Dict[str, Any]) -> str:
    parts = [clean(p.get("brand")), clean(p.get("model")), clean(p.get("color")), clean(p.get("ram")), clean(p.get("rom"))]
    return " ".join([x for x in parts if x]) or clean(p.get("sku")) or "Item"


def require_admin(user: Dict[str, Any]) -> None:
    if not user or user.get("role") != "admin":
        raise PermissionError("Admin access required")


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    row = query_one("SELECT * FROM users WHERE username=? AND active=1", (clean(username),))
    if row and verify_hash(password, row["password_hash"]):
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def change_password(username: str, new_password: str, user: Dict[str, Any]) -> None:
    require_admin(user)
    if len(new_password) < 5:
        raise ValueError("Password must have at least 5 characters")
    execute("UPDATE users SET password_hash=?, updated_at=? WHERE username=?", (make_hash(new_password), now_iso(), username))
    log_audit(user["username"], user["role"], "change_password", username, {})


def next_number(prefix: str, table: str, column: str) -> str:
    day = datetime.now().strftime("%Y%m%d")
    like = f"{prefix}-{day}-%"
    row = query_one(f"SELECT {column} AS no FROM {table} WHERE {column} LIKE ? ORDER BY id DESC LIMIT 1", (like,))
    num = 1
    if row and row.get("no"):
        try:
            num = int(str(row["no"]).split("-")[-1]) + 1
        except Exception:
            num = 1
    return f"{prefix}-{day}-{num:04d}"


def payment_status(total: float, paid: float) -> str:
    if paid <= 0:
        return "Unpaid"
    if paid + 0.001 >= total:
        return "Paid"
    return "Partial"


def normalize_payments(payment_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for row in payment_rows or []:
        if not isinstance(row, dict):
            continue
        method = clean(row.get("method")) or "Cash"
        ref = clean(row.get("reference"))
        custom = clean(row.get("custom_method"))
        # Fix: when + payment is used with Custom selected, never fail because the custom name is empty.
        if method.lower() == "custom":
            method = custom or ref or "Custom Payment"
            ref = ref if ref and ref != method else ""
        amount = n(row.get("amount"))
        if amount <= 0:
            continue
        rows.append({"method": method, "amount": amount, "reference": ref, "created_at": now_iso()})
    return rows


def payment_total(payment_rows: List[Dict[str, Any]]) -> float:
    return sum(n(r.get("amount")) for r in payment_rows or [])


def payment_summary(payment_rows: List[Dict[str, Any]]) -> str:
    rows = normalize_payments(payment_rows)
    if not rows:
        return "Credit / Not Paid"
    return " + ".join([f"{r['method']} {money(r['amount'])}" for r in rows])


# -------------------- Inventory --------------------

def add_product(data: Dict[str, Any], user: Dict[str, Any]) -> int:
    require_admin(user)
    stamp = now_iso()
    sku = clean(data.get("sku")).upper()
    if not sku:
        sku = f"SKU-{int(datetime.now().timestamp())}"
    serialized = 1 if data.get("is_serialized") in (1, True, "1", "Yes", "Serialized") else 0
    units_raw = data.get("units") or ""
    qty = max(0, i(data.get("quantity")))
    units: List[str] = []
    if serialized:
        units = [u.strip() for u in str(units_raw).replace(",", "\n").splitlines() if u.strip()]
        if not units and qty > 0:
            units = [f"{sku}-{idx + 1:04d}" for idx in range(qty)]
        qty = len(units)
    cost = n(data.get("cost"))
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO products(sku,type,category,brand,model,color,ram,rom,condition,description,supplier,cost,price,offer_price,is_serialized,quantity,low_stock,status,image_path,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (sku, clean(data.get("type") or "Phone"), clean(data.get("category")), clean(data.get("brand")), clean(data.get("model") or sku), clean(data.get("color")), clean(data.get("ram")), clean(data.get("rom")), clean(data.get("condition") or "Brand New"), clean(data.get("description")), clean(data.get("supplier")), cost, n(data.get("price")), n(data.get("offer_price")), serialized, qty, i(data.get("low_stock") or LOW_STOCK_DEFAULT), "Available" if qty > 0 else "Out of Stock", clean(data.get("image_path")), stamp, stamp),
        )
        product_id = cur.lastrowid
        if serialized:
            for unit in units:
                conn.execute("INSERT INTO product_units(product_id,unit_code,cost,supplier,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (product_id, unit, cost, clean(data.get("supplier")), "Available", stamp, stamp))
        conn.execute("INSERT INTO restock_batches(product_id,sku,qty_added,unit_cost,old_qty,new_qty,old_average_cost,new_average_cost,supplier,note,stock_value_before,stock_value_after,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (product_id, sku, qty, cost, 0, qty, 0, cost, clean(data.get("supplier")), "Opening stock", 0, qty * cost, user["username"], stamp))
    log_audit(user["username"], user["role"], "add_product", sku, data)
    return int(product_id)


def update_product(product_id: int, data: Dict[str, Any], user: Dict[str, Any]) -> None:
    require_admin(user)
    p = query_one("SELECT * FROM products WHERE id=?", (product_id,))
    if not p:
        raise ValueError("Product not found")
    new_price=n(data.get("price") if "price" in data else p.get("price")); new_offer=n(data.get("offer_price") if "offer_price" in data else p.get("offer_price"))
    if new_price<=0: raise ValueError("Regular selling price must be greater than zero")
    if new_offer<0 or (new_offer>0 and new_offer>=new_price): raise ValueError("Offer price must be zero or lower than the regular selling price")
    stamp = now_iso()
    execute(
        """
        UPDATE products SET type=?,category=?,brand=?,model=?,color=?,ram=?,rom=?,condition=?,description=?,supplier=?,price=?,offer_price=?,low_stock=?,image_path=?,updated_at=? WHERE id=?
        """,
        (clean(data.get("type") or p["type"]), clean(data.get("category")), clean(data.get("brand")), clean(data.get("model") or p["model"]), clean(data.get("color")), clean(data.get("ram")), clean(data.get("rom")), clean(data.get("condition") or p.get("condition")), clean(data.get("description")), clean(data.get("supplier") if "supplier" in data else p.get("supplier")), new_price, new_offer, i(data.get("low_stock") or p.get("low_stock") or LOW_STOCK_DEFAULT), clean(data.get("image_path") if "image_path" in data else p.get("image_path")), stamp, product_id),
    )
    log_audit(user["username"], user["role"], "update_product", str(product_id), data)


def set_product_offer(product_id: int, offer_price: Any, user: Dict[str, Any]) -> None:
    require_admin(user)
    product=query_one("SELECT * FROM products WHERE id=?",(product_id,))
    if not product: raise ValueError("Product not found")
    offer=n(offer_price); regular=n(product.get("price"))
    if offer<0: raise ValueError("Offer price cannot be negative")
    if offer>0 and regular<=0: raise ValueError("Set a regular selling price before adding an offer")
    if offer>=regular and offer>0: raise ValueError(f"Offer price must be lower than regular price {money(regular)}")
    execute("UPDATE products SET offer_price=?,updated_at=? WHERE id=?",(offer,now_iso(),product_id))
    log_audit(user["username"],user["role"],"set_product_offer" if offer else "remove_product_offer",str(product_id),{"sku":product.get("sku"),"regular_price":regular,"offer_price":offer})


def restock_product(product_id: int, qty_or_units: Any, unit_cost: Any, supplier: str, note: str, user: Dict[str, Any]) -> int:
    require_admin(user)
    p = query_one("SELECT * FROM products WHERE id=?", (product_id,))
    if not p:
        raise ValueError("Product not found")
    stamp = now_iso()
    old_qty = int(p["quantity"] or 0)
    old_cost = n(p["cost"])
    unit_cost_f = n(unit_cost) or old_cost
    added = 0
    with get_conn() as conn:
        if p["is_serialized"]:
            units = [u.strip() for u in str(qty_or_units).replace(",", "\n").splitlines() if u.strip()]
            for unit in units:
                try:
                    conn.execute("INSERT INTO product_units(product_id,unit_code,cost,supplier,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (product_id, unit, unit_cost_f, clean(supplier) or clean(p.get("supplier")), "Available", stamp, stamp))
                    added += 1
                except sqlite3.IntegrityError:
                    pass
            new_qty = conn.execute("SELECT COUNT(*) AS c FROM product_units WHERE product_id=? AND status='Available'", (product_id,)).fetchone()["c"]
        else:
            added = max(0, i(qty_or_units))
            new_qty = old_qty + added
        new_avg = ((old_qty * old_cost) + (added * unit_cost_f)) / max(1, old_qty + added) if added > 0 else old_cost
        if p["is_serialized"]:
            conn.execute("UPDATE products SET quantity=?, cost=?, status=?, supplier=?, updated_at=? WHERE id=?", (new_qty, new_avg, "Available" if new_qty > 0 else "Out of Stock", clean(supplier) or p.get("supplier"), stamp, product_id))
        else:
            conn.execute("UPDATE products SET quantity=quantity+?, cost=?, status='Available', supplier=?, updated_at=? WHERE id=?", (added, new_avg, clean(supplier) or p.get("supplier"), stamp, product_id))
        conn.execute("INSERT INTO restock_batches(product_id,sku,qty_added,unit_cost,old_qty,new_qty,old_average_cost,new_average_cost,supplier,note,stock_value_before,stock_value_after,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (product_id, p["sku"], added, unit_cost_f, old_qty, new_qty, old_cost, new_avg, clean(supplier), clean(note), old_qty * old_cost, new_qty * new_avg, user["username"], stamp))
    log_audit(user["username"], user["role"], "restock_product", str(product_id), {"added": added, "old_qty": old_qty, "new_qty": new_qty})
    return added


def delete_product(product_id: int, user: Dict[str, Any]) -> None:
    require_admin(user)
    sales = query_one("SELECT COUNT(*) c FROM invoice_items WHERE product_id=?", (product_id,))["c"] + query_one("SELECT COUNT(*) c FROM wholesale_items WHERE product_id=?", (product_id,))["c"]
    if sales:
        raise ValueError("This product has invoice history. Keep it for financial accuracy. Set stock to 0 instead of deleting.")
    execute("DELETE FROM products WHERE id=?", (product_id,))
    log_audit(user["username"], user["role"], "delete_product", str(product_id), {})


def search_products(term: str = "", ptype: str = "All", include_empty: bool = False) -> List[Dict[str, Any]]:
    where = ["1=1"]
    params: List[Any] = []
    if ptype and ptype != "All":
        where.append("p.type=?")
        params.append(ptype)
    if not include_empty:
        where.append("p.quantity>0")
    term_clean = clean(term).lower()
    t = f"%{term_clean}%"
    if term_clean:
        # Supports normal search + last 5 digits of IMEI/serial.
        where.append("(lower(p.sku) LIKE ? OR lower(p.type) LIKE ? OR lower(p.category) LIKE ? OR lower(p.brand) LIKE ? OR lower(p.model) LIKE ? OR lower(p.color) LIKE ? OR EXISTS(SELECT 1 FROM product_units u WHERE u.product_id=p.id AND (lower(u.unit_code) LIKE ? OR lower(substr(u.unit_code, -?))=?)))")
        params += [t, t, t, t, t, t, t, len(term_clean), term_clean]
    sql = f"""
        SELECT p.*,
        CASE WHEN p.is_serialized=1 THEN (SELECT COUNT(*) FROM product_units u WHERE u.product_id=p.id AND u.status='Available') ELSE p.quantity END AS available_qty,
        CASE WHEN p.is_serialized=1 THEN (SELECT COUNT(*) FROM product_units u WHERE u.product_id=p.id AND u.status='Sold') ELSE 0 END AS sold_qty,
        CASE WHEN p.is_serialized=1 THEN (SELECT COUNT(*) FROM product_units u WHERE u.product_id=p.id AND u.status LIKE 'Wholesale:%') ELSE 0 END AS wholesale_qty
        FROM products p WHERE {' AND '.join(where)} ORDER BY p.updated_at DESC, p.id DESC LIMIT 600
    """
    return query(sql, params)


def available_units(product_id: int) -> List[Dict[str, Any]]:
    return query("SELECT * FROM product_units WHERE product_id=? AND status='Available' ORDER BY id", (product_id,))


def restock_history(product_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if product_id:
        return query("SELECT * FROM restock_batches WHERE product_id=? ORDER BY id DESC", (product_id,))
    return query("SELECT * FROM restock_batches ORDER BY id DESC LIMIT 500")


def product_unit_history(product_id: int) -> Dict[str, Any]:
    p = query_one("SELECT * FROM products WHERE id=?", (product_id,))
    if not p:
        raise ValueError("Product not found")
    units = query("""SELECT u.*, r.batch_code, r.note AS batch_note
                     FROM product_units u
                     LEFT JOIN restock_batches r ON r.id=u.purchase_batch_id
                     WHERE u.product_id=? ORDER BY u.updated_at DESC, u.id DESC""", (product_id,))
    retail = query("SELECT ii.*, i.invoice_no, i.customer_name, i.customer_whatsapp, i.created_at AS invoice_date FROM invoice_items ii LEFT JOIN invoices i ON i.id=ii.invoice_id WHERE ii.product_id=? ORDER BY ii.id DESC", (product_id,))
    wholesale = query("SELECT wi.*, w.invoice_no, w.shop_name, w.created_at AS invoice_date FROM wholesale_items wi LEFT JOIN wholesale_invoices w ON w.id=wi.wholesale_invoice_id WHERE wi.product_id=? ORDER BY wi.id DESC", (product_id,))
    batches = restock_history(product_id)
    return {"product": p, "units": units, "retail": retail, "wholesale": wholesale, "batches": batches}


def product_supplier_summary(product_id: int) -> List[Dict[str, Any]]:
    return query("""
        SELECT COALESCE(NULLIF(supplier,''),'Unknown') AS supplier,
               SUM(qty_added) AS qty_added,
               ROUND(SUM(qty_added * unit_cost) / NULLIF(SUM(qty_added),0), 2) AS avg_cost,
               SUM(qty_added * unit_cost) AS stock_value
        FROM restock_batches
        WHERE product_id=?
        GROUP BY COALESCE(NULLIF(supplier,''),'Unknown')
        ORDER BY qty_added DESC
    """, (product_id,))




def stock_detail_rows(product_id: int) -> List[Dict[str, Any]]:
    """Detailed real-world stock popup rows.

    One row per serialized unit; bulk stock appears as one live stock row plus
    sold/wholesale history rows.  Values are intentionally denormalized for the
    desktop table: id, item name, supplier, IMEI/SKU, cost, selling, profit and
    status.
    """
    d = product_unit_history(product_id)
    p = d["product"]
    retail_by_unit = {}
    for r in d.get("retail", []):
        key = clean(r.get("unit_code")) or f"retail-{r.get('id')}"
        retail_by_unit[key] = r
    wholesale_by_unit = {}
    for w in d.get("wholesale", []):
        key = clean(w.get("unit_code")) or f"wholesale-{w.get('id')}"
        wholesale_by_unit[key] = w
    rows: List[Dict[str, Any]] = []
    selling_default = n(p.get("offer_price")) or n(p.get("price"))
    if p.get("is_serialized"):
        for u in d.get("units", []):
            code = clean(u.get("unit_code"))
            r = retail_by_unit.get(code)
            w = wholesale_by_unit.get(code)
            sold_price = n(r.get("unit_price")) if r else n(w.get("selling_price")) if w else selling_default
            cost = n(u.get("cost")) or n(p.get("cost"))
            status = clean(u.get("status")) or "Available"
            if r:
                status = f"Sold - {clean(r.get('invoice_no'))}"
            elif w:
                status = f"Wholesale - {clean(w.get('shop_name'))}"
            rows.append({
                "id": u.get("id"),
                "name": product_display_name(p),
                "supplier": clean(u.get("supplier")) or clean(p.get("supplier")) or "Unknown",
                "batch": clean(u.get("batch_code")) or "Legacy / Unlinked",
                "imei": code,
                "cost": cost,
                "selling": sold_price,
                "profit": sold_price - cost if sold_price else 0,
                "status": status,
                "sold_ref": clean((r or w or {}).get("invoice_no")),
                "date": clean((r or w or u).get("invoice_date") or u.get("updated_at") or u.get("created_at")),
            })
    else:
        available_qty = i(p.get("quantity"))
        cost = n(p.get("cost"))
        supplier = clean(p.get("supplier")) or "Average / Multiple"
        rows.append({
            "id": p.get("id"),
            "name": product_display_name(p),
            "supplier": supplier,
            "batch": "Bulk stock",
            "imei": clean(p.get("sku")),
            "cost": cost,
            "selling": selling_default,
            "profit": selling_default - cost if selling_default else 0,
            "status": f"Available Bulk Qty {available_qty}",
            "sold_ref": "",
            "date": clean(p.get("updated_at")),
        })
        for r in d.get("retail", []):
            sold_price = n(r.get("unit_price"))
            unit_cost = n(r.get("unit_cost")) or cost
            rows.append({"id": f"R-{r.get('id')}", "name": r.get("product_name") or product_display_name(p), "supplier": supplier, "batch": "Bulk stock", "imei": r.get("unit_code") or p.get("sku"), "cost": unit_cost, "selling": sold_price, "profit": (sold_price-unit_cost)*i(r.get("qty") or 1), "status": f"Sold x{i(r.get('qty') or 1)}", "sold_ref": r.get("invoice_no"), "date": r.get("invoice_date")})
        for w in d.get("wholesale", []):
            sold_price = n(w.get("selling_price"))
            unit_cost = n(w.get("unit_cost")) or cost
            rows.append({"id": f"W-{w.get('id')}", "name": w.get("product_name") or product_display_name(p), "supplier": supplier, "batch": "Bulk stock", "imei": w.get("unit_code") or p.get("sku"), "cost": unit_cost, "selling": sold_price, "profit": (sold_price-unit_cost)*i(w.get("qty") or 1), "status": f"Wholesale x{i(w.get('qty') or 1)} - {w.get('shop_name')}", "sold_ref": w.get("invoice_no"), "date": w.get("invoice_date")})
    return rows

# -------------------- Customers / sales --------------------

def upsert_customer(customer: Dict[str, Any]) -> int:
    name = clean(customer.get("name")) or "Walk-in Customer"
    phone = clean(customer.get("phone"))
    whatsapp = clean(customer.get("whatsapp") or phone)
    email = clean(customer.get("email"))
    stamp = now_iso()
    row = query_one("SELECT * FROM customers WHERE (whatsapp<>'' AND whatsapp=?) OR (phone<>'' AND phone=?)", (whatsapp, phone)) if (whatsapp or phone) else None
    if row:
        execute("UPDATE customers SET name=?,phone=?,whatsapp=?,email=?,updated_at=? WHERE id=?", (name, phone, whatsapp, email, stamp, row["id"]))
        return int(row["id"])
    return execute("INSERT INTO customers(name,phone,whatsapp,email,created_at,updated_at) VALUES(?,?,?,?,?,?)", (name, phone, whatsapp, email, stamp, stamp))


def _reserve_stock(conn: sqlite3.Connection, cart: Dict[str, Any], invoice_id: int = 0, wholesale_invoice_id: int = 0, shop_id: int = 0) -> Dict[str, Any]:
    product_id = int(cart["product_id"])
    p = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p:
        raise ValueError("Product not found")
    qty = max(1, i(cart.get("qty") or 1))
    price = n(cart.get("price") or p.get("offer_price") or p.get("price"))
    discount = n(cart.get("discount"))
    unit_code = clean(cart.get("unit_code"))
    unit_id = None
    if p["is_serialized"]:
        qty = 1
        if unit_code:
            # Accept exact serial/IMEI or last digits typed by cashier.
            unit = conn.execute("SELECT * FROM product_units WHERE product_id=? AND unit_code=? AND status='Available'", (product_id, unit_code)).fetchone()
            if not unit:
                unit = conn.execute("SELECT * FROM product_units WHERE product_id=? AND substr(unit_code, -?)=? AND status='Available' ORDER BY id ASC LIMIT 1", (product_id, len(unit_code), unit_code)).fetchone()
        else:
            unit = conn.execute("SELECT * FROM product_units WHERE product_id=? AND status='Available' ORDER BY id ASC LIMIT 1", (product_id,)).fetchone()
        if not unit:
            raise ValueError(f"No available unit for {product_display_name(p)}")
        unit_id = unit["id"]
        unit_code = unit["unit_code"]
        if wholesale_invoice_id:
            conn.execute("UPDATE product_units SET status=?, shop_id=?, wholesale_invoice_id=?, updated_at=? WHERE id=?", (f"Wholesale:{shop_id}", shop_id, wholesale_invoice_id, now_iso(), unit_id))
        else:
            conn.execute("UPDATE product_units SET status='Sold', invoice_id=?, updated_at=? WHERE id=?", (invoice_id, now_iso(), unit_id))
        avail = conn.execute("SELECT COUNT(*) c FROM product_units WHERE product_id=? AND status='Available'", (product_id,)).fetchone()["c"]
        conn.execute("UPDATE products SET quantity=?, status=?, updated_at=? WHERE id=?", (avail, "Available" if avail > 0 else "Sold", now_iso(), product_id))
    else:
        if int(p["quantity"] or 0) < qty:
            raise ValueError(f"Not enough stock for {product_display_name(p)}. Available: {p['quantity']}")
        new_qty = int(p["quantity"] or 0) - qty
        conn.execute("UPDATE products SET quantity=?, status=?, updated_at=? WHERE id=?", (new_qty, "Available" if new_qty > 0 else "Out of Stock", now_iso(), product_id))
    ext_label = clean(cart.get("extended_warranty_name"))
    ext_charge = n(cart.get("extended_warranty_price")) if ext_label and ext_label != "No Extended" else 0.0
    line_total = max(0, price * qty - discount + (ext_charge * qty))
    return {
        "product_id": product_id,
        "unit_id": unit_id,
        "sku": p["sku"],
        "product_name": clean(cart.get("product_name")) or product_display_name(p),
        "unit_code": unit_code,
        "qty": qty,
        "unit_price": price,
        "unit_cost": n(p.get("cost")),
        "discount": discount,
        "line_total": line_total,
    }


def _direct_sale_item(cart: Dict[str, Any]) -> Dict[str, Any]:
    """Build an invoice item that is sold without creating inventory stock."""
    qty = max(1, i(cart.get("qty") or 1))
    name = clean(cart.get("product_name") or cart.get("name"))
    if not name:
        raise ValueError("Direct sale item name is required")
    price = n(cart.get("price") or cart.get("selling_price"))
    cost = n(cart.get("unit_cost") or cart.get("cost") or cart.get("buying_price"))
    discount = n(cart.get("discount"))
    if price <= 0:
        raise ValueError(f"Selling price must be greater than zero for direct item: {name}")
    if cost < 0:
        raise ValueError(f"Buying cost cannot be negative for direct item: {name}")
    ext_label = clean(cart.get("extended_warranty_name"))
    ext_charge = n(cart.get("extended_warranty_price")) if ext_label and ext_label != "No Extended" else 0.0
    line_total = max(0, price * qty - discount + (ext_charge * qty))
    return {
        "product_id": None,
        "unit_id": None,
        "sku": clean(cart.get("sku") or cart.get("reference") or "DIRECT"),
        "product_name": name,
        "unit_code": clean(cart.get("unit_code") or cart.get("serial") or cart.get("reference")),
        "qty": qty,
        "unit_price": price,
        "unit_cost": cost,
        "regular_price": price,
        "catalog_offer_price": 0.0,
        "offer_applied": 0,
        "offer_saving": 0.0,
        "discount": discount,
        "line_total": line_total,
        "item_source": "Direct Sale",
        "direct_supplier": clean(cart.get("direct_supplier") or cart.get("supplier") or cart.get("bought_from")),
        "buying_note": clean(cart.get("buying_note") or cart.get("note")),
    }


def create_retail_invoice(customer: Dict[str, Any], cart_items: List[Dict[str, Any]], billing: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    if not cart_items:
        raise ValueError("Cart is empty")
    stamp = now_iso()
    invoice_no = next_number("INV", "invoices", "invoice_no")
    fallback_general = clean(billing.get("general_warranty") or "No Warranty")
    fallback_general_days = billing.get("general_warranty_days")
    item_general_terms: List[Tuple[str, int, str]] = []
    item_extended_terms: List[Tuple[str, float, int, str]] = []
    for cart in cart_items:
        label = clean(cart.get("general_warranty") if "general_warranty" in cart else fallback_general) or "No Warranty"
        days = warranty_days(label, cart.get("general_warranty_days") if "general_warranty_days" in cart else fallback_general_days)
        if label != "No Warranty" and days <= 0:
            raise ValueError(f"General warranty days must be greater than zero for {clean(cart.get('product_name')) or 'an item'}")
        item_general_terms.append((label, days, date_add(days)))
        ext_label = clean(cart.get("extended_warranty_name"))
        ext_price = n(cart.get("extended_warranty_price"))
        if ext_price < 0:
            raise ValueError(f"Extended warranty amount cannot be negative for {clean(cart.get('product_name')) or 'an item'}")
        if not ext_label or ext_label == "No Extended":
            ext_label, ext_price, ext_days = "", 0.0, 0
        else:
            ext_days = warranty_days(ext_label, cart.get("extended_warranty_days"))
            if ext_days <= 0:
                raise ValueError(f"Extended warranty days must be greater than zero for {clean(cart.get('product_name')) or 'an item'}")
        item_extended_terms.append((ext_label, ext_price, ext_days, date_add(ext_days)))
    common_terms = set(item_general_terms)
    if len(common_terms) == 1:
        general_label, general_days, general_expire = item_general_terms[0]
    else:
        general_label, general_days, general_expire = "Per-item warranties", 0, ""
    payments = normalize_payments(billing.get("payments") or [])
    customer_id = upsert_customer(customer)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO invoices(invoice_no,customer_id,customer_name,customer_phone,customer_whatsapp,customer_email,payments_json,general_warranty,general_warranty_days,general_warranty_expire,note,created_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (invoice_no, customer_id, clean(customer.get("name")) or "Walk-in Customer", clean(customer.get("phone")), clean(customer.get("whatsapp") or customer.get("phone")), clean(customer.get("email")), json.dumps(payments), general_label, general_days, general_expire, clean(billing.get("note")), user["username"], stamp, stamp),
        )
        invoice_id = int(cur.lastrowid)
        subtotal = 0.0
        ext_total = 0.0
        for cart, (item_general_label, item_general_days, item_general_expire), (ext_name, ext_price, ext_days, ext_expire) in zip(cart_items, item_general_terms, item_extended_terms):
            item = _direct_sale_item(cart) if cart.get("direct_sale") or cart.get("item_source") == "Direct Sale" or not cart.get("product_id") else _reserve_stock(conn, cart, invoice_id=invoice_id)
            ext_total += ext_price * item["qty"]
            subtotal += item["unit_price"] * item["qty"] - item["discount"]
            conn.execute(
                """INSERT INTO invoice_items(invoice_id,product_id,unit_id,sku,product_name,unit_code,qty,unit_price,unit_cost,regular_price,catalog_offer_price,offer_applied,offer_saving,discount,item_source,direct_supplier,buying_note,extended_warranty_name,extended_warranty_price,extended_warranty_days,extended_warranty_expire,general_warranty,general_warranty_days,general_warranty_expire,warranty_note,line_total,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (invoice_id, item["product_id"], item["unit_id"], item["sku"], item["product_name"], item["unit_code"], item["qty"], item["unit_price"], item["unit_cost"], item["regular_price"], item["catalog_offer_price"], item["offer_applied"], item["offer_saving"], item["discount"], item.get("item_source") or "Inventory", item.get("direct_supplier") or "", item.get("buying_note") or "", ext_name, ext_price, ext_days, ext_expire, item_general_label, item_general_days, item_general_expire, clean(cart.get("warranty_note")), item["line_total"], stamp),
            )
        discount = n(billing.get("discount"))
        grand = max(0, subtotal + ext_total - discount)
        paid = min(payment_total(payments), grand)
        balance = max(0, grand - paid)
        conn.execute("UPDATE invoices SET subtotal=?,discount=?,extended_warranty_total=?,grand_total=?,paid_total=?,balance=?,payment_status=?,updated_at=? WHERE id=?", (subtotal, discount, ext_total, grand, paid, balance, payment_status(grand, paid), stamp, invoice_id))
    log_audit(user["username"], user["role"], "create_retail_invoice", invoice_no, {"total": grand, "paid": paid, "balance": balance})
    return get_invoice(invoice_id)


def set_invoice_pdf(invoice_id: int, pdf_path: str) -> None:
    execute("UPDATE invoices SET pdf_path=?, updated_at=? WHERE id=?", (str(pdf_path), now_iso(), invoice_id))


def list_invoices(limit: int = 500) -> List[Dict[str, Any]]:
    return query("SELECT * FROM invoices WHERE status='Active' ORDER BY id DESC LIMIT ?", (limit,))


def get_invoice(invoice_id: int) -> Dict[str, Any]:
    inv = query_one("SELECT * FROM invoices WHERE id=?", (invoice_id,))
    if not inv:
        raise ValueError("Invoice not found")
    inv["items"] = query("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id", (invoice_id,))
    inv["payments"] = parse_json(inv.get("payments_json"), [])
    return inv


def list_customers() -> List[Dict[str, Any]]:
    return query("SELECT c.*, (SELECT COUNT(*) FROM invoices i WHERE i.customer_id=c.id AND i.status='Active') invoice_count, (SELECT COALESCE(SUM(balance),0) FROM invoices i WHERE i.customer_id=c.id AND i.status='Active') due_total FROM customers c ORDER BY c.updated_at DESC LIMIT 500")


def customer_invoices(customer_id: int) -> List[Dict[str, Any]]:
    return query("SELECT * FROM invoices WHERE customer_id=? AND status='Active' ORDER BY id DESC", (customer_id,))


def delete_invoice(invoice_id: int, user: Dict[str, Any]) -> None:
    require_admin(user)
    inv = get_invoice(invoice_id)
    stamp = now_iso()
    with get_conn() as conn:
        for item in inv["items"]:
            if item.get("unit_id"):
                conn.execute("UPDATE product_units SET status='Available', invoice_id=NULL, updated_at=? WHERE id=?", (stamp, item["unit_id"]))
                _refresh_product_stock(conn, item["product_id"])
            elif item.get("product_id"):
                conn.execute("UPDATE products SET quantity=quantity+?, status='Available', updated_at=? WHERE id=?", (item["qty"], stamp, item["product_id"]))
        conn.execute("UPDATE invoices SET status='Deleted', updated_at=? WHERE id=?", (stamp, invoice_id))
    log_audit(user["username"], user["role"], "delete_invoice_restore_stock", inv["invoice_no"], {})


# -------------------- Wholesale / partners --------------------

def add_shop(data: Dict[str, Any], user: Dict[str, Any]) -> int:
    stamp = now_iso()
    name = clean(data.get("name"))
    if not name:
        raise ValueError("Shop name is required")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM shops WHERE name=?", (name,)).fetchone()
        if row:
            conn.execute("UPDATE shops SET contact_person=?,phone=?,whatsapp=?,email=?,address=?,credit_limit=?,notes=?,active=1,updated_at=? WHERE id=?", (clean(data.get("contact_person")), clean(data.get("phone")), clean(data.get("whatsapp") or data.get("phone")), clean(data.get("email")), clean(data.get("address")), n(data.get("credit_limit")), clean(data.get("notes")), stamp, row["id"]))
            sid = int(row["id"])
        else:
            cur = conn.execute("INSERT INTO shops(name,contact_person,phone,whatsapp,email,address,credit_limit,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (name, clean(data.get("contact_person")), clean(data.get("phone")), clean(data.get("whatsapp") or data.get("phone")), clean(data.get("email")), clean(data.get("address")), n(data.get("credit_limit")), clean(data.get("notes")), stamp, stamp))
            sid = int(cur.lastrowid)
    log_audit(user["username"], user["role"], "save_shop", name, data)
    return sid


def list_shops() -> List[Dict[str, Any]]:
    return query("""SELECT s.*,
        (SELECT COALESCE(SUM(grand_total),0) FROM wholesale_invoices wi WHERE wi.shop_id=s.id AND wi.status<>'Deleted') issued_total,
        (SELECT COALESCE(SUM(paid_total),0) FROM wholesale_invoices wi WHERE wi.shop_id=s.id AND wi.status<>'Deleted') paid_total,
        (SELECT COALESCE(SUM(balance),0) FROM wholesale_invoices wi WHERE wi.shop_id=s.id AND wi.status<>'Deleted') due_total,
        (SELECT COUNT(*) FROM wholesale_invoices wi WHERE wi.shop_id=s.id AND wi.status<>'Deleted') invoice_count
        FROM shops s WHERE active=1 ORDER BY s.updated_at DESC,s.name""")


def create_wholesale_invoice(shop_id: int, cart_items: List[Dict[str, Any]], billing: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    if not cart_items:
        raise ValueError("Wholesale cart is empty")
    shop = query_one("SELECT * FROM shops WHERE id=?", (shop_id,))
    if not shop:
        raise ValueError("Shop not found")
    stamp = now_iso()
    invoice_no = next_number("WS", "wholesale_invoices", "invoice_no")
    payments = normalize_payments(billing.get("payments") or [])
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO wholesale_invoices(invoice_no,shop_id,shop_name,initial_payments_json,note,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (invoice_no, shop_id, shop["name"], json.dumps(payments), clean(billing.get("note")), user["username"], stamp, stamp))
        wid = int(cur.lastrowid)
        subtotal = 0.0
        for cart in cart_items:
            item = _reserve_stock(conn, cart, invoice_id=0, wholesale_invoice_id=wid, shop_id=shop_id)
            subtotal += item["line_total"]
            conn.execute("INSERT INTO wholesale_items(wholesale_invoice_id,product_id,unit_id,sku,product_name,unit_code,qty,unit_cost,selling_price,line_total,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (wid, item["product_id"], item["unit_id"], item["sku"], item["product_name"], item["unit_code"], item["qty"], item["unit_cost"], item["unit_price"], item["line_total"], stamp))
        discount = n(billing.get("discount"))
        grand = max(0, subtotal - discount)
        paid = min(payment_total(payments), grand)
        bal = max(0, grand - paid)
        conn.execute("UPDATE wholesale_invoices SET subtotal=?,discount=?,grand_total=?,paid_total=?,balance=?,payment_status=?,status=?,updated_at=? WHERE id=?", (subtotal, discount, grand, paid, bal, payment_status(grand, paid), "Paid" if bal <= 0 else "Open", stamp, wid))
    if paid > 0:
        add_wholesale_payment(shop_id, payments, f"Initial payment for {invoice_no}", user, direct_invoice_id=wid, already_applied=True)
    log_audit(user["username"], user["role"], "create_wholesale_invoice", invoice_no, {"total": grand, "paid": paid, "balance": bal})
    return get_wholesale_invoice(wid)


def get_wholesale_invoice(wid: int) -> Dict[str, Any]:
    inv = query_one("SELECT * FROM wholesale_invoices WHERE id=?", (wid,))
    if not inv:
        raise ValueError("Wholesale invoice not found")
    inv["items"] = query("SELECT * FROM wholesale_items WHERE wholesale_invoice_id=? ORDER BY id", (wid,))
    inv["shop"] = query_one("SELECT * FROM shops WHERE id=?", (inv["shop_id"],))
    inv["initial_payments"] = parse_json(inv.get("initial_payments_json"), [])
    return inv


def list_wholesale_invoices(shop_id: Optional[int] = None) -> List[Dict[str, Any]]:
    if shop_id:
        return query("SELECT * FROM wholesale_invoices WHERE shop_id=? AND status<>'Deleted' ORDER BY id DESC", (shop_id,))
    return query("SELECT * FROM wholesale_invoices WHERE status<>'Deleted' ORDER BY id DESC LIMIT 500")


def add_wholesale_payment(shop_id: int, payment_rows: List[Dict[str, Any]], note: str, user: Dict[str, Any], direct_invoice_id: Optional[int] = None, already_applied: bool = False) -> Dict[str, Any]:
    payments = normalize_payments(payment_rows)
    amount = payment_total(payments)
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero")
    stamp = now_iso()
    payment_no = next_number("WSP", "wholesale_payments", "payment_no")
    remaining = amount
    allocations = []
    with get_conn() as conn:
        if already_applied and direct_invoice_id:
            inv = conn.execute("SELECT * FROM wholesale_invoices WHERE id=?", (direct_invoice_id,)).fetchone()
            allocations.append({"invoice_id": direct_invoice_id, "invoice_no": inv["invoice_no"] if inv else "Direct", "before": n(inv["balance"]) + amount if inv else amount, "applied": amount, "after": n(inv["balance"]) if inv else 0, "mode": "initial-direct"})
            remaining = 0
        else:
            invoices: List[Dict[str, Any]] = []
            if direct_invoice_id:
                invoices += conn.execute("SELECT * FROM wholesale_invoices WHERE id=? AND shop_id=? AND status<>'Deleted' AND balance>0", (direct_invoice_id, shop_id)).fetchall()
            invoices += conn.execute("SELECT * FROM wholesale_invoices WHERE shop_id=? AND status<>'Deleted' AND balance>0 AND id<>COALESCE(?,0) ORDER BY created_at ASC, id ASC", (shop_id, direct_invoice_id or 0)).fetchall()
            for inv in invoices:
                if remaining <= 0:
                    break
                before = n(inv["balance"])
                applied = min(before, remaining)
                after = max(0, before - applied)
                paid_total = n(inv["paid_total"]) + applied
                status = "Paid" if after <= 0 else "Open"
                pstat = payment_status(n(inv["grand_total"]), paid_total)
                conn.execute("UPDATE wholesale_invoices SET paid_total=?,balance=?,payment_status=?,status=?,updated_at=? WHERE id=?", (paid_total, after, pstat, status, stamp, inv["id"]))
                allocations.append({"invoice_id": inv["id"], "invoice_no": inv["invoice_no"], "before": before, "applied": applied, "after": after, "mode": "direct" if direct_invoice_id and inv["id"] == direct_invoice_id else "fifo-oldest"})
                remaining -= applied
            if remaining > 0:
                allocations.append({"invoice_id": None, "invoice_no": "Advance Credit", "before": 0, "applied": remaining, "after": 0, "mode": "advance"})
        conn.execute("INSERT INTO wholesale_payments(payment_no,shop_id,amount,payments_json,note,allocations_json,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)", (payment_no, shop_id, amount, json.dumps(payments), clean(note), json.dumps(allocations), user["username"], stamp))
    log_audit(user["username"], user["role"], "wholesale_payment", payment_no, {"amount": amount, "allocations": allocations})
    return {"payment_no": payment_no, "amount": amount, "payments": payments, "allocations": allocations}


def set_wholesale_pdf(wid: int, pdf_path: str) -> None:
    execute("UPDATE wholesale_invoices SET pdf_path=?, updated_at=? WHERE id=?", (str(pdf_path), now_iso(), wid))


def shop_profile(shop_id: int) -> Dict[str, Any]:
    shop = query_one("SELECT * FROM shops WHERE id=?", (shop_id,))
    if not shop:
        raise ValueError("Shop not found")
    invoices = list_wholesale_invoices(shop_id)
    payments = query("SELECT * FROM wholesale_payments WHERE shop_id=? ORDER BY id DESC", (shop_id,))
    for p in payments:
        p["payments"] = parse_json(p.get("payments_json"), [])
        p["allocations"] = parse_json(p.get("allocations_json"), [])
        p["method_summary"] = payment_summary(p["payments"])
        p["method_lines"] = [
            {
                "method": clean(row.get("method")) or "Unknown",
                "amount": n(row.get("amount")),
                "reference": clean(row.get("reference")),
                "created_at": row.get("created_at") or p.get("created_at"),
            }
            for row in p["payments"]
        ]
    all_items = query(
        """SELECT wii.*, wi.invoice_no, wi.created_at AS invoice_date
             FROM wholesale_items wii
             JOIN wholesale_invoices wi ON wi.id=wii.wholesale_invoice_id
             WHERE wi.shop_id=? AND wi.status<>'Deleted'
             ORDER BY wi.id DESC,wii.id""",
        (shop_id,),
    )
    items_by_invoice: Dict[int, List[Dict[str, Any]]] = {}
    for item in all_items:
        items_by_invoice.setdefault(int(item["wholesale_invoice_id"]), []).append(item)
    allocations_by_invoice: Dict[int, List[Dict[str, Any]]] = {}
    for p in payments:
        for allocation in p.get("allocations", []):
            invoice_id = i(allocation.get("invoice_id"))
            if not invoice_id:
                continue
            detail = dict(allocation)
            detail.update({
                "payment_no": p.get("payment_no"),
                "payment_date": p.get("created_at"),
                "payment_amount": p.get("amount"),
                "payment_methods": p.get("method_summary"),
                "payment_note": p.get("note"),
            })
            allocations_by_invoice.setdefault(invoice_id, []).append(detail)
    for inv in invoices:
        invoice_id = int(inv["id"])
        inv["items"] = items_by_invoice.get(invoice_id, [])
        inv["item_count"] = len(inv["items"])
        inv["total_qty"] = sum(i(item.get("qty")) for item in inv["items"])
        inv["payment_allocations"] = sorted(allocations_by_invoice.get(invoice_id, []), key=lambda x: str(x.get("payment_date") or ""))
        inv["paid_percent"] = min(100.0, (n(inv.get("paid_total")) / n(inv.get("grand_total")) * 100.0) if n(inv.get("grand_total")) else 0.0)
        inv["last_payment_date"] = inv["payment_allocations"][-1].get("payment_date") if inv["payment_allocations"] else ""
    payment_log = []
    for p in payments:
        allocation_summary = "; ".join([f"{a.get('invoice_no')} {money(a.get('applied'))} (due {money(a.get('after'))})" for a in p.get("allocations", [])]) or "-"
        method_detail = "; ".join([
            f"{m.get('method')} {money(m.get('amount'))}" + (f" ref {m.get('reference')}" if m.get("reference") else "")
            for m in p.get("method_lines", [])
        ]) or p.get("method_summary") or "-"
        payment_log.append({
            "payment_no": p.get("payment_no"),
            "created_at": p.get("created_at"),
            "amount": n(p.get("amount")),
            "method_summary": p.get("method_summary"),
            "method_detail": method_detail,
            "note": p.get("note") or "",
            "allocations": allocation_summary,
            "created_by": p.get("created_by"),
        })
    due_items = query(
        """SELECT wi.invoice_no, wi.created_at, wi.balance, wii.product_name, wii.unit_code, wii.qty, wii.selling_price, wii.line_total
             FROM wholesale_items wii JOIN wholesale_invoices wi ON wi.id=wii.wholesale_invoice_id
             WHERE wi.shop_id=? AND wi.status<>'Deleted' AND wi.balance>0
             ORDER BY wi.created_at ASC, wi.id ASC""",
        (shop_id,),
    )
    units = query(
        """SELECT pu.*, p.sku, p.brand, p.model, p.type, wi.invoice_no, wi.created_at AS issued_at
             FROM product_units pu JOIN products p ON p.id=pu.product_id
             LEFT JOIN wholesale_invoices wi ON wi.id=pu.wholesale_invoice_id
             WHERE pu.shop_id=? ORDER BY pu.updated_at DESC""",
        (shop_id,),
    )
    total_issued = sum(n(x["grand_total"]) for x in invoices)
    total_paid = sum(n(x["paid_total"]) for x in invoices)
    balance = sum(n(x["balance"]) for x in invoices)
    paid_percent = min(100.0, (total_paid / total_issued * 100.0) if total_issued else 0.0)
    outstanding_invoices=[inv for inv in invoices if n(inv.get("balance"))>0]
    settled_invoices=[inv for inv in invoices if n(inv.get("balance"))<=0]
    return {"shop": shop, "invoices": invoices, "outstanding_invoices":outstanding_invoices, "settled_invoices":settled_invoices, "payments": payments, "payment_log": payment_log, "due_items": due_items, "units": units, "all_items": all_items, "total_issued": total_issued, "total_paid": total_paid, "balance": balance, "paid_percent": paid_percent}


def shop_statement_text(shop_id: int) -> str:
    prof = shop_profile(shop_id)
    shop = prof["shop"]
    lines = [f"{get_setting('company_name','ICON MOBILE')} - Partner Shop Statement", f"Shop: {shop['name']}", f"WhatsApp: {shop.get('whatsapp') or shop.get('phone') or ''}", f"Date: {now_iso()}", "", f"TOTAL DUE: {money(prof['balance'])}", "", "Due Items:"]
    if not prof["due_items"]:
        lines.append("- No due items. Account is clear.")
    else:
        for item in prof["due_items"][:80]:
            lines.append(f"- {item['invoice_no']} | {item['product_name']} {item.get('unit_code') or ''} x{item['qty']} | Line {money(item['line_total'])} | Invoice Due {money(item['balance'])}")
    lines += ["", "Open Invoices:"]
    for inv in prof["invoices"][:60]:
        if n(inv["balance"]) > 0:
            lines.append(f"- {inv['invoice_no']} | Total {money(inv['grand_total'])} | Paid {money(inv['paid_total'])} | Due {money(inv['balance'])}")
    lines += ["", f"Total Issued: {money(prof['total_issued'])}", f"Total Paid: {money(prof['total_paid'])}", f"Total Due: {money(prof['balance'])}", "", "Please settle the due amount. Thank you."]
    return "\n".join(lines)


def client_statement_text(invoice_id: int) -> str:
    inv = get_invoice(invoice_id)
    lines = [f"{get_setting('company_name','ICON MOBILE')} - Invoice {inv['invoice_no']}", f"Customer: {inv['customer_name']}", f"WhatsApp: {inv.get('customer_whatsapp') or inv.get('customer_phone') or ''}", f"Date: {inv['created_at']}", "", "Items:"]
    for item in inv["items"]:
        lines.append(f"- {item['product_name']} {item.get('unit_code') or ''} x{item['qty']} = {money(item['line_total'])}")
        if item.get("general_warranty"):
            lines.append(f"  General warranty: {item['general_warranty']} | Expire: {item.get('general_warranty_expire') or 'N/A'}")
        if item.get("extended_warranty_name") or n(item.get("extended_warranty_price")):
            lines.append(f"  Extended warranty: {item.get('extended_warranty_name') or 'Extended'} {money(item.get('extended_warranty_price'))} | Expire: {item.get('extended_warranty_expire') or 'N/A'}")
        if item.get("warranty_note"):
            lines.append(f"  Warranty note: {item.get('warranty_note')}")
    lines += ["", f"Subtotal: {money(inv['subtotal'])}", f"Extended Warranty: {money(inv['extended_warranty_total'])}", f"Discount: {money(inv['discount'])}", f"Total: {money(inv['grand_total'])}", f"Paid: {money(inv['paid_total'])}", f"Balance: {money(inv['balance'])}", f"Payment: {payment_summary(inv['payments'])}", "", "Thank you."]
    return "\n".join(lines)


# -------------------- Finance / reports --------------------

def _date_start(period: str) -> str:
    now = datetime.now()
    if period == "today":
        return now.strftime("%Y-%m-%d 00:00:00")
    if period == "year":
        return now.strftime("%Y-01-01 00:00:00")
    return now.strftime("%Y-%m-01 00:00:00")


def _parse_yyyy_mm_dd(value: Any, fallback: Optional[datetime] = None) -> datetime:
    text = clean(value)
    if not text:
        if fallback is not None:
            return fallback
        raise ValueError("Date is required in YYYY-MM-DD format")
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Date must use YYYY-MM-DD format, for example 2026-07-07. Invalid: {text}")


def _date_range(period: str = "month", selected_month: str = "", date_from: str = "", date_to: str = "") -> Tuple[str, str, str]:
    """Return an inclusive start, exclusive end and display label."""
    now = datetime.now()
    mode = clean(period).lower()
    if mode in {"today", "daily", "day", "date"}:
        chosen = _parse_yyyy_mm_dd(date_from, datetime(now.year, now.month, now.day)) if clean(date_from) else datetime(now.year, now.month, now.day)
        start = datetime(chosen.year, chosen.month, chosen.day)
        end = start + timedelta(days=1)
        label = start.strftime("%d %B %Y")
    elif mode in {"week", "weekly"}:
        chosen = _parse_yyyy_mm_dd(date_from, datetime(now.year, now.month, now.day)) if clean(date_from) else datetime(now.year, now.month, now.day)
        start_day = chosen - timedelta(days=chosen.weekday())
        start = datetime(start_day.year, start_day.month, start_day.day)
        end = start + timedelta(days=7)
        label = f"Week {start.strftime('%Y-%m-%d')} to {(end - timedelta(days=1)).strftime('%Y-%m-%d')}"
    elif mode in {"year", "annual", "annually"}:
        year = now.year
        if clean(date_from):
            year = _parse_yyyy_mm_dd(date_from).year
        elif clean(selected_month) and len(clean(selected_month)) >= 4:
            try:
                year = int(clean(selected_month)[:4])
            except ValueError:
                year = now.year
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)
        label = f"Annual Sales {year}"
    elif mode in {"custom", "range", "specific"}:
        start_day = _parse_yyyy_mm_dd(date_from)
        end_day = _parse_yyyy_mm_dd(date_to, start_day) if clean(date_to) else start_day
        if end_day < start_day:
            raise ValueError("Date To cannot be before Date From")
        start = datetime(start_day.year, start_day.month, start_day.day)
        end = datetime(end_day.year, end_day.month, end_day.day) + timedelta(days=1)
        label = start.strftime("%Y-%m-%d") if start_day == end_day else f"{start.strftime('%Y-%m-%d')} to {end_day.strftime('%Y-%m-%d')}"
    else:
        try:
            chosen = datetime.strptime(clean(selected_month), "%Y-%m") if clean(selected_month) else now
        except ValueError:
            raise ValueError("Month must use YYYY-MM format, for example 2026-07")
        start = datetime(chosen.year, chosen.month, 1)
        end = datetime(chosen.year + (1 if chosen.month == 12 else 0), 1 if chosen.month == 12 else chosen.month + 1, 1)
        label = start.strftime("%B %Y")
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S"), label


def _payments_by_method(retail_invoices: List[Dict[str, Any]], wholesale_payments: List[Dict[str, Any]]) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    for inv in retail_invoices:
        for p in parse_json(inv.get("payments_json"), []):
            totals[p.get("method") or "Unknown"] = totals.get(p.get("method") or "Unknown", 0) + n(p.get("amount"))
    for pay in wholesale_payments:
        for p in parse_json(pay.get("payments_json"), []):
            totals[p.get("method") or "Unknown"] = totals.get(p.get("method") or "Unknown", 0) + n(p.get("amount"))
    return totals


def financial_dashboard(period: str = "month", admin: bool = True, selected_month: str = "", date_from: str = "", date_to: str = "") -> Dict[str, Any]:
    start, end, period_label = _date_range(period, selected_month, date_from, date_to)
    retail_invoices = query("SELECT * FROM invoices WHERE status='Active' AND created_at>=? AND created_at<?", (start, end))
    wholesale_invoices = query("SELECT * FROM wholesale_invoices WHERE status<>'Deleted' AND created_at>=? AND created_at<?", (start, end))
    wholesale_payments = query("SELECT * FROM wholesale_payments WHERE created_at>=? AND created_at<?", (start, end))
    retail_rev = sum(n(x["grand_total"]) for x in retail_invoices)
    retail_paid = sum(n(x["paid_total"]) for x in retail_invoices)
    wh_rev = sum(n(x["grand_total"]) for x in wholesale_invoices)
    wh_paid = sum(n(x["amount"]) for x in wholesale_payments)
    cogs_row = query_one("""SELECT COALESCE(SUM(unit_cost*qty),0) cogs FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE i.status='Active' AND i.created_at>=? AND i.created_at<?""", (start, end))
    wh_cogs_row = query_one("""SELECT COALESCE(SUM(unit_cost*qty),0) cogs FROM wholesale_items wi JOIN wholesale_invoices w ON w.id=wi.wholesale_invoice_id WHERE w.status<>'Deleted' AND w.created_at>=? AND w.created_at<?""", (start, end))
    cogs = n(cogs_row["cogs"]) + n(wh_cogs_row["cogs"])
    stock_assets = query_one("SELECT COALESCE(SUM(cost*quantity),0) assets, COALESCE(SUM(quantity),0) qty FROM products", ())
    receivable = query_one("SELECT COALESCE(SUM(balance),0) retail_due FROM invoices WHERE status='Active'", ())
    wh_receivable = query_one("SELECT COALESCE(SUM(balance),0) wh_due FROM wholesale_invoices WHERE status<>'Deleted'", ())
    gross_revenue = retail_rev + wh_rev
    paid_cashflow = retail_paid + wh_paid
    gross_profit = gross_revenue - cogs
    low_stock = query("SELECT * FROM products WHERE quantity<=low_stock ORDER BY quantity ASC, updated_at DESC LIMIT 50")
    daily_rows = query("""
        SELECT label,SUM(total) total FROM (
            SELECT substr(created_at,1,10) label,grand_total total FROM invoices
             WHERE status='Active' AND created_at>=? AND created_at<?
            UNION ALL
            SELECT substr(created_at,1,10) label,grand_total total FROM wholesale_invoices
             WHERE status<>'Deleted' AND created_at>=? AND created_at<?
        ) GROUP BY label ORDER BY label
    """, (start, end, start, end))
    daily_totals = {str(row["label"]): n(row["total"]) for row in daily_rows}
    range_start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
    range_end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
    now = datetime.now()
    chart_end = min(range_end, datetime(now.year, now.month, now.day) + timedelta(days=1)) if range_start <= now else range_start
    daily = []
    cursor = range_start
    while cursor < chart_end:
        label = cursor.strftime("%Y-%m-%d")
        daily.append({"label": label, "total": daily_totals.get(label, 0.0)})
        cursor += timedelta(days=1)
    wh_daily = query("""SELECT substr(created_at,1,10) label, SUM(grand_total) total FROM wholesale_invoices WHERE status<>'Deleted' AND created_at>=? AND created_at<? GROUP BY label ORDER BY label""", (start, end))
    monthly = query("""
        SELECT label,SUM(total) total FROM (
            SELECT substr(created_at,1,7) label,grand_total total FROM invoices WHERE status='Active'
            UNION ALL SELECT substr(created_at,1,7),grand_total FROM wholesale_invoices WHERE status<>'Deleted'
        ) GROUP BY label ORDER BY label DESC LIMIT 12
    """, ())
    restocks = query("SELECT * FROM restock_batches WHERE created_at>=? AND created_at<? ORDER BY id DESC LIMIT 100", (start, end))
    retail_pay_rows = query("SELECT payments_json FROM invoices WHERE status='Active' AND created_at>=? AND created_at<?", (start, end))
    pay_methods = _payments_by_method(retail_pay_rows, wholesale_payments)
    top_items = query("""
        SELECT product_name,SUM(qty) qty,SUM(total) total,SUM(cost) cost FROM (
            SELECT ii.product_name,ii.qty,ii.line_total total,ii.unit_cost*ii.qty cost
              FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id
             WHERE i.status='Active' AND i.created_at>=? AND i.created_at<?
            UNION ALL
            SELECT wi.product_name,wi.qty,wi.line_total,wi.unit_cost*wi.qty
              FROM wholesale_items wi JOIN wholesale_invoices w ON w.id=wi.wholesale_invoice_id
             WHERE w.status<>'Deleted' AND w.created_at>=? AND w.created_at<?
        ) GROUP BY product_name ORDER BY qty DESC LIMIT 100
    """, (start, end, start, end))
    income_details = query("""
        SELECT * FROM (
            SELECT 'Retail' source,invoice_no reference,customer_name party,created_at,grand_total total,paid_total paid,balance due,payment_status
              FROM invoices WHERE status='Active' AND created_at>=? AND created_at<?
            UNION ALL
            SELECT 'Partner' source,invoice_no reference,shop_name party,created_at,grand_total total,paid_total paid,balance due,payment_status
              FROM wholesale_invoices WHERE status<>'Deleted' AND created_at>=? AND created_at<?
        ) ORDER BY created_at DESC,reference DESC
    """, (start, end, start, end))
    return {
        "period": period,
        "period_label": period_label,
        "start": start,
        "end": end,
        "retail_revenue": retail_rev,
        "retail_paid": retail_paid,
        "wholesale_revenue": wh_rev,
        "wholesale_paid": wh_paid,
        "gross_revenue": gross_revenue,
        "paid_cashflow": paid_cashflow,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "stock_assets": n(stock_assets["assets"]),
        "stock_qty": n(stock_assets["qty"]),
        "retail_receivable": n(receivable["retail_due"]),
        "wholesale_receivable": n(wh_receivable["wh_due"]),
        "total_receivable": n(receivable["retail_due"]) + n(wh_receivable["wh_due"]),
        "payment_methods": pay_methods,
        "daily": daily,
        "wh_daily": wh_daily,
        "monthly": monthly,
        "low_stock": low_stock,
        "restocks": restocks,
        "top_items": top_items,
        "income_details": income_details,
    }


def staff_sold_items_month() -> List[Dict[str, Any]]:
    start = datetime.now().strftime("%Y-%m-01 00:00:00")
    return query("""SELECT ii.product_name, ii.sku, SUM(ii.qty) qty, COUNT(DISTINCT i.id) invoices FROM invoice_items ii JOIN invoices i ON i.id=ii.invoice_id WHERE i.status='Active' AND i.created_at>=? GROUP BY ii.product_name, ii.sku ORDER BY qty DESC LIMIT 200""", (start,))


def export_csv(path: Path, rows: List[Dict[str, Any]]) -> str:
    if not rows:
        path.write_text("No data\n", encoding="utf-8")
        return str(path)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return str(path)


# -------------------- Backup / WhatsApp --------------------

def export_backup(user: Optional[Dict[str, Any]] = None) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = BACKUP_DIR / f"ICON_MOBILE_BACKUP_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if DB_PATH.exists():
            z.write(DB_PATH, "data/icon_mobile_system.sqlite3")
        for p in INVOICE_DIR.rglob("*.pdf"):
            z.write(p, f"invoices/{p.name}")
    set_setting("last_backup_at", now_iso())
    if user:
        log_audit(user["username"], user["role"], "backup_export", str(zip_path), {})
    return str(zip_path)


def restore_backup(zip_file: str, user: Dict[str, Any]) -> None:
    require_admin(user)
    backup_before = export_backup(user)
    with zipfile.ZipFile(zip_file, "r") as z:
        for name in z.namelist():
            if name.endswith(".sqlite3"):
                tmp = DB_PATH.with_suffix(".restore_tmp")
                with z.open(name) as src, tmp.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                shutil.move(str(tmp), str(DB_PATH))
            elif name.startswith("invoices/") and name.endswith(".pdf"):
                z.extract(name, DB_PATH.parent.parent)
    log_audit(user["username"], user["role"], "backup_restore", str(zip_file), {"backup_before": backup_before})


def backup_due() -> bool:
    last = get_setting("last_backup_at", "")
    if not last:
        return True
    try:
        dt = datetime.strptime(last[:19], "%Y-%m-%d %H:%M:%S")
        return datetime.now() - dt >= timedelta(days=7)
    except Exception:
        return True


def whatsapp_url(phone: str, text: str) -> str:
    return f"https://wa.me/{normalize_phone(phone)}?text={quote(text)}"


def open_path(path: str) -> None:
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    try:
        if os.name == "nt":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)], check=False)
        else:
            webbrowser.open(p.as_uri())
    except Exception:
        webbrowser.open(p.as_uri())


# -------------------- Sync helpers --------------------

def sync_password_ok(password: str) -> bool:
    return clean(password) == get_setting("sync_password", SYNC_PASSWORD)

# -------------------- V6 real-world inventory core override --------------------
# These final definitions intentionally override the earlier helpers above.
# V6 tracking rule: staff do not choose Serialized/Bulk.  If IMEI/serial lines
# exist, the product is exact-unit tracked.  If no lines exist, phones/laptops/
# tablets/watches can receive auto internal IDs; accessories stay quantity stock.
UNIT_TRACKED_TYPES = {"phone", "laptop", "tablet", "smartwatch", "wearable", "watch", "gaming"}


def _normal_unit_codes(value: Any) -> List[str]:
    raw = str(value or "").replace(",", "\n")
    out: List[str] = []
    seen = set()
    for line in raw.splitlines():
        code = clean(line)
        if not code or code.startswith("#"):
            continue
        key = code.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(code)
    return out


def _needs_unit_tracking(type_value: Any, category: Any = "") -> bool:
    t = clean(type_value).lower()
    c = clean(category).lower()
    if t in UNIT_TRACKED_TYPES:
        return True
    if any(word in c for word in ["phone", "iphone", "mobile", "laptop", "watch", "tablet", "console"]):
        return True
    return False


def _auto_unit_codes(sku: str, qty: int) -> List[str]:
    return generate_internal_ids(qty)


def _serial_exists_global(conn: sqlite3.Connection, code: str, exclude_product_id: int = 0) -> bool:
    if exclude_product_id:
        row = conn.execute("SELECT id FROM product_units WHERE lower(unit_code)=lower(?) AND product_id<>? LIMIT 1", (code, exclude_product_id)).fetchone()
    else:
        row = conn.execute("SELECT id FROM product_units WHERE lower(unit_code)=lower(?) LIMIT 1", (code,)).fetchone()
    return bool(row)


def _resolve_available_unit(conn: sqlite3.Connection, product_id: int, typed: str = "") -> Optional[Dict[str, Any]]:
    typed = clean(typed)
    if typed:
        unit = conn.execute("SELECT * FROM product_units WHERE product_id=? AND unit_code=? AND status='Available'", (product_id, typed)).fetchone()
        if unit:
            return unit
        # Last-N digit/character selection.  Works for last 5 IMEI, last 4, etc.
        unit = conn.execute(
            "SELECT * FROM product_units WHERE product_id=? AND substr(unit_code, -?)=? AND status='Available' ORDER BY id ASC LIMIT 1",
            (product_id, len(typed), typed),
        ).fetchone()
        if unit:
            return unit
        return None
    return conn.execute("SELECT * FROM product_units WHERE product_id=? AND status='Available' ORDER BY id ASC LIMIT 1", (product_id,)).fetchone()


def _refresh_product_stock(conn: sqlite3.Connection, product_id: int) -> None:
    p = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p:
        return
    if p["is_serialized"]:
        stock = conn.execute("SELECT COUNT(*) c, COALESCE(AVG(cost),0) average_cost FROM product_units WHERE product_id=? AND status='Available'", (product_id,)).fetchone()
        avail = stock["c"]
        status = "Available" if avail > 0 else "Sold"
        if avail > 0:
            conn.execute("UPDATE products SET quantity=?, cost=?, status=?, updated_at=? WHERE id=?", (avail, stock["average_cost"], status, now_iso(), product_id))
        else:
            lifetime = conn.execute("SELECT COALESCE(SUM(qty_added*unit_cost)/NULLIF(SUM(qty_added),0),0) avg_cost FROM restock_batches WHERE product_id=?", (product_id,)).fetchone()
            lifetime_avg = n(lifetime.get("avg_cost")) if lifetime else 0.0
            if lifetime_avg <= 0:
                lifetime_avg = n(p.get("cost"))
            conn.execute("UPDATE products SET quantity=0, cost=?, status=?, updated_at=? WHERE id=?", (lifetime_avg, status, now_iso(), product_id))
    else:
        qty = i(p.get("quantity"))
        conn.execute("UPDATE products SET status=?, updated_at=? WHERE id=?", ("Available" if qty > 0 else "Out of Stock", now_iso(), product_id))


def _insert_supplier_get_id(conn: sqlite3.Connection, supplier_name: str, stamp: str) -> int:
    supplier_name = clean(supplier_name) or "Unknown"
    conn.execute("""
        INSERT INTO suppliers(name,active,created_at,updated_at) VALUES(?,1,?,?)
        ON CONFLICT(name) DO UPDATE SET active=1,updated_at=excluded.updated_at
    """, (supplier_name, stamp, stamp))
    row = conn.execute("SELECT id FROM suppliers WHERE name=? COLLATE NOCASE", (supplier_name,)).fetchone()
    return int(row["id"])


def _append_prepared_batches_to_product(conn: sqlite3.Connection, product_id: int, data: Dict[str, Any], prepared: List[Dict[str, Any]], user: Dict[str, Any], stamp: str, source: str) -> int:
    """Append new supplier batches to an existing product without touching old sales history."""
    p = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p:
        raise ValueError("Product not found")
    old_qty = int(p["quantity"] or 0)
    old_cost = n(p.get("cost"))
    if p["is_serialized"]:
        live = conn.execute("SELECT COUNT(*) c, COALESCE(AVG(cost),0) avg_cost FROM product_units WHERE product_id=? AND status='Available'", (product_id,)).fetchone()
        old_qty = int(live["c"] or 0)
        if old_qty > 0:
            old_cost = n(live.get("avg_cost")) or old_cost
    if not p["is_serialized"]:
        if old_qty > 0:
            raise ValueError("This existing SKU is bulk stock. Use Restock Selected Product by quantity, or keep exact-unit stock under a separate SKU.")
        conn.execute("UPDATE products SET is_serialized=1 WHERE id=?", (product_id,))
    added_total = 0
    running_qty = old_qty
    running_value = old_qty * old_cost
    supplier_names = []
    for batch_no, batch in enumerate(prepared, 1):
        supplier_id = _insert_supplier_get_id(conn, batch["supplier"], stamp)
        old_batch_qty = running_qty
        old_average = running_value / running_qty if running_qty else old_cost
        new_batch_qty = running_qty + batch["qty"]
        new_value = running_value + batch["qty"] * batch["unit_cost"]
        new_average = new_value / new_batch_qty if new_batch_qty else batch["unit_cost"]
        batch_code = f"{p['sku']}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-{source}-{batch_no:02d}"
        batch_cur = conn.execute("""
            INSERT INTO restock_batches(product_id,sku,qty_added,unit_cost,old_qty,new_qty,old_average_cost,new_average_cost,supplier,supplier_id,batch_code,note,stock_value_before,stock_value_after,created_by,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (product_id, p["sku"], batch["qty"], batch["unit_cost"], old_batch_qty, new_batch_qty, old_average, new_average, batch["supplier"], supplier_id, batch_code, batch["note"] or "Added stock to existing product", old_batch_qty * old_average, new_value, user["username"], stamp))
        purchase_batch_id = int(batch_cur.lastrowid)
        for code in batch["units"]:
            conn.execute("""
                INSERT INTO product_units(product_id,unit_code,cost,supplier,supplier_id,purchase_batch_id,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,'Available',?,?)
            """, (product_id, code, batch["unit_cost"], batch["supplier"], supplier_id, purchase_batch_id, stamp, stamp))
        supplier_names.append(batch["supplier"])
        added_total += batch["qty"]
        running_qty = new_batch_qty
        running_value = new_value
    new_avg = running_value / running_qty if running_qty else old_cost
    existing_supplier = clean(p.get("supplier"))
    known_suppliers = [s for s in [existing_supplier, *supplier_names] if s and s.lower() not in {"multiple suppliers", "unknown"}]
    product_supplier = known_suppliers[0] if len(set(x.casefold() for x in known_suppliers)) == 1 else "Multiple Suppliers"
    price = n(data.get("price")) or n(p.get("price"))
    offer_price = n(data.get("offer_price")) if data.get("offer_price") not in (None, "") else n(p.get("offer_price"))
    if offer_price < 0 or (offer_price > 0 and price > 0 and offer_price >= price):
        raise ValueError("Offer price must be zero or lower than the regular selling price")
    conn.execute("""
        UPDATE products
           SET brand=?,model=?,color=?,ram=?,rom=?,condition=?,description=?,supplier=?,cost=?,price=?,offer_price=?,quantity=?,status=?,updated_at=?
         WHERE id=?
    """, (
        clean(data.get("brand")) or clean(p.get("brand")),
        clean(data.get("model")) or clean(p.get("model")),
        clean(data.get("color")) or clean(p.get("color")),
        clean(data.get("ram")) or clean(p.get("ram")),
        clean(data.get("rom")) or clean(p.get("rom")),
        clean(data.get("condition")) or clean(p.get("condition")),
        clean(data.get("description")) or clean(p.get("description")),
        product_supplier,
        new_avg,
        price,
        offer_price,
        running_qty,
        "Available" if running_qty > 0 else "Out of Stock",
        stamp,
        product_id,
    ))
    return added_total


def list_suppliers() -> List[Dict[str, Any]]:
    """Normalized supplier directory with live purchase totals."""
    return query("""
        SELECT s.*,
               COALESCE(SUM(r.qty_added),0) total_qty,
               COALESCE(SUM(r.qty_added*r.unit_cost),0) total_value
        FROM suppliers s
        LEFT JOIN restock_batches r ON r.supplier_id=s.id
        WHERE s.active=1
        GROUP BY s.id
        ORDER BY s.name COLLATE NOCASE
    """)


def create_product_group(data: Dict[str, Any], supplier_batches: List[Dict[str, Any]], user: Dict[str, Any]) -> int:
    """Create a product and all supplier-owned exact units atomically.

    This mirrors the advanced inventory reference: one SKU/product group can
    contain several supplier acquisition batches.  Every unit retains the
    supplier id, supplier name and original buying price, while the product
    stores the mathematically correct quantity-weighted average cost.
    """
    require_admin(user)
    stamp = now_iso()
    sku = clean(data.get("sku")).upper()
    brand = clean(data.get("brand"))
    model = clean(data.get("model"))
    selling_price = n(data.get("price"))
    offer_price=n(data.get("offer_price"))
    if not sku or not brand or not model or selling_price <= 0:
        raise ValueError("SKU, brand, model and selling price are required")
    if offer_price<0 or (offer_price>0 and offer_price>=selling_price):
        raise ValueError("Offer price must be zero or lower than the regular selling price")
    if not supplier_batches:
        raise ValueError("Add at least one supplier batch")

    prepared: List[Dict[str, Any]] = []
    all_codes: List[str] = []
    seen_codes = set()
    for batch_no, raw in enumerate(supplier_batches, 1):
        supplier = clean(raw.get("supplier") or raw.get("name"))
        unit_cost = n(raw.get("unit_cost") if raw.get("unit_cost") is not None else raw.get("cost"))
        qty = i(raw.get("qty") or raw.get("quantity"))
        raw_units = raw.get("units") or []
        if isinstance(raw_units, (list, tuple)):
            units = [clean(value) for value in raw_units if clean(value)]
        else:
            units = _normal_unit_codes(raw_units)
        if not supplier:
            raise ValueError(f"Supplier name is required in batch {batch_no}")
        if unit_cost <= 0:
            raise ValueError(f"Buying price must be greater than zero in batch {batch_no}")
        if qty <= 0:
            raise ValueError(f"Quantity must be greater than zero in batch {batch_no}")
        if len(units) != qty:
            raise ValueError(f"Batch {batch_no} expects {qty} IMEI / ID values but has {len(units)}")
        for code in units:
            key = code.casefold()
            if key in seen_codes:
                raise ValueError(f"Duplicate IMEI / ID in product group: {code}")
            seen_codes.add(key)
            all_codes.append(code)
        prepared.append({"supplier": supplier, "unit_cost": unit_cost, "qty": qty, "units": units, "note": clean(raw.get("note"))})

    total_qty = sum(x["qty"] for x in prepared)
    total_value = sum(x["qty"] * x["unit_cost"] for x in prepared)
    weighted_average = total_value / total_qty
    supplier_names = list(dict.fromkeys(x["supplier"] for x in prepared))
    product_supplier = supplier_names[0] if len(supplier_names) == 1 else "Multiple Suppliers"

    appended_existing = False
    appended_added = 0
    with get_conn() as conn:
        existing = conn.execute("SELECT * FROM products WHERE upper(sku)=upper(?) LIMIT 1", (sku,)).fetchone()
        for code in all_codes:
            if _serial_exists_global(conn, code):
                raise ValueError(f"Duplicate IMEI / ID already exists: {code}")
        if existing:
            product_id = int(existing["id"])
            appended_added = _append_prepared_batches_to_product(conn, product_id, data, prepared, user, stamp, "A")
            appended_existing = True
        else:
            cur = conn.execute("""
                INSERT INTO products(sku,type,category,brand,model,color,ram,rom,condition,description,supplier,cost,price,offer_price,is_serialized,quantity,low_stock,status,image_path,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                sku, clean(data.get("type") or "Phone"), clean(data.get("category")), brand, model,
                clean(data.get("color")), clean(data.get("ram")), clean(data.get("rom")),
                clean(data.get("condition") or "Brand New"), clean(data.get("description")), product_supplier,
                weighted_average, selling_price, offer_price, 1, total_qty,
                i(data.get("low_stock") or LOW_STOCK_DEFAULT), "Available", clean(data.get("image_path")), stamp, stamp,
            ))
            product_id = int(cur.lastrowid)
            running_qty = 0
            running_value = 0.0
            for batch_no, batch in enumerate(prepared, 1):
                supplier_id = _insert_supplier_get_id(conn, batch["supplier"], stamp)
                old_qty = running_qty
                old_average = running_value / running_qty if running_qty else 0.0
                new_qty = running_qty + batch["qty"]
                new_value = running_value + batch["qty"] * batch["unit_cost"]
                new_average = new_value / new_qty
                batch_code = f"{sku}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-{batch_no:02d}"
                batch_cur = conn.execute("""
                    INSERT INTO restock_batches(product_id,sku,qty_added,unit_cost,old_qty,new_qty,old_average_cost,new_average_cost,supplier,supplier_id,batch_code,note,stock_value_before,stock_value_after,created_by,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (product_id, sku, batch["qty"], batch["unit_cost"], old_qty, new_qty, old_average, new_average, batch["supplier"], supplier_id, batch_code, batch["note"] or "Opening supplier batch", old_qty*old_average, new_value, user["username"], stamp))
                purchase_batch_id = int(batch_cur.lastrowid)
                for code in batch["units"]:
                    conn.execute("""
                        INSERT INTO product_units(product_id,unit_code,cost,supplier,supplier_id,purchase_batch_id,status,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,'Available',?,?)
                    """, (product_id, code, batch["unit_cost"], batch["supplier"], supplier_id, purchase_batch_id, stamp, stamp))
                running_qty = new_qty
                running_value = new_value

    if appended_existing:
        log_audit(user["username"], user["role"], "append_product_group_stock", sku, {
            "product_id": product_id, "added": appended_added,
            "suppliers": [{"name": x["supplier"], "qty": x["qty"], "unit_cost": x["unit_cost"]} for x in prepared],
        })
    else:
        log_audit(user["username"], user["role"], "create_product_group", sku, {
            "product_id": product_id, "quantity": total_qty, "weighted_average": weighted_average,
            "suppliers": [{"name": x["supplier"], "qty": x["qty"], "unit_cost": x["unit_cost"]} for x in prepared],
        })
    return product_id


def add_product(data: Dict[str, Any], user: Dict[str, Any]) -> int:  # type: ignore[override] # noqa: F811
    require_admin(user)
    stamp = now_iso()
    sku = clean(data.get("sku")).upper() or f"SKU-{int(datetime.now().timestamp())}"
    ptype = clean(data.get("type") or "Phone")
    category = clean(data.get("category"))
    qty_requested = max(0, i(data.get("quantity")))
    serial_lines = _normal_unit_codes(data.get("units"))
    track_units = bool(serial_lines) or _needs_unit_tracking(ptype, category)
    if track_units:
        if not serial_lines and qty_requested > 0:
            serial_lines = _auto_unit_codes(sku, qty_requested)
        qty = len(serial_lines)
        serialized = 1
    else:
        qty = qty_requested
        serialized = 0
    if serialized and qty <= 0:
        raise ValueError("Exact-unit products need at least one serial/IMEI or a quantity for auto IDs.")
    cost = n(data.get("cost"))
    price=n(data.get("price")); offer_price=n(data.get("offer_price"))
    if price<=0: raise ValueError("Regular selling price must be greater than zero")
    if offer_price<0 or (offer_price>0 and offer_price>=price): raise ValueError("Offer price must be zero or lower than the regular selling price")
    existing = query_one("SELECT * FROM products WHERE upper(sku)=upper(?) LIMIT 1", (sku,))
    if existing:
        if qty > 0:
            restock_input = "\n".join(serial_lines) if serialized else str(qty)
            restock_product(int(existing["id"]), restock_input, cost, clean(data.get("supplier")) or existing.get("supplier") or "Unknown", "Added through Add Product - existing SKU preserved", user)
        merged = dict(data)
        for key in ["type", "category", "brand", "model", "color", "ram", "rom", "condition", "description", "supplier", "image_path"]:
            if not clean(merged.get(key)):
                merged[key] = existing.get(key)
        merged["price"] = price or existing.get("price")
        merged["offer_price"] = offer_price if data.get("offer_price") not in (None, "") else existing.get("offer_price")
        merged["low_stock"] = data.get("low_stock") or existing.get("low_stock")
        update_product(int(existing["id"]), merged, user)
        log_audit(user["username"], user["role"], "add_product_existing_sku_as_restock", sku, {"product_id": existing["id"], "added": qty})
        return int(existing["id"])
    with get_conn() as conn:
        if conn.execute("SELECT id FROM products WHERE upper(sku)=upper(?) LIMIT 1", (sku,)).fetchone():
            raise ValueError(f"SKU already exists: {sku}")
        for code in serial_lines:
            if _serial_exists_global(conn, code):
                raise ValueError(f"Duplicate IMEI/serial already exists in inventory: {code}")
        cur = conn.execute(
            """
            INSERT INTO products(sku,type,category,brand,model,color,ram,rom,condition,description,supplier,cost,price,offer_price,is_serialized,quantity,low_stock,status,image_path,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (sku, ptype, category, clean(data.get("brand")), clean(data.get("model") or sku), clean(data.get("color")), clean(data.get("ram")), clean(data.get("rom")), clean(data.get("condition") or "Brand New"), clean(data.get("description")), clean(data.get("supplier")), cost, price, offer_price, serialized, qty, i(data.get("low_stock") or LOW_STOCK_DEFAULT), "Available" if qty > 0 else "Out of Stock", clean(data.get("image_path")), stamp, stamp),
        )
        product_id = int(cur.lastrowid)
        if serialized:
            for code in serial_lines:
                conn.execute("INSERT INTO product_units(product_id,unit_code,cost,supplier,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (product_id, code, cost, clean(data.get("supplier")), "Available", stamp, stamp))
        conn.execute("INSERT INTO restock_batches(product_id,sku,qty_added,unit_cost,old_qty,new_qty,old_average_cost,new_average_cost,supplier,note,stock_value_before,stock_value_after,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (product_id, sku, qty, cost, 0, qty, 0, cost, clean(data.get("supplier")), "Opening stock", 0, qty * cost, user["username"], stamp))
    log_audit(user["username"], user["role"], "add_product_v6", sku, {"qty": qty, "serialized": serialized})
    return int(product_id)


def restock_product(product_id: int, qty_or_units: Any, unit_cost: Any, supplier: str, note: str, user: Dict[str, Any]) -> int:  # type: ignore[override] # noqa: F811
    require_admin(user)
    stamp = now_iso()
    with get_conn() as conn:
        p = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        if not p:
            raise ValueError("Product not found")
        old_qty = int(p["quantity"] or 0)
        old_cost = n(p["cost"])
        unit_cost_f = n(unit_cost) or old_cost
        supplier_name = clean(supplier) or clean(p.get("supplier")) or "Unknown"
        conn.execute("""
            INSERT INTO suppliers(name,active,created_at,updated_at) VALUES(?,1,?,?)
            ON CONFLICT(name) DO UPDATE SET active=1,updated_at=excluded.updated_at
        """, (supplier_name, stamp, stamp))
        supplier_row = conn.execute("SELECT id FROM suppliers WHERE name=? COLLATE NOCASE", (supplier_name,)).fetchone()
        supplier_id = int(supplier_row["id"])
        raw_qty_units = str(qty_or_units or "").strip()
        # If the restock input is only a small number like 3/10/100, treat it as quantity.
        # Long numeric values and multiline/comma values are treated as actual serial/IMEI codes.
        if raw_qty_units.isdigit() and len(raw_qty_units) <= 4 and "\n" not in raw_qty_units and "," not in raw_qty_units:
            serial_lines = []
            qty_requested = max(0, i(raw_qty_units))
        else:
            serial_lines = _normal_unit_codes(qty_or_units)
            qty_requested = len(serial_lines) if serial_lines else max(0, i(qty_or_units))
        if qty_requested <= 0:
            raise ValueError("Enter a restock quantity or serial/IMEI lines.")
        added = 0
        added_unit_ids: List[int] = []
        # Preserve established bulk SKUs when they already contain quantity.
        # Device categories normally use exact-unit tracking, but silently
        # converting an existing bulk balance would make the old quantity
        # impossible to reconcile. New/empty device SKUs still become exact
        # unit stock automatically, and supplied IMEI lines always enable it.
        track_units = bool(p["is_serialized"]) or bool(serial_lines) or (
            old_qty <= 0 and _needs_unit_tracking(p.get("type"), p.get("category"))
        )
        if track_units:
            if not p["is_serialized"]:
                if old_qty > 0:
                    raise ValueError("This product is currently bulk stock. Keep restocking by quantity, or create a new exact-unit SKU for IMEI tracking.")
                conn.execute("UPDATE products SET is_serialized=1 WHERE id=?", (product_id,))
            if not serial_lines:
                serial_lines = _auto_unit_codes(p["sku"], qty_requested)
            for code in serial_lines:
                if _serial_exists_global(conn, code, exclude_product_id=product_id):
                    raise ValueError(f"Duplicate IMEI/serial already exists: {code}")
                try:
                    unit_cur = conn.execute("INSERT INTO product_units(product_id,unit_code,cost,supplier,supplier_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", (product_id, code, unit_cost_f, supplier_name, supplier_id, "Available", stamp, stamp))
                    added_unit_ids.append(int(unit_cur.lastrowid))
                    added += 1
                except sqlite3.IntegrityError:
                    raise ValueError(f"Duplicate IMEI/serial already exists for this product: {code}")
            new_qty = conn.execute("SELECT COUNT(*) AS c FROM product_units WHERE product_id=? AND status='Available'", (product_id,)).fetchone()["c"]
        else:
            added = qty_requested
            new_qty = old_qty + added
        new_avg = ((old_qty * old_cost) + (added * unit_cost_f)) / max(1, old_qty + added) if added > 0 else old_cost
        if track_units:
            conn.execute("UPDATE products SET quantity=?, cost=?, status=?, supplier=?, updated_at=? WHERE id=?", (new_qty, new_avg, "Available" if new_qty > 0 else "Out of Stock", supplier_name, stamp, product_id))
        else:
            conn.execute("UPDATE products SET quantity=?, cost=?, status=?, supplier=?, updated_at=? WHERE id=?", (new_qty, new_avg, "Available" if new_qty > 0 else "Out of Stock", supplier_name, stamp, product_id))
        batch_code = f"{p['sku']}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}-R"
        batch_cur = conn.execute("INSERT INTO restock_batches(product_id,sku,qty_added,unit_cost,old_qty,new_qty,old_average_cost,new_average_cost,supplier,supplier_id,batch_code,note,stock_value_before,stock_value_after,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (product_id, p["sku"], added, unit_cost_f, old_qty, new_qty, old_cost, new_avg, supplier_name, supplier_id, batch_code, clean(note), old_qty * old_cost, new_qty * new_avg, user["username"], stamp))
        purchase_batch_id = int(batch_cur.lastrowid)
        if added_unit_ids:
            placeholders = ",".join("?" for _ in added_unit_ids)
            conn.execute(f"UPDATE product_units SET purchase_batch_id=? WHERE id IN ({placeholders})", (purchase_batch_id, *added_unit_ids))
    log_audit(user["username"], user["role"], "restock_product_v6", str(product_id), {"added": added, "old_qty": old_qty, "new_qty": new_qty})
    return int(added)


def _reserve_stock(conn: sqlite3.Connection, cart: Dict[str, Any], invoice_id: int = 0, wholesale_invoice_id: int = 0, shop_id: int = 0) -> Dict[str, Any]:  # type: ignore[override]
    product_id = int(cart["product_id"])
    p = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not p:
        raise ValueError("Product not found")
    qty = max(1, i(cart.get("qty") or 1))
    price = n(cart.get("price") or p.get("offer_price") or p.get("price"))
    discount = n(cart.get("discount"))
    unit_code = clean(cart.get("unit_code"))
    unit_id = None
    unit_cost = n(p.get("cost"))
    regular_price=n(p.get("price")); catalog_offer=n(p.get("offer_price"))
    offer_applied=1 if catalog_offer>0 and catalog_offer<regular_price and abs(price-catalog_offer)<0.01 else 0
    offer_saving=max(0,(regular_price-price)*qty) if offer_applied else 0.0
    if p["is_serialized"]:
        qty = 1
        unit = _resolve_available_unit(conn, product_id, unit_code)
        if not unit:
            typed_msg = f" matching '{unit_code}'" if unit_code else ""
            raise ValueError(f"No available serial/IMEI{typed_msg} for {product_display_name(p)}")
        unit_id = unit["id"]
        unit_code = unit["unit_code"]
        unit_cost = n(unit.get("cost")) or unit_cost
        if wholesale_invoice_id:
            conn.execute("UPDATE product_units SET status=?, shop_id=?, wholesale_invoice_id=?, updated_at=? WHERE id=? AND status='Available'", (f"Wholesale:{shop_id}", shop_id, wholesale_invoice_id, now_iso(), unit_id))
        else:
            conn.execute("UPDATE product_units SET status='Sold', invoice_id=?, updated_at=? WHERE id=? AND status='Available'", (invoice_id, now_iso(), unit_id))
        if conn.total_changes < 1:
            raise ValueError(f"Unit already sold or issued: {unit_code}")
        _refresh_product_stock(conn, product_id)
    else:
        current_qty = int(p["quantity"] or 0)
        if current_qty < qty:
            raise ValueError(f"Not enough stock for {product_display_name(p)}. Available: {current_qty}")
        new_qty = current_qty - qty
        conn.execute("UPDATE products SET quantity=?, status=?, updated_at=? WHERE id=?", (new_qty, "Available" if new_qty > 0 else "Out of Stock", now_iso(), product_id))
    ext_label = clean(cart.get("extended_warranty_name"))
    ext_charge = n(cart.get("extended_warranty_price")) if ext_label and ext_label != "No Extended" else 0.0
    line_total = max(0, price * qty - discount + (ext_charge * qty))
    return {
        "product_id": product_id,
        "unit_id": unit_id,
        "sku": p["sku"],
        "product_name": clean(cart.get("product_name")) or product_display_name(p),
        "unit_code": unit_code,
        "qty": qty,
        "unit_price": price,
        "unit_cost": unit_cost,
        "regular_price":regular_price,
        "catalog_offer_price":catalog_offer,
        "offer_applied":offer_applied,
        "offer_saving":offer_saving,
        "discount": discount,
        "line_total": line_total,
    }
