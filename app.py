import json
import os
import smtplib
import sqlite3
from datetime import datetime
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "pos_demo.db"
NOTIFY_LOG = BASE_DIR / "data" / "order_notifications.log"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS families (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS brands (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS seasons (id INTEGER PRIMARY KEY, name TEXT UNIQUE);

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            item_name TEXT NOT NULL,
            item_description TEXT,
            barcodes TEXT,
            category_id INTEGER,
            family_id INTEGER,
            season_id INTEGER,
            brand_id INTEGER,
            cost REAL DEFAULT 0,
            price1 REAL DEFAULT 0,
            price2 REAL DEFAULT 0,
            stock_quantity INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_service_item INTEGER DEFAULT 0,
            image_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS stock_history (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            quantity_change INTEGER NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            phone1 TEXT,
            phone2 TEXT,
            address TEXT,
            country TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            phone1 TEXT,
            phone2 TEXT,
            address TEXT,
            country TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY,
            reference TEXT,
            supplier_id INTEGER,
            invoice_number TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            customer_phone TEXT,
            shipping_address TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def seed_data():
    conn = get_db()
    cur = conn.cursor()
    for table, values in {
        "categories": ["Shoes", "Clothes", "Accessories"],
        "families": ["Men", "Women", "Kids"],
        "brands": ["Nova", "UrbanX", "Peak"],
        "seasons": ["Summer", "Winter", "All Season"],
    }.items():
        for name in values:
            cur.execute(f"INSERT OR IGNORE INTO {table}(name) VALUES(?)", (name,))

    existing = cur.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
    if existing == 0:
        cur.execute(
            """
            INSERT INTO products (item_name,item_description,barcodes,category_id,family_id,season_id,brand_id,cost,price1,price2,stock_quantity,is_active,is_service_item,image_url)
            VALUES
            ('Running Shoe','Comfort sport shoe','111111,222222',1,1,3,1,40,69,64,20,1,0,''),
            ('Winter Jacket','Warm jacket','333333',2,2,2,2,55,95,88,12,1,0,''),
            ('Gift Wrapping Service','Gift package service','SRV001',3,3,3,3,0,5,5,0,1,1,'')
            """
        )
        rows = cur.execute("SELECT id, stock_quantity FROM products").fetchall()
        for row in rows:
            if row["stock_quantity"]:
                cur.execute(
                    "INSERT INTO stock_history (product_id, transaction_type, quantity_change, note) VALUES (?, 'inventory', ?, 'Initial stock')",
                    (row["id"], row["stock_quantity"]),
                )

    conn.commit()
    conn.close()


def json_response(handler, data, code=200):
    body = json.dumps(data).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def parse_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length) if length else b"{}"
    return json.loads(body.decode("utf-8") or "{}")


def send_owner_notification(order_id, order_data):
    owner_email = os.getenv("OWNER_EMAIL", "owner@example.com")
    smtp_host = os.getenv("SMTP_HOST")
    subject = f"New website order #{order_id}"
    text = f"New order #{order_id} from {order_data['customer_name']} ({order_data['customer_email']})"

    if smtp_host:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = os.getenv("SMTP_FROM", "no-reply@demo.local")
        msg["To"] = owner_email
        msg.set_content(text)
        with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "25"))) as s:
            if os.getenv("SMTP_USER"):
                s.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
    else:
        NOTIFY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with NOTIFY_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow().isoformat()}] TO:{owner_email} SUBJECT:{subject} BODY:{text}\n")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed)
            return
        if parsed.path == "/":
            self.serve_file("static/shop.html")
            return
        if parsed.path == "/pos":
            self.serve_file("static/pos.html")
            return
        self.serve_file("static" + parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_post(parsed)
            return
        self.send_error(404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_put(parsed)
            return
        self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_delete(parsed)
            return
        self.send_error(404)

    def serve_file(self, rel_path):
        p = BASE_DIR / rel_path.lstrip("/")
        if not p.exists() or p.is_dir():
            self.send_error(404)
            return
        content = p.read_bytes()
        content_type = "text/plain"
        if str(p).endswith(".html"):
            content_type = "text/html"
        elif str(p).endswith(".css"):
            content_type = "text/css"
        elif str(p).endswith(".js"):
            content_type = "application/javascript"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def handle_api_get(self, parsed):
        conn = get_db()
        q = parse_qs(parsed.query)
        if parsed.path == "/api/meta":
            data = {}
            for table in ["categories", "families", "brands", "seasons"]:
                data[table] = [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY name")]
            json_response(self, data)
        elif parsed.path == "/api/products":
            sql = """
                SELECT p.*, c.name category, f.name family, b.name brand, s.name season
                FROM products p
                LEFT JOIN categories c ON p.category_id=c.id
                LEFT JOIN families f ON p.family_id=f.id
                LEFT JOIN brands b ON p.brand_id=b.id
                LEFT JOIN seasons s ON p.season_id=s.id
                WHERE 1=1
            """
            args = []
            search = q.get("search", [""])[0].strip()
            if search:
                sql += " AND (p.item_name LIKE ? OR p.barcodes LIKE ? OR c.name LIKE ? OR f.name LIKE ? OR b.name LIKE ? OR s.name LIKE ?)"
                args.extend([f"%{search}%"] * 6)
            for field, col in [("category_id", "p.category_id"), ("family_id", "p.family_id"), ("brand_id", "p.brand_id"), ("season_id", "p.season_id")]:
                if q.get(field, [""])[0]:
                    sql += f" AND {col}=?"
                    args.append(q[field][0])
            rows = [dict(r) for r in conn.execute(sql + " ORDER BY p.id DESC", args)]
            json_response(self, rows)
        elif parsed.path == "/api/stock":
            sql = "SELECT p.id,p.item_name,p.stock_quantity,p.cost,(p.stock_quantity*p.cost) total_cost,c.name category,f.name family,b.name brand,s.name season FROM products p LEFT JOIN categories c ON p.category_id=c.id LEFT JOIN families f ON p.family_id=f.id LEFT JOIN brands b ON p.brand_id=b.id LEFT JOIN seasons s ON p.season_id=s.id WHERE p.is_service_item=0"
            args = []
            qty_filter = q.get("qty_filter", [""])[0]
            if qty_filter == "negative":
                sql += " AND p.stock_quantity < 0"
            elif qty_filter == "zero":
                sql += " AND p.stock_quantity = 0"
            elif qty_filter == "positive":
                sql += " AND p.stock_quantity > 0"
            rows = [dict(r) for r in conn.execute(sql, args)]
            total = sum(r["total_cost"] for r in rows)
            json_response(self, {"items": rows, "total_cost": total})
        elif parsed.path == "/api/stock/history":
            product_id = q.get("product_id", [""])[0]
            ttype = q.get("type", [""])[0]
            sql = "SELECT h.*, p.item_name FROM stock_history h JOIN products p ON p.id=h.product_id WHERE 1=1"
            args = []
            if product_id:
                sql += " AND product_id=?"
                args.append(product_id)
            if ttype:
                sql += " AND transaction_type=?"
                args.append(ttype)
            rows = [dict(r) for r in conn.execute(sql + " ORDER BY h.id DESC", args)]
            json_response(self, rows)
        elif parsed.path in ["/api/customers", "/api/suppliers"]:
            table = "customers" if "customers" in parsed.path else "suppliers"
            search = q.get("search", [""])[0]
            sql = f"SELECT * FROM {table} WHERE 1=1"
            args = []
            if search:
                sql += " AND (name LIKE ? OR phone1 LIKE ? OR phone2 LIKE ? OR address LIKE ? OR country LIKE ?)"
                args = [f"%{search}%"] * 5
            rows = [dict(r) for r in conn.execute(sql + " ORDER BY id DESC", args)]
            json_response(self, rows)
        elif parsed.path == "/api/orders":
            rows = [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY id DESC")]
            json_response(self, rows)
        elif parsed.path == "/api/reports":
            report = {
                "daily_sales": conn.execute("SELECT COUNT(*) c FROM orders WHERE date(created_at)=date('now')").fetchone()["c"],
                "cash_report": conn.execute("SELECT IFNULL(SUM(oi.quantity*oi.unit_price),0) t FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE date(o.created_at)=date('now')").fetchone()["t"],
                "products": conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"],
                "customers": conn.execute("SELECT COUNT(*) c FROM customers").fetchone()["c"],
                "purchases": conn.execute("SELECT COUNT(*) c FROM purchases").fetchone()["c"],
            }
            json_response(self, report)
        else:
            self.send_error(404)
        conn.close()

    def handle_api_post(self, parsed):
        conn = get_db()
        data = parse_body(self)
        if parsed.path.startswith("/api/meta/"):
            table = parsed.path.split("/")[-1]
            if table not in ["categories", "families", "brands", "seasons"]:
                return self.send_error(400)
            conn.execute(f"INSERT INTO {table}(name) VALUES(?)", (data["name"],))
            conn.commit()
            return json_response(self, {"ok": True}, 201)
        if parsed.path == "/api/products":
            conn.execute(
                """INSERT INTO products (item_name,item_description,barcodes,category_id,family_id,season_id,brand_id,cost,price1,price2,stock_quantity,is_active,is_service_item,image_url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data.get("item_name"), data.get("item_description"), data.get("barcodes"), data.get("category_id"), data.get("family_id"),
                    data.get("season_id"), data.get("brand_id"), data.get("cost", 0), data.get("price1", 0), data.get("price2", 0),
                    data.get("stock_quantity", 0), 1 if data.get("is_active", True) else 0, 1 if data.get("is_service_item", False) else 0, data.get("image_url", "")
                ),
            )
            pid = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
            if int(data.get("stock_quantity", 0)) != 0:
                conn.execute("INSERT INTO stock_history(product_id,transaction_type,quantity_change,note) VALUES (?, 'inventory', ?, 'Opening stock')", (pid, data.get("stock_quantity", 0)))
            conn.commit()
            return json_response(self, {"ok": True, "id": pid}, 201)
        if parsed.path == "/api/customers":
            conn.execute("INSERT INTO customers(name,phone1,phone2,address,country,is_active) VALUES (?,?,?,?,?,?)", (data.get("name"), data.get("phone1"), data.get("phone2"), data.get("address"), data.get("country"), 1 if data.get("is_active", True) else 0))
            conn.commit()
            return json_response(self, {"ok": True}, 201)
        if parsed.path == "/api/suppliers":
            conn.execute("INSERT INTO suppliers(name,phone1,phone2,address,country,is_active) VALUES (?,?,?,?,?,?)", (data.get("name"), data.get("phone1"), data.get("phone2"), data.get("address"), data.get("country"), 1 if data.get("is_active", True) else 0))
            conn.commit()
            return json_response(self, {"ok": True}, 201)
        if parsed.path == "/api/purchases":
            conn.execute("INSERT INTO purchases(reference,supplier_id,invoice_number) VALUES (?,?,?)", (data.get("reference"), data.get("supplier_id"), data.get("invoice_number")))
            conn.commit()
            return json_response(self, {"ok": True}, 201)
        if parsed.path == "/api/orders":
            items = data.get("items", [])
            cur = conn.cursor()
            cur.execute("INSERT INTO orders(customer_name,customer_email,customer_phone,shipping_address) VALUES (?,?,?,?)", (data.get("customer_name"), data.get("customer_email"), data.get("customer_phone"), data.get("shipping_address")))
            order_id = cur.lastrowid
            for item in items:
                prod = conn.execute("SELECT price1,is_service_item FROM products WHERE id=?", (item["product_id"],)).fetchone()
                if not prod:
                    continue
                qty = int(item.get("quantity", 1))
                cur.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price) VALUES (?,?,?,?)", (order_id, item["product_id"], qty, prod["price1"]))
                if prod["is_service_item"] == 0:
                    cur.execute("UPDATE products SET stock_quantity = stock_quantity - ? WHERE id=?", (qty, item["product_id"]))
                    cur.execute("INSERT INTO stock_history(product_id,transaction_type,quantity_change,note) VALUES (?, 'sales', ?, ?)", (item["product_id"], -qty, f"Web order #{order_id}"))
            conn.commit()
            send_owner_notification(order_id, data)
            return json_response(self, {"ok": True, "order_id": order_id}, 201)
        self.send_error(404)
        conn.close()

    def handle_api_put(self, parsed):
        conn = get_db()
        data = parse_body(self)
        if parsed.path.startswith("/api/products/"):
            pid = parsed.path.split("/")[-1]
            conn.execute(
                """UPDATE products SET item_name=?,item_description=?,barcodes=?,category_id=?,family_id=?,season_id=?,brand_id=?,cost=?,price1=?,price2=?,is_active=?,is_service_item=?,image_url=? WHERE id=?""",
                (data.get("item_name"), data.get("item_description"), data.get("barcodes"), data.get("category_id"), data.get("family_id"), data.get("season_id"), data.get("brand_id"), data.get("cost", 0), data.get("price1", 0), data.get("price2", 0), 1 if data.get("is_active", True) else 0, 1 if data.get("is_service_item", False) else 0, data.get("image_url", ""), pid),
            )
            conn.commit()
            return json_response(self, {"ok": True})
        if parsed.path.startswith("/api/stock/"):
            pid = parsed.path.split("/")[-1]
            qty = int(data.get("stock_quantity", 0))
            prev = conn.execute("SELECT stock_quantity FROM products WHERE id=?", (pid,)).fetchone()["stock_quantity"]
            diff = qty - prev
            conn.execute("UPDATE products SET stock_quantity=? WHERE id=?", (qty, pid))
            conn.execute("INSERT INTO stock_history(product_id,transaction_type,quantity_change,note) VALUES (?, 'inventory', ?, 'Manual stock edit')", (pid, diff))
            conn.commit()
            return json_response(self, {"ok": True})
        if parsed.path.startswith("/api/purchases/"):
            pid = parsed.path.split("/")[-1]
            conn.execute("UPDATE purchases SET reference=?,supplier_id=?,invoice_number=? WHERE id=?", (data.get("reference"), data.get("supplier_id"), data.get("invoice_number"), pid))
            conn.commit()
            return json_response(self, {"ok": True})
        self.send_error(404)

    def handle_api_delete(self, parsed):
        conn = get_db()
        if parsed.path.startswith("/api/products/"):
            pid = parsed.path.split("/")[-1]
            conn.execute("DELETE FROM products WHERE id=?", (pid,))
            conn.commit()
            return json_response(self, {"ok": True})
        if parsed.path.startswith("/api/purchases/"):
            pid = parsed.path.split("/")[-1]
            conn.execute("DELETE FROM purchases WHERE id=?", (pid,))
            conn.commit()
            return json_response(self, {"ok": True})
        self.send_error(404)


if __name__ == "__main__":
    init_db()
    seed_data()
    port = int(os.getenv("PORT", "8000"))
    print(f"POS demo running at http://localhost:{port} (shop) and /pos")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
