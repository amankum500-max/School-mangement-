# ==========================================
# 🚨 CRITICAL: Eventlet Monkey Patch (Must be first)
# ==========================================
import eventlet
eventlet.sleep(0)  # <--- YEH NAYI LINE ADD KAREIN
eventlet.monkey_patch()

import os
import io
import csv
import json
import hashlib
import razorpay
import requests
import urllib3
urllib3.util.connection.HAS_IPV6 = False
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
from fpdf import FPDF
# --- Naye Imports Bulk Import ke liye ---
import pandas as pd
import threading
import uuid
import re
# Local Database Functions (Ensure database.py exists)
from database import init_db, run, all as db_all, one, current_month, today
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
import signal

# --- BULK IMPORT SETUP ---
TEMP_UPLOAD_FOLDER = 'static/temp_imports'
os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)
STAGING_CACHE = {}
# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school-secret-key-2026")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
import signal

# Gunicorn ke graceful shutdown ke liye signal handler
def handle_sigterm(signum, frame):
    print("SIGTERM received, shutting down gracefully...")
    socketio.stop()

signal.signal(signal.SIGTERM, handle_sigterm)
# ==========================================
# 🗄️ Supabase Setup (For Photo Uploads)
# ==========================================
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("⚠️ Supabase URL or Key is missing in Environment Variables!")
    
# Gemini AI Setup
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    ai_model = None

# Razorpay Payment Gateway Setup
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_dummy")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "dummy_secret")
rzp_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# File Uploads Setup
UPLOAD_FOLDER = 'static/uploads/students'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------- AUTH DECORATORS ----------------
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
        return jsonify({"status": "error", "message": str(e)})

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

@app.route("/api/weather")
@login_required
def api_weather():
    return jsonify({"temp": "32°C", "condition": "Clear Sky", "icon": "☀️"})

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
    # ==========================================
# 🪪 ID CARD GENERATION ROUTE
# ==========================================
@app.route("/student/id_card/<roll_no>")
@login_required
def student_id_card(roll_no):
    # Aapke database se student ka data fetch kar raha hai
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    
    if not student:
        flash("Student not found for ID Card!", "error")
        return redirect(url_for("students"))
        
    # HTML template render karega jisme student ka data jayega
    return render_template("students/id_card.html", student=student)

@app.route("/student/profile/<roll_no>")
@login_required
def student_profile(roll_no):
    try:
        student_row = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
        if not student_row: 
            flash("Student not found!", "error")
            return redirect(url_for("students"))
        
        student = dict(student_row)
        
        # Defaults (Agar DB me column nahi hai toh crash na ho)
        defaults = {
            'photo_url': f"https://api.dicebear.com/7.x/initials/svg?seed={student.get('name','Student')}&backgroundColor=00f3ff", 
            'house': 'Red', 'blood_group': 'O+', 'allergies': 'None', 
            'emergency_contact': 'N/A', 'merit_points': 0, 'transport_route': 'N/A', 
            'hostel_room': 'N/A', 'library_books': 'None', 'achievements': 'No achievements recorded.',
            'communication_log': 'No parent communication logged.', 'portfolio_links': '',
            'gate_pass_active': False
        }
        for key, val in defaults.items():
            if key not in student or student[key] is None:
                student[key] = val

        # Fees Data
        total_paid = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE roll_no=%s", (roll_no,))["t"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
        recent_payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY id DESC LIMIT 5", (roll_no,))
        
        # Attendance Data
        total_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll_no,))["c"]
        present_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll_no,))["c"]
        attendance_pct = round((present_days / total_days * 100), 2) if total_days > 0 else 0
        heatmap_data = {str(r['att_date']): r['status'] for r in db_all("SELECT att_date, status FROM attendance WHERE roll_no=%s", (roll_no,))}

        # Academic & Notes Data
        marks_data = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
        try: teacher_notes = db_all("SELECT * FROM teacher_notes WHERE roll_no=%s ORDER BY id DESC", (roll_no,))
        except: teacher_notes = []

        # AI Warnings
        warnings = []
        if attendance_pct < 75 and total_days > 0: warnings.append(f"Low Attendance ({attendance_pct}%).")
        if float(total_due) > 5000: warnings.append(f"High Pending Dues (₹{total_due}).")

        # Portfolio List
        portfolio_list = [link.strip() for link in student['portfolio_links'].split(',')] if student['portfolio_links'] else []

        return render_template("students/student_profile.html", 
            student=student, total_paid=total_paid, total_due=total_due, 
            marks_data=marks_data, recent_payments=recent_payments,
            total_days=total_days, present_days=present_days, attendance_pct=attendance_pct, 
            heatmap_data=heatmap_data, warnings=warnings, teacher_notes=teacher_notes,
            portfolio_list=portfolio_list, growth_labels=["UT-1", "Half Yearly", "UT-2", "Pre-Board"], growth_data=[65, 72, 78, 85] 
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"Error loading profile: {str(e)}", "error")
        return redirect(url_for("students"))

@app.route("/student/add_note/<roll_no>", methods=["POST"])
@login_required
def add_teacher_note(roll_no):
    note_text = request.form.get("note_text")
    if note_text:
        run("INSERT INTO teacher_notes (roll_no, note_text, teacher_name) VALUES (%s, %s, %s)", (roll_no, note_text, session.get("name", "Teacher")))
        flash("✅ Diary note added!", "success")
    return redirect(url_for("student_profile", roll_no=roll_no))

# -------- PDF & Gate Pass Generation --------
@app.route("/student/dossier/pdf/<roll_no>")
@login_required
def student_dossier_pdf(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    marks = db_all("SELECT * FROM marks WHERE roll_no=%s", (roll_no,))
    
    html = f"""
    <html><body>
    <h2 style="text-align:center; color: #2c3e50;">STUDENT DOSSIER</h2>
    <hr>
    <h3>Personal Info</h3>
    <p><b>Name:</b> {student['name']}<br><b>Roll No:</b> {student['roll_no']}<br><b>Class:</b> {student['class_name']}<br><b>Father:</b> {student['father']}</p>
    <h3>Academic Records</h3>
    <table border="1" style="width:100%; text-align:left; border-collapse: collapse;">
        <tr style="background:#f2f2f2;"><th>Subject</th><th>Marks</th><th>Total</th></tr>
        {''.join([f"<tr><td>{m['subject']}</td><td>{m['marks']}</td><td>{m['total']}</td></tr>" for m in marks])}
    </table>
    </body></html>
    """
    pdf = io.BytesIO()
    pisa.CreatePDF(html, dest=pdf)
    pdf.seek(0)
    return send_file(pdf, mimetype='application/pdf', as_attachment=True, download_name=f"{roll_no}_Dossier.pdf")

@app.route("/api/generate-gate-pass/<roll_no>")
@login_required
def generate_gate_pass(roll_no):
    run("UPDATE students SET gate_pass_active=TRUE WHERE roll_no=%s", (roll_no,))
    data = f"GATE_PASS|{roll_no}|{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    qr = qrcode.QRCode(version=1, box_size=10, border=2); qr.add_data(data); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = io.BytesIO(); img.save(buffered, format="PNG")
    return jsonify({"qr_code": base64.b64encode(buffered.getvalue()).decode()})

# -------- ALL 8 AI ROUTES FOR STUDENT --------
@app.route("/api/ai-study-plan/<roll_no>")
@login_required
def api_ai_study_plan(roll_no):
    if not ai_model: return jsonify({"reply": "AI Offline"})
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    prompt = f"Create a 7-day study plan for a student with marks: {marks}. Keep it short in Hinglish."
    try: return jsonify({"reply": ai_model.generate_content(prompt).text})
    except: return jsonify({"reply": "Error"})

@app.route("/api/ai-ptm-script/<roll_no>")
@login_required
def api_ai_ptm_script(roll_no):
    if not ai_model: return jsonify({"reply": "AI Offline"})
    student = one("SELECT name FROM students WHERE roll_no=%s", (roll_no,))
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    prompt = f"Write a 1-minute PTM script for teacher to talk to parents of {student['name']} with marks: {marks}."
    try: return jsonify({"reply": ai_model.generate_content(prompt).text})
    except: return jsonify({"reply": "Error"})

@app.route("/api/ai-grade-predictor/<roll_no>")
@login_required
def api_ai_grade_predictor(roll_no):
    if not ai_model: return jsonify({"reply": "AI Offline"})
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    prompt = f"Predict next exam percentage and give 2 tips based on marks: {marks}."
    try: return jsonify({"reply": ai_model.generate_content(prompt).text})
    except: return jsonify({"reply": "Error"})

@app.route("/api/ai-psych-alert/<roll_no>")
@login_required
def api_ai_psych_alert(roll_no):
    if not ai_model: return jsonify({"reply": "AI Offline"})
    notes = db_all("SELECT note_text FROM teacher_notes WHERE roll_no=%s", (roll_no,))
    notes_str = " | ".join([n['note_text'] for n in notes]) if notes else "No notes."
    prompt = f"Analyze behavior from notes: '{notes_str}'. Give a 2-line psychological insight."
    try: return jsonify({"reply": ai_model.generate_content(prompt).text})
    except: return jsonify({"reply": "Error"})

@app.route("/api/ai-career-counselor/<roll_no>")
@login_required
def api_ai_career_counselor(roll_no):
    if not ai_model: return jsonify({"reply": "AI Offline"})
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    prompt = f"Act as Career Counselor. Suggest stream and top 3 careers based on marks: {marks}. Keep it under 50 words."
    try: return jsonify({"reply": ai_model.generate_content(prompt).text})
    except: return jsonify({"reply": "Error"})

@app.route("/api/ai-dropout-risk/<roll_no>")
@login_required
def api_ai_dropout_risk(roll_no):
    if not ai_model: return jsonify({"risk_score": 50, "reason": "AI Offline", "action": "Check manually"})
    due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s", (roll_no,))["t"]
    absent = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Absent'", (roll_no,))["c"]
    prompt = f"Analyze dropout risk. Pending Fees: {due}, Absences: {absent}. Output ONLY JSON: {{\"risk_score\": 0-100, \"reason\": \"...\", \"action\": \"...\"}}"
    try:
        res = ai_model.generate_content(prompt).text.replace('```json', '').replace('```', '').strip()
        return jsonify(json.loads(res))
    except: return jsonify({"risk_score": 50, "reason": "Error", "action": "Manual check"})

@app.route("/api/ai-sentiment/<roll_no>")
@login_required
def api_ai_sentiment(roll_no):
    if not ai_model: return jsonify({"sentiment": "Neutral", "score": 50, "advice": "AI Offline"})
    notes = db_all("SELECT note_text FROM teacher_notes WHERE roll_no=%s", (roll_no,))
    notes_str = " | ".join([n['note_text'] for n in notes]) if notes else "Good"
    prompt = f"Analyze sentiment: '{notes_str}'. Output ONLY JSON: {{\"sentiment\": \"Positive/Negative/Neutral\", \"score\": 0-100, \"advice\": \"...\"}}"
    try:
        res = ai_model.generate_content(prompt).text.replace('```json', '').replace('```', '').strip()
        return jsonify(json.loads(res))
    except: return jsonify({"sentiment": "Neutral", "score": 50, "advice": "Error"})

@app.route("/api/ai-subject-forecast/<roll_no>")
@login_required
def api_ai_subject_forecast(roll_no):
    if not ai_model: return jsonify({"reply": "AI Offline"})
    marks = db_all("SELECT subject, marks, total FROM marks WHERE roll_no=%s", (roll_no,))
    prompt = f"Forecast which subject is at highest risk of dropping next term based on marks: {marks}."
    try: return jsonify({"reply": ai_model.generate_content(prompt).text})
    except: return jsonify({"reply": "Error"})

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
    if 'photo' not in request.files:
        flash("No file part", "error")
        return redirect(url_for("student_profile", roll_no=roll_no))
        
    file = request.files['photo']
    
    if file.filename == '':
        flash("No selected file", "error")
        return redirect(url_for("student_profile", roll_no=roll_no))

    if not SUPABASE_URL or not SUPABASE_KEY:
        flash("❌ Supabase is not configured properly.", "error")
        return redirect(url_for("student_profile", roll_no=roll_no))

    if file:
        filename = secure_filename(f"student_{roll_no}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        bucket_name = 'student_photos'
        
        try:
            file_data = file.read()
            upload_url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{filename}"
            
            headers = {
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": file.content_type or "image/jpeg"
            }
            
            response = requests.post(upload_url, headers=headers, data=file_data, timeout=30)
            
            if response.status_code == 200:
                public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{filename}"
                run("UPDATE students SET photo_url=%s WHERE roll_no=%s", (public_url, roll_no))
                flash("✅ Photo uploaded successfully!", "success")
            else:
                flash(f"❌ Error uploading photo: Server returned {response.status_code}", "error")
                
        except requests.exceptions.Timeout:
            flash("❌ Error: Network timeout. Please try uploading again.", "error")
        except requests.exceptions.ConnectionError:
            flash("❌ Error: Could not connect to Supabase.", "error")
        except Exception as e:
            flash(f"❌ Error uploading photo: {str(e)}", "error")
            
    # Function ke end mein hamesha return hona chahiye
    return redirect(url_for("student_profile", roll_no=roll_no))
# ==========================================
# 💵 ULTIMATE FEE MANAGEMENT ENGINE
# ==========================================
@app.route("/fees")
@login_required
def fees():
    rows = db_all("""
    SELECT s.roll_no, s.name, s.class_name, s.section, s.parent_contact, s.father,
           COALESCE(f.tuition_fee, 0) AS tuition_fee, 
           COALESCE(f.transport_fee, 0) AS transport_fee, 
           COALESCE(f.hostel_fee, 0) AS hostel_fee, 
           COALESCE(f.misc_fee, 0) AS misc_fee,
           COALESCE(f.discount, 0) AS discount, 
           COALESCE(f.late_fee, 0) AS late_fee, 
           COALESCE(f.back_dues, 0) AS back_dues, 
           f.due_date, 
           COALESCE(f.wallet_balance, 0) AS wallet_balance
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
# 💰 PAYMENTS & TRANSACTIONS (Bills & Collect)
# ==========================================
@app.route("/bills")
@login_required
def bills():
    month = request.args.get("month", current_month())
    try:
        rows = db_all("SELECT * FROM bills WHERE month=%s ORDER BY roll_no", (month,))
    except Exception:
        rows = []
    return render_template("fees/bills.html", bills=rows, month=month)

@app.route("/bills/generate", methods=["POST"])
@login_required
def generate_bills():
    month = request.form["month"]
    students_list = db_all("SELECT roll_no, name FROM students")
    created = skipped = 0
    
    for s in students_list:
        roll = s["roll_no"]
        ex = one("SELECT id FROM bills WHERE roll_no=%s AND month=%s", (roll, month))
        if ex: skipped += 1; continue
            
        fs = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fs: skipped += 1; continue
            
        t = fs["tuition_fee"] or 0
        tr = fs["transport_fee"] or 0
        ho = fs["hostel_fee"] or 0
        adm_paid = fs["admission_paid"] or 0
        
        prev_added = one("SELECT COALESCE(SUM(admission),0) a FROM bills WHERE roll_no=%s", (roll,))["a"]
        adm = 0 if (adm_paid or prev_added > 0) else (fs["admission_fee"] or 0)
        dr = 0 if prev_added > 0 else (fs["dress_fee"] or 0)
        ex_f = 0 if prev_added > 0 else (fs["exam_fee"] or 0)
        bk = 0 if prev_added > 0 else (fs["book_fee"] or 0)
        nb = 0 if prev_added > 0 else (fs["notebook_fee"] or 0)
        ms = fs["misc_fee"] or 0
        
        prev_due = one("SELECT COALESCE(SUM(balance),0) d FROM bills WHERE roll_no=%s AND balance>0", (roll,))["d"]
        
        total = t + tr + ho + adm + dr + ex_f + bk + nb + ms + prev_due
        bill_no = f"B{month.replace('-','')}{roll}"

        run("""INSERT INTO bills
            (bill_no,roll_no,month,bill_date,tuition,transport,hostel,
             admission,dress,exam,book,notebook,misc,prev_due,total,paid,balance,status)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (bill_no, roll, month, today(), t, tr, ho, adm, dr, ex_f, bk, nb, ms, prev_due, total, 0, total, "Unpaid"))
        created += 1
        
    flash(f"✅ Bills generated: {created} | Skipped: {skipped}", "success")
    return redirect(url_for("bills", month=month))

@app.route("/collect/<roll_no>", methods=["GET", "POST"])
@login_required
def collect(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student not found", "error")
        return redirect(url_for("students"))

    if request.method == "POST":
        amount = float(request.form.get("amount") or 0)
        mode = request.form.get("mode", "Cash")
        remark = request.form.get("remark", "")
        
        if amount <= 0:
            flash("Amount must be greater than 0", "error")
            return redirect(url_for("collect", roll_no=roll_no))

        try:
            receipt_no = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
            run("""INSERT INTO payments (receipt_no, roll_no, amount, mode, pay_date, remark)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (receipt_no, roll_no, amount, mode, today(), remark))
            
            bills_list = db_all("SELECT id, balance, paid, total FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
            rem = amount
            for b in bills_list:
                if rem <= 0: break
                deduct = min(rem, float(b['balance']))
                new_paid = float(b['paid']) + deduct
                new_bal = float(b['total']) - new_paid
                status = "Paid" if new_bal <= 0 else "Partial"
                run("UPDATE bills SET paid=%s, balance=%s, status=%s WHERE id=%s",
                    (new_paid, new_bal, status, b['id']))
                rem -= deduct
                
            socketio.emit('new_payment_alert', {'name': student['name'], 'amount': amount, 'msg': f"₹{amount} paid by {student['name']}"})
            flash(f"✅ ₹{amount} collected successfully!", "success")
            return redirect(url_for("receipt", roll_no=roll_no, receipt_no=receipt_no))
        except Exception as e:
            flash(f"❌ Error: {e}", "error")
            
    bills_list = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
    total_due = sum(float(b['balance']) for b in bills_list)
    return render_template("fees/collect.html", student=student, bills=bills_list, total_due=total_due)

@app.route("/receipt/<roll_no>/<receipt_no>")
@login_required
def receipt(roll_no, receipt_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    payment = one("SELECT * FROM payments WHERE receipt_no=%s", (receipt_no,))
    if not student or not payment:
        flash("Receipt not found", "error")
        return redirect(url_for("students"))
    return render_template("fees/receipt.html", student=student, payment=payment, now=datetime.now())

@app.route("/defaulters")
@login_required
def defaulters():
    try:
        rows = db_all("""SELECT s.roll_no, s.name, s.class_name, s.section,
                         s.parent_contact, b.month, b.balance
                         FROM bills b JOIN students s ON b.roll_no = s.roll_no
                         WHERE b.balance > 0 ORDER BY b.balance DESC""")
        total = sum(float(r["balance"]) for r in rows)
    except Exception:
        rows = []
        total = 0
    return render_template("fees/defaulters.html", defaulters=rows, total=total)

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
    if not ai_model:
        return jsonify({"reply": "⚠️ AI Configure nahi hai. Render me GEMINI_API_KEY daalein."})
    data = request.get_json() or {}
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"reply": "Kuch toh likho bhai!"})
    try:
        students_count = one("SELECT COUNT(*) c FROM students")["c"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
        today_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date = %s", (today(),))["t"]
        prompt = f"School AI Assistant. Data: Students={students_count}, Due={total_due}, Today={today_collection}. User asks: {user_msg}"
        response = ai_model.generate_content(prompt)
        return jsonify({"reply": response.text})
    except Exception as e:
        return jsonify({"reply": f"❌ AI Error: {str(e)}"})

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

# ==========================================
# 📅 ATTENDANCE & EXAMS
# ==========================================
@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    if request.method == "POST":
        att_date = request.form.get("att_date")
        class_name = request.form.get("class_name")
        
        run("""DELETE FROM attendance WHERE att_date=%s AND roll_no IN 
               (SELECT roll_no FROM students WHERE class_name=%s)""", (att_date, class_name))
        
        present_count = 0
        for key, value in request.form.items():
            if key.startswith("status_"):
                roll_no = key.replace("status_", "")
                run("INSERT INTO attendance (roll_no, att_date, status) VALUES (%s, %s, %s)", 
                    (roll_no, att_date, value))
                if value == "Present": present_count += 1
                
        flash(f"✅ Attendance marked for {class_name}! Present: {present_count}", "success")
        return redirect(url_for("attendance", date=att_date, class_name=class_name))

    att_date = request.args.get("date", today())
    class_name = request.args.get("class_name", "")
    students_list = []
    existing_att = {}
    
    if class_name:
        students_list = db_all("SELECT * FROM students WHERE class_name=%s ORDER BY roll_no", (class_name,))
        att_records = db_all("SELECT roll_no, status FROM attendance WHERE att_date=%s", (att_date,))
        existing_att = {a['roll_no']: a['status'] for a in att_records}

    classes = db_all("SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL ORDER BY class_name")
    return render_template("attendance/attendance.html", students=students_list, classes=classes, att_date=att_date, class_name=class_name, existing_att=existing_att)

def calc_grade(pct):
    if pct >= 90: return "A+"
    if pct >= 80: return "A"
    if pct >= 70: return "B"
    if pct >= 60: return "C"
    if pct >= 50: return "D"
    return "F"

@app.route("/result", methods=["GET", "POST"])
@login_required
def result():
    if request.method == "POST":
        d = request.form
        try:
            existing = one("SELECT id FROM marks WHERE roll_no=%s AND subject=%s AND exam=%s", (d["roll_no"], d["subject"], d["exam"]))
            if existing:
                run("UPDATE marks SET marks=%s, total=%s WHERE id=%s", (d["marks"], d["total"], existing["id"]))
            else:
                run("INSERT INTO marks (roll_no, subject, exam, marks, total) VALUES (%s,%s,%s,%s,%s)", (d["roll_no"], d["subject"], d["exam"], d["marks"], d["total"]))
            flash("✅ Marks saved!", "success")
        except Exception as e:
            flash(f"❌ Error: {e}", "error")
        return redirect(url_for("result", roll_no=d["roll_no"]))

    roll = request.args.get("roll_no", "")
    marks_data = []
    student = None
    if roll:
        student = one("SELECT * FROM students WHERE roll_no=%s", (roll,))
        marks_data = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll,))
    students_list = db_all("SELECT roll_no, name FROM students ORDER BY roll_no")
    return render_template("exams/result.html", students=students_list, marks=marks_data, student=student, roll=roll)

@app.route("/report-card/<roll_no>")
@login_required
def report_card(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("students"))
    marks_data = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
    total_obtained = sum(float(m['marks'] or 0) for m in marks_data)
    total_max = sum(float(m['total'] or 0) for m in marks_data)
    percentage = (total_obtained / total_max * 100) if total_max > 0 else 0
    overall_grade = calc_grade(percentage)
    return render_template("exams/report_card.html", student=student, marks=marks_data, total_obtained=total_obtained, total_max=total_max, percentage=round(percentage, 2), overall_grade=overall_grade, today_date=today())

# ==========================================
# 🏫 STAFF & TRANSPORT MANAGEMENT
# ==========================================
@app.route("/staff")
@login_required
def staff():
    try:
        rows = db_all("SELECT * FROM staff WHERE is_active = TRUE ORDER BY name")
        total_salary = sum(float(s['salary'] or 0) for s in rows)
    except:
        rows = []
        total_salary = 0
    return render_template("management/staff.html", staff=rows, total_salary=total_salary)

@app.route("/staff/add", methods=["POST"])
@login_required
def add_staff():
    d = request.form
    try:
        run("""INSERT INTO staff (emp_id, name, designation, subject, phone, email, salary, joining_date) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (d["emp_id"], d["name"], d.get("designation"), d.get("subject"), d.get("phone"), d.get("email"), d.get("salary") or 0, d.get("joining_date")))
        flash("✅ Staff member added successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("staff"))

@app.route("/staff/delete/<int:sid>")
@login_required
def delete_staff(sid):
    try:
        run("UPDATE staff SET is_active = FALSE WHERE id = %s", (sid,))
        flash("🗑️ Staff member removed", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("staff"))

@app.route("/transport")
@login_required
def transport():
    try:
        routes = db_all("SELECT * FROM transport_routes WHERE is_active = TRUE ORDER BY route_number")
    except:
        routes = []
    return render_template("facilities/transport.html", routes=routes)

@app.route("/transport/add", methods=["POST"])
@login_required
def add_transport():
    d = request.form
    try:
        run("""INSERT INTO transport_routes (route_number, route_name, driver_name, driver_phone, vehicle_no, capacity) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (d["route_number"], d["route_name"], d.get("driver_name"), d.get("driver_phone"), d.get("vehicle_no"), d.get("capacity") or 40))
        flash("✅ Transport route added successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("transport"))

@app.route("/transport/delete/<int:rid>")
@login_required
def delete_transport(rid):
    try:
        run("UPDATE transport_routes SET is_active = FALSE WHERE id = %s", (rid,))
        flash("🗑️ Route removed", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("transport"))

# ==========================================
# 📢 COMMUNICATION (Notices)
# ==========================================
@app.route("/notices", methods=["GET", "POST"])
@login_required
def notices():
    if request.method == "POST":
        d = request.form
        run("""INSERT INTO notices (title, content, category, posted_by, posted_date, priority) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (d["title"], d["content"], "General", session.get("name", "Admin"), today(), "Normal"))
        flash("✅ Notice posted successfully!", "success")
        return redirect(url_for("notices"))
        
    notices_list = db_all("SELECT * FROM notices ORDER BY posted_date DESC, id DESC")
    return render_template("communication/notices.html", notices=notices_list)

# ==========================================
# 🚀 APP RUN
# ==========================================
if __name__ == '__main__':
    init_db()
    # socketio.run ki jagah app.run use karein
    app.run(debug=True, port=5000) 
