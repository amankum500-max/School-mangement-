# ==========================================
# 🚨 CRITICAL: Eventlet Monkey Patch (Must be first)
# ==========================================
import eventlet
eventlet.sleep(0) 
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

# --- Naye Imports Bulk Import & God-Level TC ke liye ---
import pandas as pd
import threading
import uuid
import re
import signal
import time  # <--- YEH MISSING THA, ADD KAR DIYA
from geopy.distance import geodesic
from pinatapy import PinataPy

# Local Database Functions
from database import init_db, run, all as db_all, one, current_month, today

# ==========================================
# 🛠️ APP SETUP (Yahan Order Sabse Zaroori Hai)
# ==========================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school-secret-key-2026")

# App define hone ke BAAD SocketIO banega
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Gunicorn ke graceful shutdown ke liye signal handler
def handle_sigterm(signum, frame):
    print("SIGTERM received, shutting down gracefully...")
    socketio.stop()

signal.signal(signal.SIGTERM, handle_sigterm)

# --- BULK IMPORT SETUP ---
TEMP_UPLOAD_FOLDER = 'static/temp_imports'
os.makedirs(TEMP_UPLOAD_FOLDER, exist_ok=True)
STAGING_CACHE = {}

# --- GOD-LEVEL TC CONFIGURATIONS ---
SCHOOL_LAT = 28.6139  # Apne school ki exact Latitude daalein
SCHOOL_LON = 77.2090  # Apne school ki exact Longitude daalein
ALLOWED_RADIUS_METERS = 500 # 500 meters ke andar hi TC banega

PINATA_API_KEY = os.environ.get("PINATA_API_KEY", "your_key")
PINATA_SECRET = os.environ.get("PINATA_SECRET", "your_secret")
pinata = PinataPy(PINATA_API_KEY, PINATA_SECRET)

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
# 🚀 SMART BULK IMPORT PIPELINE
# ==========================================
@app.route("/students/download-template")
@login_required
def download_import_template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll No', 'Student Name', 'Class', 'Father Name', 'Mobile Number'])
    writer.writerow(['101', 'Rahul Sharma', '10-A', 'Ramesh Sharma', '9876543210'])
    writer.writerow(['102', 'Priya Singh', '10-B', 'Suresh Singh', '8765432109'])
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=Student_Import_Template.csv"}
    )

@app.route("/api/friendly-import/analyze", methods=["POST"])
@login_required
def friendly_import_analyze():
    file = request.files.get("file")
    if not file: return jsonify({"status": "error", "msg": "Please select a file first."})

    filename = secure_filename(file.filename)
    file_path = os.path.join(TEMP_UPLOAD_FOLDER, f"{uuid.uuid4()}_{filename}")
    file.save(file_path)

    try:
        if filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path, engine='openpyxl')
        else:
            df = pd.read_csv(file_path)
            
        df = df.fillna("")
        
        ai_mapping = {}
        for col in df.columns:
            c = str(col).lower().replace(" ", "")
            if 'roll' in c or 'scholar' in c: ai_mapping[col] = 'roll_no'
            elif 'name' in c and 'father' not in c: ai_mapping[col] = 'name'
            elif 'class' in c or 'grade' in c: ai_mapping[col] = 'class_name'
            elif 'contact' in c or 'mobile' in c or 'phone' in c: ai_mapping[col] = 'parent_contact'
            elif 'father' in c or 'guardian' in c: ai_mapping[col] = 'father'

        processed_data = []
        for index, row in df.iterrows():
            parsed_row = {"_original_row": index + 2}
            
            for csv_col, db_col in ai_mapping.items():
                val = str(row.get(csv_col, '')).strip()
                if db_col in ['name', 'father', 'class_name'] and val:
                    val = val.title()
                if db_col == 'parent_contact' and val:
                    val = re.sub(r'\D', '', val)[-10:]
                parsed_row[db_col] = val

            errors = []
            if not parsed_row.get('roll_no'): errors.append("Roll No is missing")
            if not parsed_row.get('name'): errors.append("Name is missing")
            
            if parsed_row.get('roll_no') and one("SELECT roll_no FROM students WHERE roll_no=%s", (parsed_row['roll_no'],)):
                errors.append("Roll No already exists")
            
            parsed_row['_status'] = 'error' if errors else 'valid'
            parsed_row['_friendly_error'] = " and ".join(errors) if errors else "Ready to import"
            processed_data.append(parsed_row)

        staging_id = str(uuid.uuid4())
        STAGING_CACHE[staging_id] = {"data": processed_data, "file_path": file_path}

        return jsonify({
            "status": "success",
            "staging_id": staging_id,
            "preview": processed_data[:150],
            "total_rows": len(processed_data),
            "valid_count": sum(1 for r in processed_data if r['_status'] == 'valid'),
            "error_count": sum(1 for r in processed_data if r['_status'] == 'error')
        })
    except Exception as e:
        return jsonify({"status": "error", "msg": f"File error: {str(e)}"})

def process_friendly_commit(staging_id, batch_id, task_id):
    cache_data = STAGING_CACHE.get(staging_id)
    if not cache_data: return
    data = cache_data['data']
    added, skipped = 0, 0
    
    for i, row in enumerate(data):
        if row['_status'] == 'error':
            skipped += 1
            continue
        try:
            run("""INSERT INTO students (roll_no, name, class_name, father, parent_contact, import_batch_id) 
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (row.get('roll_no'), row.get('name'), row.get('class_name', ''), 
                 row.get('father', ''), row.get('parent_contact', ''), batch_id))
            added += 1
        except Exception:
            skipped += 1

        if i % 5 == 0:
            percent = int(((i + 1) / len(data)) * 100)
            socketio.emit('friendly_progress', {'task_id': task_id, 'percent': percent, 'added': added})

    try: os.remove(cache_data['file_path']) 
    except: pass
    
    del STAGING_CACHE[staging_id]
    socketio.emit('friendly_complete', {'task_id': task_id, 'added': added, 'skipped': skipped, 'batch_id': batch_id})

@app.route("/api/friendly-import/commit", methods=["POST"])
@login_required
def friendly_import_commit():
    staging_id = request.json.get("staging_id")
    if staging_id not in STAGING_CACHE:
        return jsonify({"status": "error", "msg": "Session expired. Please upload again."})

    batch_id = f"BATCH-{datetime.now().strftime('%Y%m%d%H%M')}"
    task_id = f"task_{int(time.time())}"
    threading.Thread(target=process_friendly_commit, args=(staging_id, batch_id, task_id)).start()
    return jsonify({"status": "success", "task_id": task_id})

@app.route("/api/friendly-import/rollback/<batch_id>", methods=["DELETE"])
@login_required
def friendly_import_rollback(batch_id):
    try:
        run("DELETE FROM students WHERE import_batch_id=%s", (batch_id,))
        return jsonify({"status": "success", "msg": "Import successfully undone."})
    except Exception as e:
        return jsonify({"status": "error", "msg": "Could not undo the import."})

@app.route("/api/friendly-import/download-errors", methods=["POST"])
@login_required
def friendly_import_download_errors():
    errors = request.json.get("errors", [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Excel Row", "Roll No", "Name", "Reason to Fix"])
    for e in errors:
        writer.writerow([e.get('_original_row'), e.get('roll_no'), e.get('name'), e.get('_friendly_error')])
    
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=Errors.csv"})


# ==========================================
# 🪪 ID CARD & PROFILE GENERATION (Clean Version)
# ==========================================
@app.route("/student/id_card/<roll_no>")
@login_required
def student_id_card(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student not found for ID Card!", "error")
        return redirect(url_for("students"))
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

        total_paid = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE roll_no=%s", (roll_no,))["t"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
        recent_payments = db_all("SELECT * FROM payments WHERE roll_no=%s ORDER BY id DESC LIMIT 5", (roll_no,))
        
        total_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll_no,))["c"]
        present_days = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll_no,))["c"]
        attendance_pct = round((present_days / total_days * 100), 2) if total_days > 0 else 0
        heatmap_data = {str(r['att_date']): r['status'] for r in db_all("SELECT att_date, status FROM attendance WHERE roll_no=%s", (roll_no,))}

        marks_data = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
        try: teacher_notes = db_all("SELECT * FROM teacher_notes WHERE roll_no=%s ORDER BY id DESC", (roll_no,))
        except: teacher_notes = []

        warnings = []
        if attendance_pct < 75 and total_days > 0: warnings.append(f"Low Attendance ({attendance_pct}%).")
        if float(total_due) > 5000: warnings.append(f"High Pending Dues (₹{total_due}).")

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
    return redirect(url_for("student_profil app.py
