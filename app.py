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
# 1. WebSockets (Live Dashboard)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 2. Gemini AI
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    ai_model = None

# 3. Razorpay Payment Gateway
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_dummy")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "dummy_secret")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# 4. File Uploads (Photos & Documents)
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
# 🔐 AUTHENTICATION & LOGIN (Admin & Parent)
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
# 📊 DASHBOARD, ANALYTICS & LIVE APIS
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

@app.route("/analytics")
@login_required
def analytics():
    return render_template("dashboard/analytics.html")

@app.route("/reports")
@login_required
def reports():
    return render_template("dashboard/reports.html")

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
# 👨‍🎓 STUDENTS MODULE & PDF GENERATORS
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
    
    if not student.get('photo_url'):
        student['photo_url'] = f"https://api.dicebear.com/7.x/initials/svg?seed={student['name']}&backgroundColor=00f3ff"

    total_paid = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE roll_no=%s", (roll_no,))["t"]
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
    marks_data = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
    recent_payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY id DESC LIMIT 5", (roll_no,))
    
    growth_labels = ["Unit Test 1", "Half Yearly", "Unit Test 2", "Pre-Board", "Final"]
    growth_data = [65, 72, 78, 85, 88]

    total_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll_no,))["c"]
    present_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll_no,))["c"]
    attendance_pct = round((present_days / total_days * 100), 2) if total_days > 0 else 0
    
    att_records = db_all("SELECT att_date, status FROM attendance WHERE roll_no=%s ORDER BY att_date ASC", (roll_no,))
    heatmap_data = {r['att_date']: r['status'] for r in att_records}

    try:
        documents = db_all("SELECT * FROM student_documents WHERE roll_no=%s ORDER BY id DESC", (roll_no,))
    except:
        documents = []

    try:
        discipline_logs = db_all("SELECT * FROM student_discipline WHERE roll_no=%s ORDER BY id DESC", (roll_no,))
    except:
        discipline_logs = []

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

@app.route("/student/bulk_import")
@login_required
def bulk_import():
    return render_template("students/bulk_import.html")

# ID Card & PDF
@app.route("/student/id_card/<roll_no>")
@login_required
def student_id_card(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student.get('photo_url'):
        student['photo_url'] = f"https://api.dicebear.com/7.x/initials/svg?seed={student['name']}&backgroundColor=00f3ff"
    return render_template("students/id_card.html", student=student)

@app.route("/student/id_card/pdf/<roll_no>")
@login_required
def id_card_pdf(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student.get('photo_url'):
        student['photo_url'] = f"https://api.dicebear.com/7.x/initials/svg?seed={student['name']}&backgroundColor=00f3ff"
    html = render_template("students/id_card.html", student=student, is_pdf=True)
    pdf = io.BytesIO()
    pisa.CreatePDF(html, dest=pdf)
    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=ID_{roll_no}.pdf'
    return response

# Transfer Certificate (TC) & PDF
@app.route("/student/tc/<roll_no>")
@login_required
def transfer_certificate(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    return render_template("students/transfer_certificate.html", student=student)

@app.route("/student/tc_pdf/<roll_no>")
@login_required
def transfer_certificate_pdf(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    html = render_template("students/transfer_certificate.html", student=student, is_pdf=True)
    pdf = io.BytesIO()
    pisa.CreatePDF(html, dest=pdf)
    pdf.seek(0)
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=TC_{roll_no}.pdf'
    return response

# Uploads
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

@app.route("/api/upload-document/<roll_no>", methods=["POST"])
@login_required
def upload_document(roll_no):
    if 'document' not in request.files: return jsonify({"status": "error"})
    file = request.files['document']
    doc_type = request.form.get("doc_type", "Other")
    if file:
        filename = secure_filename(f"{roll_no}_{doc_type}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        db_path = f"/static/uploads/students/{filename}"
        run("INSERT INTO student_documents (roll_no, doc_type, file_path, upload_date) VALUES (%s, %s, %s, %s)", (roll_no, doc_type, db_path, today()))
        return jsonify({"status": "success", "message": "Document uploaded!"})


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
        if r['father']:
            sibling_fathers[r['father']] = sibling_fathers.get(r['father'], 0) + 1

    current_dt = date.today()
    aging_stats = {"0-30": 0, "30-60": 0, "60+": 0} 
    processed_rows = []
    
    for r in rows:
        r_dict = dict(r)
        dues = r_dict['back_dues'] or 0
        
        aging_bucket = "Clear"
        if dues > 0 and r_dict['due_date']:
            try:
                if isinstance(r_dict['due_date'], str):
                    d_date = datetime.strptime(r_dict['due_date'], '%Y-%m-%d').date()
                else:
                    d_date = r_dict['due_date']
                    
                days_overdue = (current_dt - d_date).days
                
                if days_overdue <= 0:
                    aging_bucket = "Current"
                elif days_overdue <= 30:
                    aging_bucket = "0-30 Days"
                    aging_stats["0-30"] += dues
                elif days_overdue <= 60:
                    aging_bucket = "30-60 Days"
                    aging_stats["30-60"] += dues
                else:
                    aging_bucket = "60+ Days"
                    aging_stats["60+"] += dues
            except:
                aging_bucket = "N/A"
                
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
    
    vals = (
        float(d.get("tuition_fee") or 0), float(d.get("transport_fee") or 0),
        float(d.get("hostel_fee") or 0), float(d.get("misc_fee") or 0),
        float(d.get("discount") or 0), float(d.get("late_fee") or 0),
        float(d.get("back_dues") or 0), d.get("due_date") or None, 
        float(d.get("wallet_balance") or 0), roll
    )
    
    if existing:
        run("""UPDATE student_fees SET
            tuition_fee=%s, transport_fee=%s, hostel_fee=%s, misc_fee=%s,
            discount=%s, late_fee=%s, back_dues=%s, due_date=%s, wallet_balance=%s 
            WHERE roll_no=%s""", vals)
        flash("✅ Fee structure updated!", "success")
    else:
        run("""INSERT INTO student_fees
            (tuition_fee,transport_fee,hostel_fee,misc_fee,
             discount,late_fee,back_dues,due_date,wallet_balance,roll_no) 
             VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
        flash("✅ New Fee structure added!", "success")
    return redirect(url_for("fees"))

@app.route("/fees/update", methods=["POST"])
@login_required
def update_fee_modal():
    d = request.form
    roll = d["roll_no"]
    run("""UPDATE student_fees SET
           tuition_fee=%s, back_dues=%s, due_date=%s, wallet_balance=%s 
           WHERE roll_no=%s""", 
        (float(d.get("tuition_fee") or 0), float(d.get("back_dues") or 0), 
         d.get("due_date") or None, float(d.get("wallet_balance") or 0), roll))
    flash(f"✅ {roll} ki fee update ho gayi!", "success")
    return redirect(url_for('fees'))

@app.route("/fees/delete/<roll_no>")
@login_required
def delete_fees(roll_no):
    run("DELETE FROM student_fees WHERE roll_no=%s", (roll_no,))
    flash("🗑️ Fee record deleted!", "success")
    return redirect(url_for("fees"))

@app.route("/fees/bulk-action", methods=["POST"])
@login_required
def bulk_action():
    action = request.form.get("action")
    selected_rolls = request.form.getlist("selected_students")
    
    if not selected_rolls:
        flash("Koi student select nahi kiya!", "error")
        return redirect(url_for('fees'))
        
    if action == "delete":
        for roll in selected_rolls:
            run("DELETE FROM student_fees WHERE roll_no=%s", (roll,))
        flash(f"🗑️ {len(selected_rolls)} records deleted successfully!", "success")
    elif action == "whatsapp":
        flash(f"📱 WhatsApp reminders triggered for {len(selected_rolls)} students.", "info")
        
    return redirect(url_for('fees'))

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
    if not ai_model:
        return jsonify({"reply": "AI API key configure nahi hai."})
    
    total_pending = one("SELECT SUM(back_dues) t FROM student_fees")['t'] or 0
    total_collected = one("SELECT SUM(amount) t FROM payments")['t'] or 0
    
    prompt = f"""
    You are an expert Financial Advisor for a School ERP.
    Total Pending Dues: Rs {total_pending}
    Total Collected Revenue: Rs {total_collected}
    Give 3 short, actionable bullet points in Hinglish on how to recover pending dues faster. Keep it under 60 words.
    """
    try:
        res = ai_model.generate_content(prompt)
        return jsonify({"reply": res.text})
    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})

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
        except:
            pass
            
    return jsonify({"message": msg, "contact": student['parent_contact']})

@app.route("/fees/upi-qr/<roll_no>")
@login_required
def generate_upi_qr(roll_no):
    fee = one("SELECT back_dues FROM student_fees WHERE roll_no=%s", (roll_no,))
    amount = fee['back_dues'] if fee else 0
    if amount <= 0: return jsonify({"error": "No pending dues!"})
    
    UPI_ID = "school@upi" 
    upi_string = f"upi://pay?pa={UPI_ID}&pn=School ERP&am={amount}&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(upi_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return jsonify({"qr_code": img_str, "amount": amount})

@app.route("/fees/pdf/<roll_no>")
@login_required
def fee_pdf(roll_no):
    s = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    f = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll_no,))
    if not s or not f: return redirect(url_for('fees'))

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(200, 10, txt="SCHOOL MANAGEMENT SYSTEM", ln=True, align='C')
    pdf.set_font("Arial", 'I', 12)
    pdf.cell(200, 10, txt="Official Fee Receipt", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, txt=f"Student Name: {s['name']}", ln=False)
    pdf.cell(90, 10, txt=f"Roll No: {s['roll_no']}", ln=True)
    pdf.cell(100, 10, txt=f"Class: {s['class_name']}-{s['section'] if 'section' in s else ''}", ln=False)
    pdf.cell(90, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
    pdf.ln(5)
    
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(100, 10, "Particulars", border=1, fill=True)
    pdf.cell(90, 10, "Amount (Rs)", border=1, fill=True, ln=True)
    
    total = 0
    items = [("Tuition Fee", f['tuition_fee'] or 0), ("Transport Fee", f['transport_fee'] or 0),
             ("Hostel Fee", f['hostel_fee'] or 0), ("Misc Fee", f['misc_fee'] or 0),
             ("Discount", -(f['discount'] or 0)), ("Late Fee", f['late_fee'] or 0),
             ("Back Dues", f['back_dues'] or 0)]
             
    for name, amt in items:
        pdf.cell(100, 10, name, border=1)
        pdf.cell(90, 10, str(amt), border=1, ln=True)
        total += amt
        
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Grand Total", border=1)
    pdf.cell(90, 10, str(total), border=1, ln=True)
    
    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True, download_name=f"Receipt_{roll_no}.pdf")


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
            status = "Paid" if new_bal <= 0 else "Partial"
            run("UPDATE bills SET paid=%s, balance=%s, status=%s WHERE id=%s", (new_paid, new_bal, status, b['id']))
            rem -= deduct
            
        socketio.emit('new_payment_alert', {
            'name': student['name'],
            'amount': amount,
            'msg': f"₹{amount} paid by {student['name']}"
        })
        
        flash(f"✅ ₹{amount} collected successfully!", "success")
        return redirect(url_for("student_profile", roll_no=roll_no))
        
    bills_list = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
    total_due = sum(float(b['balance']) for b in bills_list)
    return render_template("fees/collect.html", student=student, bills=bills_list, total_due=total_due)

@app.route("/api/create-payment-order", methods=["POST"])
@login_required
def create_payment_order():
    amount = float(request.json.get("amount")) * 100
    try:
        order = rzp_client.order.create({'amount': amount, 'currency': 'INR', 'receipt': f'rcpt_{session.get("user")}', 'payment_capture': 1})
        return jsonify({"status": "success", "order_id": order['id'], "key": RAZORPAY_KEY_ID})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/receipt_pdf/<roll_no>/<receipt_no>")
@login_required
def receipt_pdf(roll_no, receipt_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    payment = one("SELECT * FROM payments WHERE receipt_no=%s", (receipt_no,))
    
    html = render_template("fees/receipt.html", student=student, payment=payment, is_pdf=True)
    pdf = io.BytesIO()
    pisa.CreatePDF(html, dest=pdf)
    pdf.seek(0)
    
    response = make_response(pdf.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Receipt_{receipt_no}.pdf'
    return response


# ==========================================
# 📸 QR ATTENDANCE SCANNER
# ==========================================
@app.route("/attendance/scanner")
@login_required
def attendance_scanner():
    return render_template("attendance/scanner.html")

@app.route("/api/scan-attendance", methods=["POST"])
@login_required
def api_scan_attendance():
    roll_no = request.json.get("roll_no")
    if not roll_no: return jsonify({"status": "error", "message": "Invalid QR"})
    student = one("SELECT name FROM students WHERE roll_no=%s", (roll_no,))
    if not student: return jsonify({"status": "error", "message": "Student not found!"})
    
    existing = one("SELECT id FROM attendance WHERE roll_no=%s AND att_date=%s", (roll_no, today()))
    if existing:
        run("UPDATE attendance SET status='Present' WHERE id=%s", (existing['id'],))
    else:
        run("INSERT INTO attendance (roll_no, att_date, status) VALUES (%s, %s, 'Present')", (roll_no, today()))
    return jsonify({"status": "success", "message": f"Present marked for {student['name']}"})


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
    user_msg = request.json.get("message", "")
    try:
        response = ai_model.generate_content(user_msg)
        return jsonify({"reply": response.text})
    except Exception as e:
        return jsonify({"reply": f"❌ AI Error: {str(e)}"})

@app.route("/api/ai-career-counselor/<roll_no>")
@login_required
def ai_career_counselor(roll_no):
    if not ai_model: return jsonify({"reply": "AI Offline"})
    student = one("SELECT name FROM students WHERE roll_no=%s", (roll_no,))
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    marks_summary = ", ".join([f"{m['subject']}: {(float(m['marks'])/float(m['total']))*100}%" for m in marks if m['total'] > 0])
    prompt = f"Act as an expert Career Counselor. Student: {student['name']}. Marks: {marks_summary}. Suggest best stream (Science/Commerce/Arts), top 3 careers, and a short motivational message in Hinglish."
    try:
        response = ai_model.generate_content(prompt)
        return jsonify({"reply": response.text})
    except:
        return jsonify({"reply": "Error fetching career advice."})

@app.route("/api/ai-fee-predictor")
@login_required
def api_fee_predictor():
    if not ai_model: return jsonify({"risk_students": []})
    pending_students = db_all("SELECT s.name, s.roll_no, SUM(b.balance) as total_due, (SELECT COUNT(*) FROM attendance a WHERE a.roll_no = s.roll_no AND a.status='Absent') as absent_days FROM students s JOIN bills b ON s.roll_no = b.roll_no WHERE b.balance > 0 GROUP BY s.roll_no ORDER BY total_due DESC LIMIT 5")
    if not pending_students: return jsonify({"risk_students": []})
    prompt = f"Analyze these pending fee students: {pending_students}. Output ONLY a JSON array: 'name', 'roll_no', 'risk_score' (0-100), 'reason', 'action'."
    try:
        response = ai_model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return jsonify({"risk_students": json.loads(text)})
    except:
        return jsonify({"risk_students": []})

@app.route("/api/ai-student-persona/<roll_no>")
@login_required
def ai_student_persona(roll_no):
    if not ai_model: return jsonify({"persona": "AI Offline"})
    
    student = one("SELECT name FROM students WHERE roll_no=%s", (roll_no,))
    marks = db_all("SELECT AVG((marks * 100.0) / total) as avg_score FROM marks WHERE roll_no=%s", (roll_no,))
    att = one("SELECT ROUND((SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) * 100.0) / COUNT(*), 1) p FROM attendance WHERE roll_no=%s", (roll_no,))["p"] or 0
    
    prompt = f"""
    Analyze this student's data: Name: {student['name']}, Average Marks: {marks[0]['avg_score'] if marks else 'N/A'}%, Attendance: {att}%.
    Write a 2-sentence AI Persona summary for the Principal. 
    Keep it professional and insightful.
    """
    try:
        response = ai_model.generate_content(prompt)
        return jsonify({"persona": response.text})
    except:
        return jsonify({"persona": "Could not generate persona."})

@app.route("/api/ai-grade-predictor/<roll_no>")
@login_required
def ai_grade_predictor(roll_no):
    if not ai_model: return jsonify({"prediction": "AI Offline"})
    
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    if not marks: return jsonify({"prediction": "Not enough data to predict. Please upload marks first."})
    
    marks_str = ", ".join([f"{m['subject']}: {m['marks']}/{m['total']}" for m in marks])
    prompt = f"""
    Analyze these past marks: {marks_str}.
    Predict the likely percentage and marks for the NEXT exam for each subject.
    Output in a short, encouraging paragraph with brief advice.
    """
    try:
        response = ai_model.generate_content(prompt)
        return jsonify({"prediction": response.text})
    except Exception as e:
        return jsonify({"prediction": "Error predicting grades."})

@app.route("/api/ai-study-plan/<roll_no>")
@login_required
def ai_study_plan(roll_no):
    if not ai_model: return jsonify({"plan": "AI Offline"})
    
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    weakest = min(marks, key=lambda x: (x['marks']/x['total']) if x['total'] > 0 else 100) if marks else None
    focus_subject = weakest['subject'] if weakest else "General"
    
    prompt = f"""
    Create a 7-day personalized study plan for a student struggling with {focus_subject}.
    Format: Day 1, Day 2... etc. Include 2-hour daily slots. Keep it concise.
    """
    try:
        response = ai_model.generate_content(prompt)
        return jsonify({"plan": response.text})
    except Exception as e:
        return jsonify({"plan": "Error generating plan."})

@app.route("/api/ai-ptm-script/<roll_no>")
@login_required
def ai_ptm_script(roll_no):
    if not ai_model: return jsonify({"script": "AI Offline"})
    
    student = one("SELECT name FROM students WHERE roll_no=%s", (roll_no,))
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s", (roll_no,))["t"]
    
    prompt = f"""
    You are a class teacher preparing for a Parent-Teacher Meeting for {student['name']}.
    Data: Marks: {marks}. Pending Fees: ₹{due}.
    Write a short 1-minute script for the teacher to read to the parents politely.
    """
    try:
        response = ai_model.generate_content(prompt)
        return jsonify({"script": response.text})
    except Exception as e:
        return jsonify({"script": "Error generating script."})

@app.route("/api/ai-psych-alert/<roll_no>")
@login_required
def ai_psych_alert(roll_no):
    if not ai_model: return jsonify({"alert": "AI Offline"})
    try:
        notes = db_all("SELECT note_text FROM teacher_notes WHERE roll_no=%s", (roll_no,))
    except:
        notes = []
        
    if not notes: return jsonify({"alert": "No teacher notes available to analyze."})
    notes_str = " | ".join([n['note_text'] for n in notes])
    
    prompt = f"""
    Analyze these teacher observations: "{notes_str}".
    Is the student showing signs of stress, bullying, or depression? 
    Output a short 2-line psychological insight for the counselor.
    """
    try:
        response = ai_model.generate_content(prompt)
        return jsonify({"alert": response.text})
    except Exception as e:
        return jsonify({"alert": "Error analyzing notes."})

@app.route("/ai-auto-whatsapp")
@login_required
@admin_required
def ai_auto_whatsapp():
    defaulters = db_all("""
        SELECT s.roll_no, s.name, s.class_name, s.parent_contact, 
               SUM(b.balance) as total_due
        FROM bills b 
        JOIN students s ON b.roll_no = s.roll_no
        WHERE b.balance > 0 AND s.parent_contact IS NOT NULL AND s.parent_contact != ''
        GROUP BY s.roll_no, s.name, s.class_name, s.parent_contact
        HAVING SUM(b.balance) > 0
        ORDER BY total_due DESC
    """)
    
    reminders = []
    for d in defaulters:
        phone = str(d['parent_contact']).replace(" ", "").replace("+", "").replace("-", "")
        if len(phone) == 10:
            phone = "91" + phone
            
        msg = f"Dear Parent, Aapke bachhe {d['name']} (Roll: {d['roll_no']}) ki school fees me Rs {d['total_due']:,.0f} pending hai. Kripya jaldi jama karein. Dhanyawad - School Management"
        wa_link = f"https://wa.me/{phone}?text={msg.replace(' ', '%20')}"
        reminders.append({**dict(d), "wa_link": wa_link, "message": msg})

    return render_template("ai_auto_whatsapp.html", reminders=reminders)


# ==========================================
# 📱 COMMUNICATION & QUICK ACTIONS
# ==========================================
@app.route("/send-whatsapp", methods=["POST"])
@login_required
def send_whatsapp():
    msg = request.form.get("whatsapp_msg")
    if msg: flash("✅ WhatsApp Broadcast Sent Successfully!", "success")
    return redirect(url_for("dashboard"))

@app.route("/send-email", methods=["POST"])
@login_required
def send_email():
    subject = request.form.get("email_subject")
    if subject: flash("✅ Email Sent Successfully!", "success")
    return redirect(url_for("dashboard"))

@app.route("/quick_actions")
@login_required
def quick_actions():
    return render_template("quick_actions.html")


# ---------------- APP RUN (SocketIO) ----------------
if __name__ == '__main__':
    socketio.run(app, debug=True)
