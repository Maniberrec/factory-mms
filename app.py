from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file
import os
from flask_sqlalchemy import SQLAlchemy
import sqlite3, datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import openpyxl
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///maintenance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


# ---------------- Database Models ----------------
class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100))
    status = db.Column(db.String(50))


class Spare(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer)
    machine_id = db.Column(db.Integer, db.ForeignKey('machine.id'))


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100))
    email = db.Column(db.String(100))

DB_NAME = "maintenance.db"
LOW_STOCK_LIMIT = 5  # threshold for low stock

# Email config (replace with your details)
SUPPLIER_EMAIL = "supplier@example.com"
SENDER_EMAIL = "your_email@gmail.com"
SENDER_PASSWORD = "your_app_password"

# ---------- Database Setup ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Machines
    c.execute('''CREATE TABLE IF NOT EXISTS machines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    location TEXT,
                    last_maintenance TEXT
                )''')
    # Logs
    c.execute('''CREATE TABLE IF NOT EXISTS maintenance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_id INTEGER,
                    description TEXT,
                    date TEXT,
                    FOREIGN KEY(machine_id) REFERENCES machines(id)
                )''')
    # Spares
    c.execute('''CREATE TABLE IF NOT EXISTS spares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    stock INTEGER,
                    location TEXT
                )''')
    # Suppliers
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spare_id INTEGER,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    FOREIGN KEY(spare_id) REFERENCES spares(id)
                )''')
    conn.commit()
    conn.close()

init_db()

# ---------- Email Utility ----------
def send_email_with_attachment(file_path, recipients, file_type="PDF"):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = f"Purchase Request ({file_type})"

    body = "Dear Supplier,\n\nPlease find attached the Purchase Request for low-stock items.\n\nRegards,\nFactory MMS"
    msg.attach(MIMEText(body, 'plain'))

    with open(file_path, "rb") as attachment:
        mime_base = MIMEBase('application', 'octet-stream')
        mime_base.set_payload(attachment.read())
        encoders.encode_base64(mime_base)
        mime_base.add_header('Content-Disposition', f'attachment; filename={os.path.basename(file_path)}')
        msg.attach(mime_base)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return f"✅ Email sent to {', '.join(recipients)}"
    except Exception as e:
        return f"❌ Failed to send email: {str(e)}"

# ---------- Dashboard ----------
@app.route('/',endpoint='index')
@app.route('/index')
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Summary counts
    c.execute("SELECT COUNT(*) FROM machines")
    total_machines = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM spares")
    total_spares = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM spares WHERE stock < ?", (LOW_STOCK_LIMIT,))
    low_stock_count = c.fetchone()[0]

    # Recent logs
    c.execute("""
        SELECT maintenance_logs.id, machines.name, maintenance_logs.description, maintenance_logs.date
        FROM maintenance_logs
        JOIN machines ON maintenance_logs.machine_id = machines.id
        ORDER BY maintenance_logs.date DESC LIMIT 5
    """)
    recent_logs = c.fetchall()

    # Machine list for dropdown
    c.execute("SELECT id, name FROM machines")
    machines = c.fetchall()

    conn.close()

    return render_template("index.html",
                           total_machines=total_machines,
                           total_spares=total_spares,
                           low_stock_count=low_stock_count,
                           recent_logs=recent_logs,
                           machines=machines)   # 👈 added machines here


# ---------- Machines ----------
@app.route('/machines_ui')
def machines_ui():
    query = request.args.get("q", "")   # get search term
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if query:
        c.execute("SELECT * FROM machines WHERE name LIKE ? OR id LIKE ? OR location LIKE ?",
                  (f"%{query}%", f"%{query}%", f"%{query}%"))
    else:
        c.execute("SELECT * FROM machines")
    machines = c.fetchall()
    conn.close()
    return render_template("machines.html", machines=machines, query=query)


@app.route('/add_machine_ui', methods=['POST'])
def add_machine_ui():
    name = request.form['name']
    location = request.form['location']
    last_maintenance = request.form['last_maintenance']
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO machines (name, location, last_maintenance) VALUES (?, ?, ?)",
              (name, location, last_maintenance))
    conn.commit()
    conn.close()
    return redirect(url_for('machines_ui'))

# Edit machine
@app.route('/edit_machine/<int:machine_id>', methods=['POST'])
def edit_machine(machine_id):
    name = request.form['name']
    location = request.form['location']
    last_maintenance = request.form['last_maintenance']
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE machines SET name=?, location=?, last_maintenance=? WHERE id=?",
              (name, location, last_maintenance, machine_id))
    conn.commit()
    conn.close()
    return redirect(url_for('machines_ui'))

# Delete machine
@app.route('/delete_machine/<int:machine_id>', methods=['POST'])
def delete_machine(machine_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM machines WHERE id=?", (machine_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('machines_ui'))

# ---------- Spares ----------
@app.route('/spares_ui')
def spares_ui():
    query = request.args.get("q", "")
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if query:
        c.execute("SELECT * FROM spares WHERE name LIKE ? OR id LIKE ? OR location LIKE ?",
                  (f"%{query}%", f"%{query}%", f"%{query}%"))
    else:
        c.execute("SELECT * FROM spares")
    spares = [dict(s) for s in c.fetchall()]
    conn.close()
    return render_template("spares.html", spares=spares, query=query)


@app.route('/add_spare_ui', methods=['POST'])
def add_spare_ui():
    name = request.form['name']
    stock = request.form['stock']
    location = request.form['location']
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO spares (name, stock, location) VALUES (?, ?, ?)",
              (name, stock, location))
    conn.commit()
    conn.close()
    return redirect(url_for('spares_ui'))

# Edit spare
@app.route('/edit_spare/<int:spare_id>', methods=['POST'])
def edit_spare(spare_id):
    name = request.form['name']
    stock = request.form['stock']
    location = request.form['location']
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE spares SET name=?, stock=?, location=? WHERE id=?",
              (name, stock, location, spare_id))
    conn.commit()
    conn.close()
    return redirect(url_for('spares_ui'))

# Delete spare
@app.route('/delete_spare/<int:spare_id>', methods=['POST'])
def delete_spare(spare_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM spares WHERE id=?", (spare_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('spares_ui'))

import os
from flask import render_template

# --- Low stock alerts route ---
@app.route('/low_stock_alerts')
def low_stock_alerts():
    import os
    from flask import render_template

    print("✅ /low_stock_alerts route triggered")

    try:
        threshold = int(os.environ.get('LOW_STOCK_THRESHOLD', 5))
    except ValueError:
        threshold = 5

    try:
        all_spares = Spare.query.all()
        print(f"Fetched {len(all_spares)} spares")
    except Exception as e:
        print("❌ Database error:", e)
        all_spares = []

    low_stock_items = []
    for s in all_spares:
        qty = getattr(s, 'quantity', None) or getattr(s, 'qty', None) or getattr(s, 'quantity_available', None)
        try:
            if qty is not None and int(qty) < threshold:
                low_stock_items.append(s)
        except Exception:
            continue

    print(f"Low stock count: {len(low_stock_items)}")
    try:
        return render_template('low_stock.html', spares=low_stock_items, threshold=threshold)
    except Exception as e:
        print("❌ Template error:", e)
        return f"Template rendering error: {e}", 500



# ---------- Suppliers ----------
@app.route('/suppliers_ui/<int:spare_id>')
def suppliers_ui(spare_id):
    query = request.args.get("q", "")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if query:
        c.execute("SELECT * FROM suppliers WHERE spare_id=? AND (name LIKE ? OR email LIKE ? OR id LIKE ?)",
                  (spare_id, f"%{query}%", f"%{query}%", f"%{query}%"))
    else:
        c.execute("SELECT * FROM suppliers WHERE spare_id=?", (spare_id,))
    suppliers = c.fetchall()
    conn.close()
    return render_template("suppliers.html", suppliers=suppliers, spare_id=spare_id, query=query)

@app.route('/add_supplier_ui/<int:spare_id>', methods=['POST'])
def add_supplier_ui(spare_id):
    name = request.form['name']
    email = request.form['email']
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO suppliers (spare_id, name, email) VALUES (?, ?, ?)",
              (spare_id, name, email))
    conn.commit()
    conn.close()
    return redirect(url_for('suppliers_ui', spare_id=spare_id))

# Edit supplier
@app.route('/edit_supplier/<int:supplier_id>/<int:spare_id>', methods=['POST'])
def edit_supplier(supplier_id, spare_id):
    name = request.form['name']
    email = request.form['email']
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE suppliers SET name=?, email=? WHERE id=?",
              (name, email, supplier_id))
    conn.commit()
    conn.close()
    return redirect(url_for('suppliers_ui', spare_id=spare_id))

# Delete supplier
@app.route('/delete_supplier/<int:supplier_id>/<int:spare_id>', methods=['POST'])
def delete_supplier(supplier_id, spare_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('suppliers_ui', spare_id=spare_id))

# ---------- Maintenance Logs ----------
@app.route('/logs', methods=['POST'])
def add_log():
    data = request.json
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO maintenance_logs (machine_id, description, date) VALUES (?, ?, ?)",
              (data['machine_id'], data['description'], data['date']))
    conn.commit()
    conn.close()
    return jsonify({"message": "Log added successfully"})

@app.route('/add_log_ui', methods=['POST'])
def add_log_ui():
    machine_id = request.form['machine_id']
    description = request.form['description']
    date = request.form['date']

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO maintenance_logs (machine_id, description, date) VALUES (?, ?, ?)",
              (machine_id, description, date))
    conn.commit()
    conn.close()

    return redirect(url_for('dashboard'))

# ---------- Purchase Requests ----------
@app.route('/generate_pr/pdf')
def generate_pr_pdf():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM spares WHERE stock < ?", (LOW_STOCK_LIMIT,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "<h3>✅ No low-stock items</h3>"

    filename = "purchase_request.pdf"
    cpdf = canvas.Canvas(filename, pagesize=A4)
    cpdf.setFont("Helvetica-Bold", 14)
    cpdf.drawString(200, 800, "PURCHASE REQUEST")
    cpdf.setFont("Helvetica", 10)
    cpdf.drawString(50, 780, f"Date: {datetime.date.today()}")

    y = 750
    for spare in rows:
        suggested_qty = LOW_STOCK_LIMIT * 2 - spare[2]
        cpdf.drawString(50, y, str(spare[0]))
        cpdf.drawString(100, y, spare[1])
        cpdf.drawString(250, y, str(spare[2]))
        cpdf.drawString(300, y, spare[3])
        cpdf.drawString(450, y, str(suggested_qty))
        y -= 20
    cpdf.save()
    return send_file(filename, as_attachment=True)

@app.route('/generate_pr/excel')
def generate_pr_excel():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM spares WHERE stock < ?", (LOW_STOCK_LIMIT,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return "<h3>✅ No low-stock items</h3>"

    filename = "purchase_request.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Purchase Request"
    headers = ["ID", "Name", "Stock", "Location", "Suggested Qty"]
    ws.append(headers)

    for spare in rows:
        suggested_qty = LOW_STOCK_LIMIT * 2 - spare[2]
        ws.append([spare[0], spare[1], spare[2], spare[3], suggested_qty])
    wb.save(filename)
    return send_file(filename, as_attachment=True)

@app.route('/send_pr_ui')
def send_pr_ui():
    filename = "purchase_request.pdf"
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM spares WHERE stock < ?", (LOW_STOCK_LIMIT,))
    rows = c.fetchall()
    if not rows:
        return "<h3>✅ No low-stock items</h3>"

    cpdf = canvas.Canvas(filename, pagesize=A4)
    cpdf.setFont("Helvetica-Bold", 14)
    cpdf.drawString(200, 800, "PURCHASE REQUEST")
    y = 750
    for spare in rows:
        suggested_qty = LOW_STOCK_LIMIT * 2 - spare[2]
        cpdf.drawString(50, y, str(spare[0]))
        cpdf.drawString(100, y, spare[1])
        cpdf.drawString(250, y, str(spare[2]))
        cpdf.drawString(300, y, spare[3])
        cpdf.drawString(450, y, str(suggested_qty))
        y -= 20
    cpdf.save()

    supplier_emails = []
    for spare in rows:
        spare_id = spare[0]
        c.execute("SELECT email FROM suppliers WHERE spare_id=?", (spare_id,))
        supplier_rows = c.fetchall()
        supplier_emails.extend([row[0] for row in supplier_rows])
    conn.close()

    if not supplier_emails:
        return "<h3 style='color:red'>❌ No suppliers linked</h3>"

    result = send_email_with_attachment(filename, supplier_emails)
    return f"<h3>{result}</h3><a href='/'>⬅ Back</a>"
with app.app_context():
    db.create_all()

# ---------- Run ----------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

