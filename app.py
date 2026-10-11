from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime
import random

app = Flask(__name__)

DATABASE = "isp_dashboard.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    
    # Create customers table with more details
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            address TEXT,
            package TEXT NOT NULL,
            status TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            last_payment TEXT,
            receipt_verified INTEGER DEFAULT 0,
            connection_status TEXT DEFAULT 'Disconnected',
            device_type TEXT,
            ip_address TEXT,
            installation_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create payments table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            receipt_no TEXT NOT NULL,
            payment_date TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        )
    """)
    
    # Create connections table for relationships
    conn.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            primary_customer_id INTEGER NOT NULL,
            secondary_customer_id INTEGER NOT NULL,
            relationship TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(primary_customer_id) REFERENCES customers(id),
            FOREIGN KEY(secondary_customer_id) REFERENCES customers(id)
        )
    """)
    
    conn.commit()
    conn.close()

    # Seed demo data if empty
    conn = get_db_connection()
    existing = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    if existing == 0:
        conn.execute("""
            INSERT INTO customers (name, phone, email, address, package, status, balance, last_payment, receipt_verified, connection_status, device_type, ip_address, installation_date)
            VALUES
            ('James K.', '0712345678', 'james@email.com', '123 Main St, Nairobi', 'Home 20 Mbps', 'Active', 0, '2026-10-01', 1, 'Online', 'Router', '192.168.1.10', '2024-01-15'),
            ('Mary A.', '0798765432', 'mary@email.com', '456 Oak Ave, Nairobi', 'Business 50 Mbps', 'Overdue', 5400, '2026-09-15', 0, 'Disconnected', 'Router', '192.168.1.11', '2023-05-20'),
            ('Samuel T.', '0723456789', 'samuel@email.com', '789 Pine Rd, Nairobi', 'Family 30 Mbps', 'Pending', 2200, '2026-09-28', 1, 'Online', 'WiFi', '192.168.1.12', '2024-03-10'),
            ('Grace N.', '0734567890', 'grace@email.com', '321 Elm St, Nairobi', 'Student 10 Mbps', 'Active', 0, '2026-10-05', 1, 'Online', 'Router', '192.168.1.13', '2024-06-05')
        """)
        
        conn.execute("""
            INSERT INTO payments (customer_id, amount, payment_method, receipt_no, payment_date, status)
            VALUES
            (1, 2500, 'Cash', 'RCPT-101', '2026-10-01', 'Verified'),
            (1, 2500, 'Mobile Money', 'RCPT-102', '2026-10-05', 'Verified'),
            (2, 2000, 'Bank Transfer', 'RCPT-205', '2026-09-15', 'Pending'),
            (3, 1800, 'Cash', 'RCPT-330', '2026-09-28', 'Verified'),
            (4, 2500, 'Bank Transfer', 'RCPT-440', '2026-10-05', 'Verified')
        """)
        
        # Add connection relationships
        conn.execute("""
            INSERT INTO connections (primary_customer_id, secondary_customer_id, relationship)
            VALUES
            (1, 3, 'Family Member'),
            (2, 4, 'Business Affiliate')
        """)
        
        conn.commit()
    conn.close()


def get_dashboard_data():
    conn = get_db_connection()
    
    customers = conn.execute("""
        SELECT * FROM customers
        ORDER BY id ASC
    """).fetchall()

    payments = conn.execute("""
        SELECT p.*, c.name AS customer_name
        FROM payments p
        JOIN customers c ON c.id = p.customer_id
        ORDER BY p.payment_date DESC
    """).fetchall()

    total_collected = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments").fetchone()[0]
    overdue = conn.execute("SELECT COUNT(*) FROM customers WHERE status='Overdue' OR balance > 0").fetchone()[0]
    verified = conn.execute("SELECT COUNT(*) FROM payments WHERE status='Verified'").fetchone()[0]
    active_accounts = conn.execute("SELECT COUNT(*) FROM customers WHERE status='Active'").fetchone()[0]
    online_count = conn.execute("SELECT COUNT(*) FROM customers WHERE connection_status='Online'").fetchone()[0]
    offline_count = conn.execute("SELECT COUNT(*) FROM customers WHERE connection_status='Disconnected'").fetchone()[0]

    conn.close()

    return {
        "customers": customers,
        "payments": payments,
        "total_collected": total_collected,
        "overdue": overdue,
        "verified": verified,
        "active_accounts": active_accounts,
        "online_count": online_count,
        "offline_count": offline_count
    }


def get_customer_connections(customer_id):
    conn = get_db_connection()
    
    # Get connections where this customer is primary
    primary_connections = conn.execute("""
        SELECT c.*, cust.name as secondary_name
        FROM connections c
        JOIN customers cust ON c.secondary_customer_id = cust.id
        WHERE c.primary_customer_id = ?
    """, (customer_id,)).fetchall()
    
    # Get connections where this customer is secondary
    secondary_connections = conn.execute("""
        SELECT c.*, cust.name as primary_name
        FROM connections c
        JOIN customers cust ON c.primary_customer_id = cust.id
        WHERE c.secondary_customer_id = ?
    """, (customer_id,)).fetchall()
    
    conn.close()
    return primary_connections, secondary_connections


@app.route("/", methods=["GET"])
def index():
    data = get_dashboard_data()
    return render_template("index.html", data=data)


@app.route("/customer/<int:customer_id>", methods=["GET"])
def customer_detail(customer_id):
    conn = get_db_connection()
    customer = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    
    payments = conn.execute("""
        SELECT * FROM payments WHERE customer_id = ?
        ORDER BY payment_date DESC
    """, (customer_id,)).fetchall()
    
    conn.close()
    
    primary_conn, secondary_conn = get_customer_connections(customer_id)
    
    if not customer:
        return redirect(url_for("index"))
    
    return render_template("customer_detail.html", 
                         customer=customer, 
                         payments=payments,
                         primary_connections=primary_conn,
                         secondary_connections=secondary_conn)


@app.route("/add-payment", methods=["POST"])
def add_payment():
    try:
        customer_name = request.form["customer_name"].strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()
        package = request.form["package"].strip()
        status = request.form["status"].strip()
        amount = float(request.form["amount"])
        method = request.form["payment_method"].strip()
        receipt_no = request.form["receipt_no"].strip()
        payment_date = request.form["payment_date"]
        balance = float(request.form.get("balance", 0))
        device_type = request.form.get("device_type", "Router").strip()
        ip_address = request.form.get("ip_address", "").strip()

        conn = get_db_connection()
        customer = conn.execute(
            "SELECT * FROM customers WHERE name = ?",
            (customer_name,)
        ).fetchone()

        if customer is None:
            conn.execute("""
                INSERT INTO customers (name, phone, email, address, package, status, balance, last_payment, receipt_verified, device_type, ip_address, installation_date, connection_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (customer_name, phone, email, address, package, status, max(0, balance - amount), payment_date, 1, device_type, ip_address, payment_date, 'Online'))
            customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            customer_id = customer["id"]
            new_balance = max(0, customer["balance"] - amount)
            status_update = status if status else customer["status"]
            receipt_verified = 1 if receipt_no else customer["receipt_verified"]
            conn.execute("""
                UPDATE customers
                SET phone = ?, email = ?, address = ?, package = ?, status = ?, balance = ?, last_payment = ?, receipt_verified = ?, device_type = ?, ip_address = ?
                WHERE id = ?
            """, (phone or customer["phone"], email or customer["email"], address or customer["address"], package or customer["package"], status_update, new_balance, payment_date, receipt_verified, device_type, ip_address or customer["ip_address"], customer_id))

        conn.execute("""
            INSERT INTO payments (customer_id, amount, payment_method, receipt_no, payment_date, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (customer_id, amount, method, receipt_no, payment_date, "Verified"))

        conn.commit()
        conn.close()

        return redirect(url_for("index"))
    except Exception as e:
        return {"error": str(e)}, 400


@app.route("/delete-payment/<int:payment_id>", methods=["POST"])
def delete_payment(payment_id):
    try:
        conn = get_db_connection()
        payment = conn.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone()
        
        if payment:
            conn.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
            conn.commit()
        
        conn.close()
        return redirect(url_for("index"))
    except Exception as e:
        return {"error": str(e)}, 400


@app.route("/delete-customer/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM payments WHERE customer_id = ?", (customer_id,))
        conn.execute("DELETE FROM connections WHERE primary_customer_id = ? OR secondary_customer_id = ?", (customer_id, customer_id))
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    except Exception as e:
        return {"error": str(e)}, 400


@app.route("/update-status/<int:customer_id>", methods=["POST"])
def update_status(customer_id):
    try:
        new_status = request.form.get("status")
        conn = get_db_connection()
        conn.execute("UPDATE customers SET status = ? WHERE id = ?", (new_status, customer_id))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    except Exception as e:
        return {"error": str(e)}, 400


@app.route("/update-connection-status/<int:customer_id>/<status>", methods=["POST"])
def update_connection_status(customer_id, status):
    try:
        conn = get_db_connection()
        conn.execute("UPDATE customers SET connection_status = ? WHERE id = ?", (status, customer_id))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    except Exception as e:
        return {"error": str(e)}, 400


@app.route("/verify-receipt/<int:payment_id>", methods=["POST"])
def verify_receipt(payment_id):
    try:
        conn = get_db_connection()
        conn.execute("UPDATE payments SET status = 'Verified' WHERE id = ?", (payment_id,))
        conn.commit()
        conn.close()
        return redirect(url_for("index"))
    except Exception as e:
        return {"error": str(e)}, 400


@app.route("/api/connection-status", methods=["GET"])
def api_connection_status():
    """API endpoint for real-time connection status"""
    conn = get_db_connection()
    customers = conn.execute("SELECT id, name, connection_status FROM customers").fetchall()
    conn.close()
    return jsonify([dict(c) for c in customers])


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
