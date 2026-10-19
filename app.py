# ==========================================
# 🚨 CRITICAL: Eventlet Monkey Patch (Must be first)
# ==========================================
import eventlet
eventlet.monkey_patch()

import os
import io
import csv
import json
import hashlib
import razorpay
import requests
import qrcode
import base64
from datetime import datetime, date
from functools import wraps
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, make_response, send_file
from flask_socketio import SocketIO, emit
from xhtml2pdf import pisa
import google.generativeai as genai
from fpdf import FPDF

# Local Database Functions
from database import init_db, run, all as db_all, one, current_month, today

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school-secret-key-2026")

# ---------------- SETUPS ----------------
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Gemini AI
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash') # Updated to 1.5 flash
else:
    ai_model = None

# Razorpay Payment Gateway
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_dummy")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "dummy_secret")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# File Uploads
UPLOAD_FOLDER = 'static/uploads/students'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------- AUTH DECORATOR ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if session.get("role") != "admin":
            flash("Access denied! Admin only.", "error")
            return redirect(url_for("dashboard"))
        return f(*a, **kw)
    return wrapper

# ==========================================
# 🔐 AUTHENTICATION & LOGIN
# ==========================================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        
        # Admin Login
        if u == "admin" and p == "admin123":
            session["user"] = u
            session["role"] = "admin"
            session["name"] = "System Admin"
            return redirect(url_for("dashboard"))
        
        # Parent Login
        student = one("SELECT * FROM students WHERE roll_no=%s AND parent_contact=%s", (u, p))
        if student:
            session["user"] = student["roll_no"]
            session["role"] = "parent"
            session["name"] = student["father"]
            return redirect(url_for("parent_dashboard"))
            
        flash("Invalid credentials!", "error")
    return render_template("auth/login.html")

@app.route("/parent/login", methods=["GET", "POST"])
def parent_login():
    return render_template("auth/parent_login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ==========================================
# 📊 DASHBOARD & LIVE APIS
# ==========================================
@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "parent":
        return redirect(url_for("parent_dashboard"))
    try:
        students_count = one("SELECT COUNT(*) c FROM students")["c"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
        today_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date = %s", (today(),))["t"]
        
        recent_payments = db_all("SELECT s.name, p.amount, p.pay_date FROM payments p JOIN students s ON p.roll_no = s.roll_no ORDER BY p.id DESC LIMIT 5")
        payment_feed = [{"name": r["name"], "amount": float(r["amount"]), "date": str(r["pay_date"])} for r in recent_payments]
    except Exception as e:
        students_count, total_due, today_collection, payment_feed = 0, 0, 0, []

    return render_template("dashboard/dashboard.html", students_count=students_count, pending_dues=total_due, today_collection=today_collection, payment_feed=payment_feed)

@app.route("/api/dashboard-live")
@login_required
def api_dashboard_live():
    try:
        students_count = one("SELECT COUNT(*) c FROM students")["c"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
        today_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date = %s", (today(),))["t"]
        recent_payments = db_all("SELECT s.name, p.amount, p.pay_date FROM payments p JOIN students s ON p.roll_no = s.roll_no ORDER BY p.id DESC LIMIT 5")
        return jsonify({
            "status": "success", "students_count": students_count, "total_due": float(total_due), "today_collection": float(today_collection),
            "payment_feed": [{"name": r["name"], "amount": float(r["amount"]), "date": str(r["pay_date"])} for r in recent_payments]
        })
    except Exception as e:
        return jsonify({"status": "error"})

@app.route("/api/global-search")
@login_required
def api_global_search():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    students = db_all("SELECT roll_no, name, class_name, father, parent_contact, photo_url FROM students WHERE roll_no LIKE %s OR name LIKE %s LIMIT 10", (f"%{q}%", f"%{q}%"))
    results = []
    for s in students:
        s_dict = dict(s)
        if not s_dict.get('photo_url'):
            s_dict['photo_url'] = f"https://api.dicebear.com/7.x/initials/svg?seed={s_dict['name']}&backgroundColor=00f3ff"
        results.append(s_dict)
    return jsonify(results)

# ==========================================
# 👨‍👩‍👦 PARENT PORTAL
# ==========================================
@app.route("/parent/dashboard")
@login_required
def parent_dashboard():
    if session.get("role") != "parent":
        return redirect(url_for("dashboard"))
    roll_no = session.get("user")
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
    recent_payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY id DESC LIMIT 5", (roll_no,))
    return render_template("parent_portal.html", student=student, total_due=total_due, recent_payments=recent_payments)

# ==========================================
# 👨‍🎓 STUDENTS MODULE
# ==========================================
@app.route("/students")
@login_required
def students():
    search_query = request.args.get("search", "").strip()
    query = "SELECT * FROM students WHERE 1=1"
    params = []
    if search_query:
        query += " AND (name LIKE %s OR roll_no LIKE %s)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])
    query += " ORDER BY LENGTH(roll_no), roll_no ASC"
    students_list = db_all(query, tuple(params))
    return render_template("students/students.html", students=students_list, search_query=search_query)

@app.route("/student/add", methods=["POST"])
@login_required
def add_student():
    d = request.form
    try:
        run("INSERT INTO students (roll_no, name, class_name, father, parent_contact) VALUES (%s, %s, %s, %s, %s)",
            (d["roll_no"], d["name"], d.get("class_name", ""), d.get("father", ""), d.get("parent_contact", "")))
        flash("✅ Student added successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e} (Roll No might already exist)", "error")
    return redirect(url_for("students"))

@app.route("/student/profile/<roll_no>")
@login_required
def student_profile(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student: return redirect(url_for("students"))
    
    # Safe Dict handling
    student = dict(student)
    if not student.get('photo_url'):
        student['photo_url'] = f"https://api.dicebear.com/7.x/initials/svg?seed={student['name']}&backgroundColor=00f3ff"

    total_paid = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE roll_no=%s", (roll_no,))["t"]
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
    marks_data = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
    recent_payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY id DESC LIMIT 5", (roll_no,))
    
    growth_labels = ["Unit Test 1", "Half Yearly", "Unit Test 2", "Pre-Board", "Final"]
    growth_data = [65, 72, 78, 85, 88] # Placeholder for now

    total_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll_no,))["c"]
    present_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll_no,))["c"]
    attendance_pct = round((present_days / total_days * 100), 2) if total_days > 0 else 0
    
    att_records = db_all("SELECT att_date, status FROM attendance WHERE roll_no=%s ORDER BY att_date ASC", (roll_no,))
    heatmap_data = {str(r['att_date']): r['status'] for r in att_records}

    try: documents = db_all("SELECT * FROM student_documents WHERE roll_no=%s ORDER BY id DESC", (roll_no,))
    except: documents = []

    try: discipline_logs = db_all("SELECT * FROM student_discipline WHERE roll_no=%s ORDER BY id DESC", (roll_no,))
    except: discipline_logs = []

    return render_template("students/student_profile.html", student=student, total_paid=total_paid, total_due=total_due, 
                           marks_data=marks_data, growth_labels=growth_labels, growth_data=growth_data,
                           recent_payments=recent_payments, heatmap_data=heatmap_data,
                           total_days=total_days, present_days=present_days, attendance_pct=attendance_pct, 
                           documents=documents, discipline_logs=discipline_logs)

@app.route("/student/edit/<roll_no>", methods=["GET", "POST"])
@login_required
def edit_student(roll_no):
    if request.method == "POST":
        d = request.form
        try:
            run("UPDATE students SET name=%s, class_name=%s, father=%s, parent_contact=%s WHERE roll_no=%s",
                (d["name"], d.get("class_name", ""), d.get("father", ""), d.get("parent_contact", ""), roll_no))
            return jsonify({"status": "success", "message": "Student updated successfully!"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
    
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    return render_template("students/edit_student.html", student=student)

@app.route("/student/delete/<roll_no>")
@login_required
def delete_student(roll_no):
    try:
        run("DELETE FROM marks WHERE roll_no=%s", (roll_no,))
        run("DELETE FROM attendance WHERE roll_no=%s", (roll_no,))
        run("DELETE FROM payments WHERE roll_no=%s", (roll_no,))
        run("DELETE FROM bills WHERE roll_no=%s", (roll_no,))
        run("DELETE FROM students WHERE roll_no=%s", (roll_no,))
        flash("🗑️ Student deleted successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("students"))

@app.route("/student/upload_photo/<roll_no>", methods=["POST"])
@login_required
def upload_photo(roll_no):
    if 'photo' not in request.files: return jsonify({"status": "error"})
    file = request.files['photo']
    if file:
        filename = secure_filename(f"student_{roll_no}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        db_path = f"/static/uploads/students/{filename}"
        run("UPDATE students SET photo_url=%s WHERE roll_no=%s", (db_path, roll_no))
        return jsonify({"status": "success", "url": db_path})

# ==========================================
# 💵 ULTIMATE FEE MANAGEMENT ENGINE
# ==========================================
@app.route("/fees")
@login_required
def fees():
    rows = db_all("""
        SELECT s.roll_no, s.name, s.class_name, s.section, s.parent_contact, s.father,
               f.tuition_fee, f.transport_fee, f.hostel_fee, f.misc_fee, 
               f.discount, f.late_fee, f.back_dues, f.due_date, f.wallet_balance
        FROM students s 
        LEFT JOIN student_fees f ON s.roll_no = f.roll_no
        ORDER BY s.roll_no
    """)
    
    sibling_fathers = {}
    for r in rows:
        if r['father']: sibling_fathers[r['father']] = sibling_fathers.get(r['father'], 0) + 1

    current_dt = date.today()
    aging_stats = {"0-30": 0, "30-60": 0, "60+": 0} 
    processed_rows = []
    
    for r in rows:
        r_dict = dict(r)
        dues = r_dict['back_dues'] or 0
        aging_bucket = "Clear"
        if dues > 0 and r_dict['due_date']:
            try:
                if isinstance(r_dict['due_date'], str): d_date = datetime.strptime(r_dict['due_date'], '%Y-%m-%d').date()
                else: d_date = r_dict['due_date']
                days_overdue = (current_dt - d_date).days
                if days_overdue <= 0: aging_bucket = "Current"
                elif days_overdue <= 30: aging_bucket = "0-30 Days"; aging_stats["0-30"] += dues
                elif days_overdue <= 60: aging_bucket = "30-60 Days"; aging_stats["30-60"] += dues
                else: aging_bucket = "60+ Days"; aging_stats["60+"] += dues
            except: aging_bucket = "N/A"
                
        r_dict['aging_bucket'] = aging_bucket
        r_dict['is_sibling'] = (r_dict['father'] and sibling_fathers.get(r_dict['father'], 0) > 1)
        r_dict['wallet'] = r_dict['wallet_balance'] or 0
        processed_rows.append(r_dict)
        
    return render_template("fees/fees.html", fees=processed_rows, aging_stats=aging_stats)

@app.route("/fees/save", methods=["POST"])
@login_required
def save_fees():
    d = request.form
    roll = d["roll_no"]
    existing = one("SELECT id FROM student_fees WHERE roll_no=%s", (roll,))
    vals = (float(d.get("tuition_fee") or 0), float(d.get("transport_fee") or 0), float(d.get("hostel_fee") or 0), 
            float(d.get("misc_fee") or 0), float(d.get("discount") or 0), float(d.get("late_fee") or 0),
            float(d.get("back_dues") or 0), d.get("due_date") or None, float(d.get("wallet_balance") or 0), roll)
    
    if existing:
        run("""UPDATE student_fees SET tuition_fee=%s, transport_fee=%s, hostel_fee=%s, misc_fee=%s,
            discount=%s, late_fee=%s, back_dues=%s, due_date=%s, wallet_balance=%s WHERE roll_no=%s""", vals)
        flash("✅ Fee structure updated!", "success")
    else:
        run("""INSERT INTO student_fees (tuition_fee,transport_fee,hostel_fee,misc_fee,
             discount,late_fee,back_dues,due_date,wallet_balance,roll_no) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
        flash("✅ New Fee structure added!", "success")
    return redirect(url_for("fees"))

@app.route("/fees/delete/<roll_no>")
@login_required
def delete_fees(roll_no):
    run("DELETE FROM student_fees WHERE roll_no=%s", (roll_no,))
    flash("🗑️ Fee record deleted!", "success")
    return redirect(url_for("fees"))

@app.route("/fees/waive-off", methods=["POST"])
@login_required
def waive_off_fees():
    roll_no = request.form.get("roll_no")
    run("UPDATE student_fees SET back_dues=0 WHERE roll_no=%s", (roll_no,))
    flash(f"⚖️ Roll No {roll_no} ke dues maaf kar diye gaye hain.", "success")
    return redirect(url_for('fees'))

@app.route("/fees/ai-advisor", methods=["POST"])
@login_required
def fees_ai_advisor():
    if not ai_model: return jsonify({"reply": "AI API key configure nahi hai."})
    total_pending = one("SELECT SUM(back_dues) t FROM student_fees")['t'] or 0
    total_collected = one("SELECT SUM(amount) t FROM payments")['t'] or 0
    
    prompt = f"Total Pending Dues: Rs {total_pending}, Total Collected: Rs {total_collected}. Give 3 short, actionable bullet points in Hinglish on how to recover pending dues faster. Keep it under 60 words."
    try: return jsonify({"reply": ai_model.generate_content(prompt).text})
    except Exception as e: return jsonify({"reply": f"Error: {str(e)}"})

@app.route("/fees/ai-reminder/<roll_no>", methods=["GET"])
@login_required
def fees_ai_reminder(roll_no):
    student = one("SELECT name, class_name, parent_contact FROM students WHERE roll_no=%s", (roll_no,))
    fee = one("SELECT back_dues FROM student_fees WHERE roll_no=%s", (roll_no,))
    dues = fee['back_dues'] if fee else 0
    msg = f"Dear Parent, {student['name']} (Class {student['class_name']}) ki fees me Rs {dues} pending hai. Kripya jaldi jama karein. - School ERP"
    
    if ai_model:
        try:
            prompt = f"Write a very polite, short 2-line WhatsApp reminder in Hinglish for parent of {student['name']}. Pending amount is Rs {dues}. No formal English."
            msg = ai_model.generate_content(prompt).text.strip()
        except: pass
    return jsonify({"message": msg, "contact": student['parent_contact']})

@app.route("/fees/upi-qr/<roll_no>")
@login_required
def generate_upi_qr(roll_no):
    fee = one("SELECT back_dues FROM student_fees WHERE roll_no=%s", (roll_no,))
    amount = fee['back_dues'] if fee else 0
    if amount <= 0: return jsonify({"error": "No pending dues!"})
    
    upi_string = f"upi://pay?pa=school@upi&pn=School ERP&am={amount}&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=2); qr.add_data(upi_string); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO(); img.save(buffered, format="PNG")
    return jsonify({"qr_code": base64.b64encode(buffered.getvalue()).decode(), "amount": amount})

@app.route("/fees/pdf/<roll_no>")
@login_required
def fee_pdf(roll_no):
    s = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    f = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll_no,))
    if not s or not f: return redirect(url_for('fees'))

    pdf = FPDF(); pdf.add_page()
    pdf.set_font("Arial", 'B', 20); pdf.cell(200, 10, txt="SCHOOL MANAGEMENT SYSTEM", ln=True, align='C')
    pdf.set_font("Arial", 'I', 12); pdf.cell(200, 10, txt="Official Fee Receipt", ln=True, align='C'); pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, txt=f"Student Name: {s['name']}", ln=False)
    pdf.cell(90, 10, txt=f"Roll No: {s['roll_no']}", ln=True)
    pdf.cell(100, 10, txt=f"Class: {s['class_name']}-{s.get('section', '')}", ln=False)
    pdf.cell(90, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True); pdf.ln(5)
    
    pdf.set_fill_color(240, 240, 240); pdf.cell(100, 10, "Particulars", border=1, fill=True); pdf.cell(90, 10, "Amount (Rs)", border=1, fill=True, ln=True)
    total = 0
    items = [("Tuition Fee", f['tuition_fee'] or 0), ("Transport Fee", f['transport_fee'] or 0), ("Hostel Fee", f['hostel_fee'] or 0), 
             ("Misc Fee", f['misc_fee'] or 0), ("Discount", -(f['discount'] or 0)), ("Late Fee", f['late_fee'] or 0), ("Back Dues", f['back_dues'] or 0)]
             
    for name, amt in items:
        pdf.cell(100, 10, name, border=1); pdf.cell(90, 10, str(amt), border=1, ln=True); total += amt
        
    pdf.set_font("Arial", 'B', 12); pdf.cell(100, 10, "Grand Total", border=1); pdf.cell(90, 10, str(total), border=1, ln=True)
    return send_file(io.BytesIO(pdf.output(dest='S').encode('latin-1')), mimetype="application/pdf", as_attachment=True, download_name=f"Receipt_{roll_no}.pdf")

# ==========================================
# 💰 PAYMENTS & TRANSACTIONS
# ==========================================
@app.route("/collect/<roll_no>", methods=["GET", "POST"])
@login_required
def collect(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if request.method == "POST":
        amount = float(request.form.get("amount") or 0)
        receipt_no = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        run("INSERT INTO payments (receipt_no, roll_no, amount, mode, pay_date, remark) VALUES (%s, %s, %s, %s, %s, %s)",
            (receipt_no, roll_no, amount, request.form.get("mode", "Cash"), today(), request.form.get("remark", "")))
        
        bills_list = db_all("SELECT id, balance, paid, total FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
        rem = amount
        for b in bills_list:
            if rem <= 0: break
            deduct = min(rem, float(b['balance']))
            new_paid = float(b['paid']) + deduct
            new_bal = float(b['total']) - new_paid
            run("UPDATE bills SET paid=%s, balance=%s, status=%s WHERE id=%s", (new_paid, new_bal, "Paid" if new_bal <= 0 else "Partial", b['id']))
            rem -= deduct
            
        socketio.emit('new_payment_alert', {'name': student['name'], 'amount': amount, 'msg': f"₹{amount} paid by {student['name']}"})
        flash(f"✅ ₹{amount} collected successfully!", "success")
        return redirect(url_for("student_profile", roll_no=roll_no))
        
    bills_list = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
    return render_template("fees/collect.html", student=student, bills=bills_list, total_due=sum(float(b['balance']) for b in bills_list))

@app.route("/api/create-payment-order", methods=["POST"])
@login_required
def create_payment_order():
    try:
        order = rzp_client.order.create({'amount': float(request.json.get("amount")) * 100, 'currency': 'INR', 'receipt': f'rcpt_{session.get("user")}', 'payment_capture': 1})
        return jsonify({"status": "success", "order_id": order['id'], "key": RAZORPAY_KEY_ID})
    except Exception as e: return jsonify({"status": "error", "message": str(e)})

# ==========================================
# 🧠 AI FEATURES & TOOLS
# ==========================================
@app.route("/ai-assistant")
@login_required
def ai_assistant():
    return render_template("ai_assistant.html")

@app.route("/api/ai-chat", methods=["POST"])
@login_required
def api_ai_chat():
    if not ai_model: return jsonify({"reply": "⚠️ AI Configure nahi hai."})
    try: return jsonify({"reply": ai_model.generate_content(request.json.get("message", "")).text})
    except Exception as e: return jsonify({"reply": f"❌ AI Error: {str(e)}"})

@app.route("/api/scan-attendance", methods=["POST"])
@login_required
def api_scan_attendance():
    roll_no = request.json.get("roll_no")
    if not roll_no: return jsonify({"status": "error", "message": "Invalid QR"})
    student = one("SELECT name FROM students WHERE roll_no=%s", (roll_no,))
    if not student: return jsonify({"status": "error", "message": "Student not found!"})
    
    existing = one("SELECT id FROM attendance WHERE roll_no=%s AND att_date=%s", (roll_no, today()))
    if existing: run("UPDATE attendance SET status='Present' WHERE id=%s", (existing['id'],))
    else: run("INSERT INTO attendance (roll_no, att_date, status) VALUES (%s, %s, 'Present')", (roll_no, today()))
    return jsonify({"status": "success", "message": f"Present marked for {student['name']}"})

# ---------------- APP RUN ----------------
if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True)
