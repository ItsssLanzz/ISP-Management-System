from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = "isp_dashboard.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            package TEXT NOT NULL,
            status TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0,
            last_payment TEXT,
            receipt_verified INTEGER DEFAULT 0
        )
    """)
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
    conn.commit()
    conn.close()

    # Seed demo data if empty
    conn = get_db_connection()
    existing = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    if existing == 0:
        conn.execute("""
            INSERT INTO customers (name, phone, package, status, balance, last_payment, receipt_verified)
            VALUES
            ('James K.', '0712345678', 'Home 20 Mbps', 'Active', 0, '2026-10-01', 1),
            ('Mary A.', '0798765432', 'Business 50 Mbps', 'Overdue', 5400, '2026-09-15', 0),
            ('Samuel T.', '0723456789', 'Family 30 Mbps', 'Pending', 2200, '2026-09-28', 1),
            ('Grace N.', '0734567890', 'Student 10 Mbps', 'Active', 0, '2026-10-05', 1)
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

    conn.close()

    return {
        "customers": customers,
        "payments": payments,
        "total_collected": total_collected,
        "overdue": overdue,
        "verified": verified,
        "active_accounts": active_accounts
    }


@app.route("/", methods=["GET"])
def index():
    data = get_dashboard_data()
    return render_template("index.html", data=data)


@app.route("/add-payment", methods=["POST"])
def add_payment():
    try:
        customer_name = request.form["customer_name"].strip()
        phone = request.form.get("phone", "").strip()
        package = request.form["package"].strip()
        status = request.form["status"].strip()
        amount = float(request.form["amount"])
        method = request.form["payment_method"].strip()
        receipt_no = request.form["receipt_no"].strip()
        payment_date = request.form["payment_date"]
        balance = float(request.form.get("balance", 0))

        conn = get_db_connection()
        customer = conn.execute(
            "SELECT * FROM customers WHERE name = ?",
            (customer_name,)
        ).fetchone()

        if customer is None:
            conn.execute("""
                INSERT INTO customers (name, phone, package, status, balance, last_payment, receipt_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (customer_name, phone, package, status, max(0, balance - amount), payment_date, 1))
            customer_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            customer_id = customer["id"]
            new_balance = max(0, customer["balance"] - amount)
            status_update = status if status else customer["status"]
            receipt_verified = 1 if receipt_no else customer["receipt_verified"]
            conn.execute("""
                UPDATE customers
                SET phone = ?, package = ?, status = ?, balance = ?, last_payment = ?, receipt_verified = ?
                WHERE id = ?
            """, (phone or customer["phone"], package or customer["package"], status_update, new_balance, payment_date, receipt_verified, customer_id))

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


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
