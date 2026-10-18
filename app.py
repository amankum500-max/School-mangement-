from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from functools import wraps
from datetime import datetime
import os, csv
from io import StringIO
from database import init_db, run, all as db_all, one, current_month, today

# ---------------- AI SETUP ----------------
try:
    import google.generativeai as genai
    GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
    if GEMINI_KEY:
        genai.configure(api_key=GEMINI_KEY)
        ai_model = genai.GenerativeModel('gemini-1.5-flash')
    else:
        ai_model = None
except ImportError:
    ai_model = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school-secret-key-2026")

# ---------------- CONTEXT PROCESSOR (School Name for Sidebar) ----------------
@app.context_processor
def inject_global_settings():
    try:
        s = one("SELECT * FROM school_settings WHERE id=1")
        if not s: s = {"school_name": "School ERP"}
    except:
        s = {"school_name": "School ERP"}
    return dict(school_settings=s)

# ---------------- AUTH DECORATOR ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

# ---------------- LOGIN / LOGOUT ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        if u == "admin" and p == "admin123":
            session["user"] = u
            session["role"] = "admin"
            session["name"] = "System Admin"
            return redirect(url_for("dashboard"))
        flash("Invalid credentials!", "error")
    return render_template("auth/login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    try:
        students_count = one("SELECT COUNT(*) c FROM students")["c"]
        total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
        today_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_date = %s", (today(),))["t"]
        
        paid = one("SELECT COUNT(*) c FROM bills WHERE status='Paid'")["c"]
        partial = one("SELECT COUNT(*) c FROM bills WHERE status='Partial'")["c"]
        unpaid = one("SELECT COUNT(*) c FROM bills WHERE status='Unpaid' OR status IS NULL")["c"]
        fee_status = [paid, partial, unpaid]

        trend = db_all("SELECT substr(pay_date, 1, 7) as month, SUM(amount) as total FROM payments GROUP BY substr(pay_date, 1, 7) ORDER BY month DESC LIMIT 6")
        trend.reverse()
        trend_labels = [t['month'] for t in trend]
        trend_data = [float(t['total']) for t in trend]
        
        recent_notices = db_all("SELECT * FROM notices WHERE is_active = TRUE ORDER BY id DESC LIMIT 3")
    except Exception as e:
        print("Dashboard Error:", e)
        students_count, total_due, today_collection = 0, 0, 0
        fee_status, trend_labels, trend_data, recent_notices = [0,0,0], [], [], []

    return render_template("dashboard/dashboard.html",
        students=students_count, total_due=total_due, today_collection=today_collection,
        fee_status=fee_status, trend_labels=trend_labels, trend_data=trend_data, recent_notices=recent_notices
    )

# ---------------- STUDENTS ----------------
@app.route("/students")
@login_required
def students():
    try:
        rows = db_all("SELECT * FROM students ORDER BY roll_no")
    except:
        rows = []
    return render_template("students/students.html", students=rows)

@app.route("/student/add", methods=["POST"])
@login_required
def add_student():
    d = request.form
    try:
        run("INSERT INTO students (roll_no, name, class_name, father, parent_contact) VALUES (%s, %s, %s, %s, %s)",
            (d["roll_no"], d["name"], d.get("class_name", ""), d.get("father", ""), d.get("parent_contact", "")))
        flash("✅ Student added successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("students"))

@app.route("/student/profile/<roll_no>")
@login_required
def student_profile(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("students"))
        
    bills = db_all("SELECT * FROM bills WHERE roll_no=%s ORDER BY month DESC", (roll_no,))
    total_due = sum(float(b['balance']) for b in bills)
    marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
    total_obtained = sum(float(m['marks'] or 0) for m in marks)
    total_max = sum(float(m['total'] or 0) for m in marks)
    percentage = round((total_obtained / total_max * 100), 2) if total_max > 0 else 0
    
    total_att = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll_no,))["c"]
    present_att = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll_no,))["c"]
    att_pct = round((present_att / total_att * 100), 1) if total_att > 0 else 0
    
    return render_template("students/student_profile.html", student=student, bills=bills, total_due=total_due, marks=marks, percentage=percentage, att_pct=att_pct)

@app.route("/student/id-card/<roll_no>")
@login_required
def student_id_card(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    return render_template("students/id_card.html", student=student)

# ---------------- FEES & BILLS ----------------
@app.route("/fees")
@login_required
def fees():
    try:
        rows = db_all("""
            SELECT s.roll_no, s.name, s.class_name, 
                   COALESCE(f.tuition_fee,0) as tuition_fee, 
                   COALESCE((SELECT SUM(balance) FROM bills WHERE roll_no=s.roll_no AND balance>0), 0) as back_dues
            FROM students s LEFT JOIN student_fees f ON s.roll_no = f.roll_no ORDER BY s.roll_no
        """)
    except:
        rows = []
    return render_template("fees/fees.html", fees=rows)

@app.route("/bills")
@login_required
def bills():
    month = request.args.get("month", current_month())
    try:
        rows = db_all("SELECT * FROM bills WHERE month=%s ORDER BY roll_no", (month,))
    except:
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
        if one("SELECT id FROM bills WHERE roll_no=%s AND month=%s", (roll, month)): skipped += 1; continue
        fs = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fs: skipped += 1; continue
        
        t, tr, ho = fs["tuition_fee"] or 0, fs["transport_fee"] or 0, fs["hostel_fee"] or 0
        prev_due = one("SELECT COALESCE(SUM(balance),0) d FROM bills WHERE roll_no=%s AND balance>0", (roll,))["d"]
        total = t + tr + ho + prev_due
        
        run("""INSERT INTO bills (bill_no,roll_no,month,bill_date,tuition,transport,hostel,total,paid,balance,status)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,0,%s,'Unpaid')""",
            (f"B{month.replace('-','')}{roll}", roll, month, today(), t, tr, ho, total, total))
        created += 1
    flash(f"✅ Bills generated: {created} | Skipped: {skipped}", "success")
    return redirect(url_for("bills", month=month))

@app.route("/collect/<roll_no>", methods=["GET", "POST"])
@login_required
def collect(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student: return redirect(url_for("students"))
    
    if request.method == "POST":
        amount = float(request.form.get("amount") or 0)
        if amount > 0:
            try:
                receipt_no = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
                run("INSERT INTO payments (receipt_no, roll_no, amount, mode, pay_date, remark) VALUES (%s, %s, %s, %s, %s, %s)",
                    (receipt_no, roll_no, amount, request.form.get("mode"), today(), request.form.get("remark")))
                
                bills = db_all("SELECT id, balance, paid, total FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
                rem = amount
                for b in bills:
                    if rem <= 0: break
                    deduct = min(rem, float(b['balance']))
                    new_paid = float(b['paid']) + deduct
                    new_bal = float(b['total']) - new_paid
                    status = "Paid" if new_bal <= 0 else "Partial"
                    run("UPDATE bills SET paid=%s, balance=%s, status=%s WHERE id=%s", (new_paid, new_bal, status, b['id']))
                    rem -= deduct
                flash(f"✅ ₹{amount} collected successfully!", "success")
                return redirect(url_for("receipt", roll_no=roll_no, receipt_no=receipt_no))
            except Exception as e: flash(f"❌ Error: {e}", "error")
    
    bills = db_all("SELECT * FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
    total_due = sum(float(b['balance']) for b in bills)
    return render_template("fees/collect.html", student=student, bills=bills, total_due=total_due)

@app.route("/receipt/<roll_no>/<receipt_no>")
@login_required
def receipt(roll_no, receipt_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    payment = one("SELECT * FROM payments WHERE receipt_no=%s", (receipt_no,))
    return render_template("fees/receipt.html", student=student, payment=payment, now=datetime.now())

@app.route("/defaulters")
@login_required
def defaulters():
    try:
        rows = db_all("""SELECT s.roll_no, s.name, s.class_name, b.month, b.balance, s.parent_contact
                         FROM bills b JOIN students s ON b.roll_no = s.roll_no WHERE b.balance > 0 ORDER BY b.balance DESC""")
        total = sum(float(r["balance"]) for r in rows)
    except:
        rows, total = [], 0
    return render_template("fees/defaulters.html", defaulters=rows, total=total)

# ---------------- EXAMS & MARKS ----------------
@app.route("/result", methods=["GET", "POST"])
@login_required
def result():
    if request.method == "POST":
        d = request.form
        existing = one("SELECT id FROM marks WHERE roll_no=%s AND subject=%s AND exam=%s", (d["roll_no"], d["subject"], d["exam"]))
        if existing:
            run("UPDATE marks SET marks=%s, total=%s WHERE id=%s", (d["marks"], d["total"], existing["id"]))
        else:
            run("INSERT INTO marks (roll_no, subject, exam, marks, total) VALUES (%s,%s,%s,%s,%s)", (d["roll_no"], d["subject"], d["exam"], d["marks"], d["total"]))
        flash("✅ Marks saved!", "success")
        return redirect(url_for("result", roll_no=d["roll_no"]))
        
    roll = request.args.get("roll_no", "")
    marks_data = db_all("SELECT * FROM marks WHERE roll_no=%s", (roll,)) if roll else []
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll,)) if roll else None
    students_list = db_all("SELECT roll_no, name FROM students ORDER BY roll_no")
    return render_template("exams/result.html", students=students_list, marks=marks_data, student=student, roll=roll)

@app.route("/report-card/<roll_no>")
@login_required
def report_card(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    marks = db_all("SELECT * FROM marks WHERE roll_no=%s", (roll_no,))
    total_obtained = sum(float(m['marks'] or 0) for m in marks)
    total_max = sum(float(m['total'] or 0) for m in marks)
    pct = round((total_obtained/total_max*100), 2) if total_max > 0 else 0
    grade = 'A+' if pct>=90 else 'A' if pct>=80 else 'B' if pct>=70 else 'C' if pct>=60 else 'F'
    return render_template("exams/report_card.html", student=student, marks=marks, total_obtained=total_obtained, total_max=total_max, percentage=pct, overall_grade=grade, today_date=today())

# ---------------- ATTENDANCE ----------------
@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    if request.method == "POST":
        att_date, class_name = request.form.get("att_date"), request.form.get("class_name")
        run("DELETE FROM attendance WHERE att_date=%s AND roll_no IN (SELECT roll_no FROM students WHERE class_name=%s)", (att_date, class_name))
        for key, val in request.form.items():
            if key.startswith("status_"):
                run("INSERT INTO attendance (roll_no, att_date, status) VALUES (%s,%s,%s)", (key.replace("status_",""), att_date, val))
        flash("✅ Attendance saved!", "success")
        return redirect(url_for("attendance", date=att_date, class_name=class_name))

    att_date, class_name = request.args.get("date", today()), request.args.get("class_name", "")
    students_list = db_all("SELECT * FROM students WHERE class_name=%s", (class_name,)) if class_name else []
    existing = {a['roll_no']: a['status'] for a in db_all("SELECT roll_no, status FROM attendance WHERE att_date=%s", (att_date,))}
    classes = db_all("SELECT DISTINCT class_name FROM students WHERE class_name IS NOT NULL")
    return render_template("attendance/attendance.html", students=students_list, classes=classes, att_date=att_date, class_name=class_name, existing_att=existing)

# ---------------- NOTICES ----------------
@app.route("/notices", methods=["GET", "POST"])
@login_required
def notices():
    if request.method == "POST":
        d = request.form
        run("INSERT INTO notices (title, content, priority, posted_date) VALUES (%s,%s,%s,%s)", (d["title"], d["content"], d.get("priority","Normal"), today()))
        flash("✅ Notice posted!", "success")
        return redirect(url_for("notices"))
    return render_template("communication/notices.html", notices=db_all("SELECT * FROM notices WHERE is_active=TRUE ORDER BY id DESC"))

@app.route("/notice/delete/<int:nid>")
@login_required
def delete_notice(nid):
    run("UPDATE notices SET is_active=FALSE WHERE id=%s", (nid,))
    return redirect(url_for("notices"))

# ---------------- STAFF ----------------
@app.route("/staff", methods=["GET", "POST"])
@login_required
def staff():
    if request.method == "POST":
        d = request.form
        run("INSERT INTO staff (emp_id, name, designation, subject, phone, salary) VALUES (%s,%s,%s,%s,%s,%s)", (d["emp_id"], d["name"], d.get("designation"), d.get("subject"), d.get("phone"), d.get("salary") or 0))
        flash("✅ Staff added!", "success")
        return redirect(url_for("staff"))
    rows = db_all("SELECT * FROM staff WHERE is_active=TRUE ORDER BY name")
    return render_template("management/staff.html", staff=rows, total_salary=sum(float(s['salary'] or 0) for s in rows))

@app.route("/staff/delete/<int:sid>")
@login_required
def delete_staff(sid):
    run("UPDATE staff SET is_active=FALSE WHERE id=%s", (sid,))
    return redirect(url_for("staff"))

# ---------------- OTHER MODULES (Hostel, Transport, Library, Events, Certificates) ----------------
@app.route("/transport", methods=["GET", "POST"])
@login_required
def transport():
    if request.method == "POST":
        d = request.form
        run("INSERT INTO transport_routes (route_number, route_name, driver_name, driver_phone, vehicle_no, capacity) VALUES (%s,%s,%s,%s,%s,%s)", (d["route_number"], d["route_name"], d.get("driver_name"), d.get("driver_phone"), d.get("vehicle_no"), d.get("capacity") or 40))
        return redirect(url_for("transport"))
    return render_template("facilities/transport.html", routes=db_all("SELECT * FROM transport_routes WHERE is_active=TRUE"))

@app.route("/hostel", methods=["GET", "POST"])
@login_required
def hostel():
    if request.method == "POST":
        d = request.form
        run("INSERT INTO hostel_rooms (room_no, block, capacity, monthly_fee, warden_name) VALUES (%s,%s,%s,%s,%s)", (d["room_no"], d.get("block"), d.get("capacity") or 4, d.get("monthly_fee") or 0, d.get("warden_name")))
        return redirect(url_for("hostel"))
    rooms = db_all("SELECT * FROM hostel_rooms WHERE is_active=TRUE")
    return render_template("facilities/hostel.html", rooms=rooms, total_capacity=sum(r['capacity'] for r in rooms), total_occupied=sum(r['occupied'] for r in rooms))

@app.route("/library", methods=["GET", "POST"])
@login_required
def library():
    if request.method == "POST":
        d = request.form
        copies = int(d.get("total_copies") or 1)
        run("INSERT INTO library_books (book_id, title, author, category, total_copies, available_copies) VALUES (%s,%s,%s,%s,%s,%s)", (d["book_id"], d["title"], d.get("author"), d.get("category"), copies, copies))
        return redirect(url_for("library"))
    books = db_all("SELECT * FROM library_books WHERE is_active=TRUE")
    return render_template("facilities/library.html", books=books, total_books=sum(b['total_copies'] for b in books), available_books=sum(b['available_copies'] for b in books))

@app.route("/events", methods=["GET", "POST"])
@login_required
def events():
    if request.method == "POST":
        d = request.form
        run("INSERT INTO events (event_name, event_date, event_type, location, description) VALUES (%s,%s,%s,%s,%s)", (d["event_name"], d["event_date"], d.get("event_type"), d.get("location"), d.get("description")))
        return redirect(url_for("events"))
    return render_template("management/events.html", upcoming=db_all("SELECT * FROM events WHERE event_date >= %s", (today(),)), past=db_all("SELECT * FROM events WHERE event_date < %s", (today(),)))

@app.route("/certificates")
@login_required
def certificates():
    return render_template("management/certificates.html", students=db_all("SELECT roll_no, name, class_name FROM students"))

@app.route("/certificate/generate/<roll_no>/<cert_type>")
@login_required
def generate_certificate(roll_no, cert_type):
    return render_template("management/certificate_print.html", student=one("SELECT * FROM students WHERE roll_no=%s", (roll_no,)), cert_type=cert_type, today_date=today())

# ---------------- AI ASSISTANT ----------------
@app.route("/ai-assistant")
@login_required
def ai_assistant():
    return render_template("ai/ai_assistant.html")

@app.route("/api/ai-chat", methods=["POST"])
@login_required
def api_ai_chat():
    if not ai_model: return jsonify({"reply": "⚠️ AI Configure nahi hai."})
    user_msg = request.get_json().get("message", "")
    try:
        context = f"Students: {one('SELECT COUNT(*) c FROM students')['c']}, Dues: {one('SELECT SUM(balance) t FROM bills WHERE balance>0')['t']}"
        res = ai_model.generate_content(f"Context: {context}\nUser: {user_msg}")
        return jsonify({"reply": res.text})
    except Exception as e: return jsonify({"reply": f"Error: {e}"})

# ---------------- PARENT PORTAL ----------------
@app.route("/parent-login", methods=["GET", "POST"])
def parent_login():
    if request.method == "POST":
        p = one("SELECT * FROM parent_users WHERE username=%s AND password=%s", (request.form["username"], request.form["password"]))
        if p:
            session["parent_user"], session["parent_child"] = p["username"], p["child_roll_no"]
            return redirect(url_for("parent_dashboard"))
        flash("Invalid login", "error")
    return render_template("auth/parent_login.html")

@app.route("/parent-dashboard")
def parent_dashboard():
    if "parent_user" not in session: return redirect(url_for("parent_login"))
    roll = session["parent_child"]
    return render_template("parent/parent_dashboard.html", student=one("SELECT * FROM students WHERE roll_no=%s", (roll,)), bills=db_all("SELECT * FROM bills WHERE roll_no=%s", (roll,)), marks=db_all("SELECT * FROM marks WHERE roll_no=%s", (roll,)), att_pct=100, percentage=85, total_due=one("SELECT SUM(balance) t FROM bills WHERE roll_no=%s", (roll,))["t"])

@app.route("/manage-parents", methods=["GET", "POST"])
@login_required
def manage_parents():
    if request.method == "POST":
        d = request.form
        run("INSERT INTO parent_users (username, password, parent_name, child_roll_no) VALUES (%s,%s,%s,%s)", (d["username"], d["password"], d.get("parent_name"), d["child_roll_no"]))
        return redirect(url_for("manage_parents"))
    return render_template("parent/manage_parents.html", parents=db_all("SELECT * FROM parent_users"), students=db_all("SELECT roll_no, name FROM students"))

# ---------------- SETTINGS & BACKUP ----------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        d = request.form
        run("UPDATE school_settings SET school_name=%s, address=%s, phone=%s, email=%s WHERE id=1", (d["school_name"], d["address"], d["phone"], d["email"]))
        flash("✅ Settings updated!", "success")
        return redirect(url_for("settings"))
    return render_template("management/settings.html")

@app.route("/backup")
@login_required
def backup():
    return render_template("management/backup.html")

@app.route("/backup/download/<table_name>")
@login_required
def download_csv(table_name):
    if table_name not in ['students', 'fees', 'bills', 'payments', 'staff', 'marks']: return redirect(url_for("backup"))
    data = db_all(f"SELECT * FROM {table_name}")
    si = StringIO()
    if data:
        cw = csv.writer(si); cw.writerow(data[0].keys())
        for row in data: cw.writerow(row.values())
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={table_name}.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# ---------------- ANALYTICS ----------------
@app.route("/analytics")
@login_required
def analytics():
    return render_template("management/analytics.html", 
        total_collection=one("SELECT SUM(amount) t FROM payments")["t"] or 0,
        pending_dues=one("SELECT SUM(balance) t FROM bills WHERE balance>0")["t"] or 0,
        monthly_data=[], class_dist=[], top_payers=[]
    )

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
