import os
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import google.generativeai as genai

# Local Database Functions
from database import init_db, run, all as db_all, one, current_month, today

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school-secret-key-2026")

# Setup Gemini AI
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    ai_model = None


# ---------------- AUTH DECORATOR & ROUTES ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
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
        
        # Fee Status Data for Doughnut Chart
        paid = one("SELECT COUNT(*) c FROM bills WHERE status='Paid'")["c"]
        partial = one("SELECT COUNT(*) c FROM bills WHERE status='Partial'")["c"]
        unpaid = one("SELECT COUNT(*) c FROM bills WHERE status='Unpaid' OR status IS NULL")["c"]
        fee_status = [paid, partial, unpaid]

        # Monthly Trend Data for Bar Chart (Last 6 Months)
        trend = db_all("""
            SELECT substr(pay_date, 1, 7) as month, SUM(amount) as total
            FROM payments GROUP BY substr(pay_date, 1, 7)
            ORDER BY month DESC LIMIT 6
        """)
        trend.reverse()  # Chronological order
        trend_labels = [t['month'] for t in trend]
        trend_data = [float(t['total']) for t in trend]

    except Exception as e:
        print("Dashboard Error:", e)
        students_count, total_due, today_collection = 0, 0, 0
        fee_status = [0, 0, 0]
        trend_labels = []
        trend_data = []

    return render_template(
        "dashboard/dashboard.html",
        students=students_count,
        total_due=total_due,
        today_collection=today_collection,
        fee_status=fee_status,
        trend_labels=trend_labels,
        trend_data=trend_data
    )


# ---------------- STUDENTS ----------------
@app.route("/students")
@login_required
def students():
    try:
        rows = db_all("SELECT * FROM students ORDER BY roll_no")
    except Exception:
        rows = []
    return render_template("students/students.html", students=rows)

@app.route("/student/add", methods=["POST"])
@login_required
def add_student():
    d = request.form
    try:
        run("""INSERT INTO students (roll_no, name, class_name, father, parent_contact) 
               VALUES (%s, %s, %s, %s, %s)""",
            (d["roll_no"], d["name"], d.get("class_name", ""), d.get("father", ""), d.get("parent_contact", "")))
        flash("✅ Student added successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("students"))


# ---------------- BILLS & FEES ----------------
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
        if ex:
            skipped += 1
            continue
            
        fs = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fs:
            skipped += 1
            continue
            
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
            
            # 1. Payment insert
            run("""INSERT INTO payments (receipt_no, roll_no, amount, mode, pay_date, remark)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (receipt_no, roll_no, amount, mode, today(), remark))
            
            # 2. Distribute amount to bills
            bills_list = db_all("SELECT id, balance, paid, total FROM bills WHERE roll_no=%s AND balance>0 ORDER BY month ASC", (roll_no,))
            rem = amount
            for b in bills_list:
                if rem <= 0:
                    break
                deduct = min(rem, float(b['balance']))
                new_paid = float(b['paid']) + deduct
                new_bal = float(b['total']) - new_paid
                status = "Paid" if new_bal <= 0 else "Partial"
                
                run("UPDATE bills SET paid=%s, balance=%s, status=%s WHERE id=%s",
                    (new_paid, new_bal, status, b['id']))
                rem -= deduct
                
            flash(f"✅ ₹{amount} collected successfully!", "success")
            return redirect(url_for("receipt", roll_no=roll_no, receipt_no=receipt_no))
        except Exception as e:
            flash(f"❌ Error: {e}", "error")
            
    # GET Request: Fetch pending bills
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


# ---------------- ATTENDANCE ----------------
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
                if value == "Present":
                    present_count += 1
                
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
    
    return render_template("attendance/attendance.html", 
                           students=students_list, classes=classes, 
                           att_date=att_date, class_name=class_name, existing_att=existing_att)


# ---------------- NOTICES ----------------
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


# ---------------- AI ASSISTANT ----------------
@app.route("/ai-assistant")
@login_required
def ai_assistant():
    return render_template("ai/ai_assistant.html")

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
        
        prompt = f"""
        Aap ek School Management System ke AI Assistant hain.
        Aapko Hinglish (Hindi + English) me short aur helpful jawab dena hai.
        
        Live School Data:
        - Total Students: {students_count}
        - Total Pending Fees: Rs {total_due}
        - Today's Collection: Rs {today_collection}
        
        User ka Sawaal: {user_msg}
        """
        
        response = ai_model.generate_content(prompt)
        return jsonify({"reply": response.text})
    except Exception as e:
        return jsonify({"reply": f"❌ AI Error: {str(e)}"})


# ---------------- EXAMS & MARKS ----------------
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
            existing = one("SELECT id FROM marks WHERE roll_no=%s AND subject=%s AND exam=%s", 
                           (d["roll_no"], d["subject"], d["exam"]))
            if existing:
                run("UPDATE marks SET marks=%s, total=%s WHERE id=%s", 
                    (d["marks"], d["total"], existing["id"]))
                flash("✏️ Marks updated successfully!", "success")
            else:
                run("INSERT INTO marks (roll_no, subject, exam, marks, total) VALUES (%s,%s,%s,%s,%s)",
                    (d["roll_no"], d["subject"], d["exam"], d["marks"], d["total"]))
                flash("✅ Marks added successfully!", "success")
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
    
    return render_template("exams/report_card.html", 
                           student=student, marks=marks_data, 
                           total_obtained=total_obtained, total_max=total_max,
                           percentage=round(percentage, 2), overall_grade=overall_grade,
                           today_date=today())
    # ---------------- NOTICES ----------------
@app.route("/notices", methods=["GET", "POST"])
@login_required
def notices():
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        priority = request.form.get("priority", "Normal")
        
        if title and content:
            run("INSERT INTO notices (title, content, priority, posted_date) VALUES (%s,%s,%s,%s)", 
                (title, content, priority, today()))
            flash("✅ Notice posted successfully!", "success")
        return redirect(url_for("notices"))
        
    notice_list = db_all("SELECT * FROM notices WHERE is_active = TRUE ORDER BY id DESC")
    return render_template("communication/notices.html", notices=notice_list)

@app.route("/notice/delete/<int:nid>")
@login_required
def delete_notice(nid):
    run("UPDATE notices SET is_active = FALSE WHERE id = %s", (nid,))
    flash("🗑️ Notice removed", "success")
    return redirect(url_for("notices"))
    # ---------------- STAFF MANAGEMENT ----------------
@app.route("/staff")
@login_required
def staff():
    try:
        rows = db_all("SELECT * FROM staff WHERE is_active = TRUE ORDER BY name")
        # Total monthly salary expense
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
            (d["emp_id"], d["name"], d.get("designation"), d.get("subject"), 
             d.get("phone"), d.get("email"), d.get("salary") or 0, d.get("joining_date")))
        flash("✅ Staff member added successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e} (Make sure Employee ID is unique)", "error")
    return redirect(url_for("staff"))

@app.route("/staff/delete/<int:sid>")
@login_required
def delete_staff(sid):
    try:
        # Soft delete (record rehne do, bas deactivate kar do)
        run("UPDATE staff SET is_active = FALSE WHERE id = %s", (sid,))
        flash("🗑️ Staff member removed", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("staff"))
    # ---------------- TRANSPORT MANAGEMENT ----------------
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
        flash(f"❌ Error: {e} (Route number must be unique)", "error")
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
    # ---------------- HOSTEL MANAGEMENT ----------------
@app.route("/hostel")
@login_required
def hostel():
    try:
        rooms = db_all("SELECT * FROM hostel_rooms WHERE is_active = TRUE ORDER BY room_no")
        total_capacity = sum(r['capacity'] for r in rooms)
        total_occupied = sum(r['occupied'] for r in rooms)
    except:
        rooms = []
        total_capacity = 0
        total_occupied = 0
    return render_template("facilities/hostel.html", rooms=rooms, total_capacity=total_capacity, total_occupied=total_occupied)

@app.route("/hostel/add", methods=["POST"])
@login_required
def add_hostel_room():
    d = request.form
    try:
        run("""INSERT INTO hostel_rooms (room_no, block, capacity, monthly_fee, warden_name) 
               VALUES (%s, %s, %s, %s, %s)""",
            (d["room_no"], d.get("block"), d.get("capacity") or 4, d.get("monthly_fee") or 0, d.get("warden_name")))
        flash("✅ Hostel room added successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e} (Room number must be unique)", "error")
    return redirect(url_for("hostel"))

@app.route("/hostel/delete/<int:rid>")
@login_required
def delete_hostel_room(rid):
    try:
        run("UPDATE hostel_rooms SET is_active = FALSE WHERE id = %s", (rid,))
        flash("🗑️ Room removed", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("hostel"))
    # ---------------- LIBRARY MANAGEMENT ----------------
@app.route("/library")
@login_required
def library():
    try:
        books = db_all("SELECT * FROM library_books WHERE is_active = TRUE ORDER BY title")
        total_books = sum(b['total_copies'] for b in books)
        available_books = sum(b['available_copies'] for b in books)
    except:
        books = []
        total_books = 0
        available_books = 0
    return render_template("facilities/library.html", books=books, total_books=total_books, available_books=available_books)

@app.route("/library/add", methods=["POST"])
@login_required
def add_book():
    d = request.form
    try:
        copies = int(d.get("total_copies") or 1)
        run("""INSERT INTO library_books (book_id, title, author, category, total_copies, available_copies) 
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (d["book_id"], d["title"], d.get("author"), d.get("category"), copies, copies))
        flash("✅ Book added to library successfully!", "success")
    except Exception as e:
        flash(f"❌ Error: {e} (Book ID must be unique)", "error")
    return redirect(url_for("library"))

@app.route("/library/delete/<int:bid>")
@login_required
def delete_book(bid):
    try:
        run("UPDATE library_books SET is_active = FALSE WHERE id = %s", (bid,))
        flash("🗑️ Book removed from library", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("library"))
    # ---------------- EVENTS MANAGEMENT ----------------
@app.route("/events", methods=["GET", "POST"])
@login_required
def events():
    if request.method == "POST":
        d = request.form
        try:
            run("""INSERT INTO events (event_name, event_date, event_type, location, description) 
                   VALUES (%s, %s, %s, %s, %s)""",
                (d["event_name"], d["event_date"], d.get("event_type"), d.get("location"), d.get("description")))
            flash("✅ Event scheduled successfully!", "success")
        except Exception as e:
            flash(f"❌ Error: {e}", "error")
        return redirect(url_for("events"))

    try:
        # Upcoming aur past events alag karke fetch karo
        upcoming_events = db_all("SELECT * FROM events WHERE is_active = TRUE AND event_date >= %s ORDER BY event_date ASC", (today(),))
        past_events = db_all("SELECT * FROM events WHERE is_active = TRUE AND event_date < %s ORDER BY event_date DESC LIMIT 10", (today(),))
    except:
        upcoming_events = []
        past_events = []
        
    return render_template("management/events.html", upcoming=upcoming_events, past=past_events)

@app.route("/event/delete/<int:eid>")
@login_required
def delete_event(eid):
    try:
        run("UPDATE events SET is_active = FALSE WHERE id = %s", (eid,))
        flash("🗑️ Event removed", "success")
    except Exception as e:
        flash(f"❌ Error: {e}", "error")
    return redirect(url_for("events"))
    # ---------------- CERTIFICATE GENERATION ----------------
@app.route("/certificates")
@login_required
def certificates():
    try:
        students = db_all("SELECT roll_no, name, class_name FROM students ORDER BY roll_no")
    except:
        students = []
    return render_template("management/certificates.html", students=students)

@app.route("/certificate/generate/<roll_no>/<cert_type>")
@login_required
def generate_certificate(roll_no, cert_type):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student not found", "error")
        return redirect(url_for("certificates"))
        
    # TC ya Bonafide ke liye check karo ki dues pending hain ya nahi
    pending_dues = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
    
    return render_template("management/certificate_print.html", 
                           student=student, cert_type=cert_type, 
                           pending_dues=pending_dues, today_date=today())
    # ---------------- PARENT PORTAL (AUTH) ----------------
@app.route("/parent-login", methods=["GET", "POST"])
def parent_login():
    if request.method == "POST":
        u = request.form["username"].strip()
        p = request.form["password"].strip()
        
        parent = one("SELECT * FROM parent_users WHERE username=%s AND password=%s AND is_active=TRUE", (u, p))
        if parent:
            session["parent_user"] = parent["username"]
            session["parent_name"] = parent["parent_name"]
            session["parent_child"] = parent["child_roll_no"]
            return redirect(url_for("parent_dashboard"))
        flash("Invalid parent credentials!", "error")
    return render_template("auth/parent_login.html")

@app.route("/parent-dashboard")
def parent_dashboard():
    if "parent_user" not in session:
        return redirect(url_for("parent_login"))
        
    roll_no = session["parent_child"]
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student data not found!", "error")
        return redirect(url_for("parent_login"))
        
    # 1. Fee Data
    bills = db_all("SELECT * FROM bills WHERE roll_no=%s ORDER BY month DESC", (roll_no,))
    total_due = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE roll_no=%s AND balance>0", (roll_no,))["t"]
    
    # 2. Marks Data
    marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
    total_obtained = sum(float(m['marks'] or 0) for m in marks)
    total_max = sum(float(m['total'] or 0) for m in marks)
    percentage = round((total_obtained / total_max * 100), 2) if total_max > 0 else 0
    
    # 3. Attendance Data
    total_att = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll_no,))["c"]
    present_att = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll_no,))["c"]
    att_pct = round((present_att / total_att * 100), 1) if total_att > 0 else 100
    
    return render_template("parent/parent_dashboard.html", student=student, bills=bills, total_due=total_due, marks=marks, percentage=percentage, att_pct=att_pct)

@app.route("/parent-logout")
def parent_logout():
    session.pop("parent_user", None)
    session.pop("parent_name", None)
    session.pop("parent_child", None)
    return redirect(url_for("parent_login"))

# ---------------- ADMIN: CREATE PARENT ACCOUNTS ----------------
@app.route("/manage-parents", methods=["GET", "POST"])
@login_required
def manage_parents():
    if request.method == "POST":
        d = request.form
        try:
            run("INSERT INTO parent_users (username, password, parent_name, child_roll_no) VALUES (%s,%s,%s,%s)",
                (d["username"], d["password"], d.get("parent_name"), d["child_roll_no"]))
            flash("✅ Parent account created successfully!", "success")
        except Exception as e:
            flash(f"❌ Error: {e} (Username might already exist)", "error")
        return redirect(url_for("manage_parents"))
        
    parents = db_all("""
        SELECT pu.*, s.name as student_name 
        FROM parent_users pu 
        LEFT JOIN students s ON pu.child_roll_no = s.roll_no 
        ORDER BY pu.id DESC
    """)
    students = db_all("SELECT roll_no, name FROM students ORDER BY roll_no")
    return render_template("parent/manage_parents.html", parents=parents, students=students)

@app.route("/parent/delete/<int:pid>")
@login_required
def delete_parent(pid):
    run("DELETE FROM parent_users WHERE id=%s", (pid,))
    flash("🗑️ Parent account deleted", "success")
    return redirect(url_for("manage_parents"))
    # ---------------- ANALYTICS & REPORTS ----------------
@app.route("/analytics")
@login_required
def analytics():
    try:
        # 1. Monthly Collection Data (Last 6 Months)
        monthly_data = db_all("""
            SELECT to_char(pay_date, 'Mon YYYY') as month, SUM(amount) as total
            FROM payments 
            GROUP BY to_char(pay_date, 'Mon YYYY'), date_trunc('month', pay_date)
            ORDER BY date_trunc('month', pay_date) ASC LIMIT 6
        """)
        
        # 2. Class Distribution Data (Students per class)
        class_dist = db_all("SELECT class_name, COUNT(*) as count FROM students GROUP BY class_name ORDER BY class_name")
        
        # 3. Top 5 Payers
        top_payers = db_all("""
            SELECT s.name, s.roll_no, SUM(p.amount) as total_paid
            FROM payments p 
            JOIN students s ON p.roll_no = s.roll_no
            GROUP BY s.name, s.roll_no 
            ORDER BY total_paid DESC LIMIT 5
        """)
        
        # 4. Overall Totals
        total_collection = one("SELECT COALESCE(SUM(amount),0) t FROM payments")["t"]
        pending_dues = one("SELECT COALESCE(SUM(balance),0) t FROM bills WHERE balance > 0")["t"]
        
    except Exception as e:
        print("Analytics Error:", e)
        monthly_data, class_dist, top_payers = [], [], []
        total_collection, pending_dues = 0, 0

    return render_template("management/analytics.html", 
                           monthly_data=monthly_data, class_dist=class_dist, 
                           top_payers=top_payers, total_collection=total_collection, 
                           pending_dues=pending_dues)
    # ---------------- SYSTEM SETTINGS ----------------
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        d = request.form
        try:
            run("""UPDATE school_settings SET school_name=%s, address=%s, phone=%s, email=%s, principal_name=%s, logo_url=%s WHERE id=1""",
                (d["school_name"], d["address"], d["phone"], d["email"], d["principal_name"], d["logo_url"]))
            flash("✅ Settings updated successfully!", "success")
        except Exception as e:
            flash(f"❌ Error: {e}", "error")
        return redirect(url_for("settings"))
        
    return render_template("management/settings.html")

# ---------------- BACKUP & EXPORT ----------------
@app.route("/backup")
@login_required
def backup():
    return render_template("management/backup.html")

@app.route("/backup/download/<table_name>")
@login_required
def download_csv(table_name):
    allowed_tables = ['students', 'fees', 'bills', 'payments', 'staff', 'marks', 'attendance']
    if table_name not in allowed_tables:
        flash("❌ Invalid table", "error")
        return redirect(url_for("backup"))

    try:
        data = db_all(f"SELECT * FROM {table_name}")
        if not data:
            flash(f"⚠️ No data found in {table_name}", "warning")
            return redirect(url_for("backup"))
            
        # CSV Generate karne ka logic
        si = StringIO()
        cw = csv.writer(si)
        # Headers
        cw.writerow(data[0].keys())
        # Rows
        for row in data:
            cw.writerow(row.values())
            
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename={table_name}_backup.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    except Exception as e:
        flash(f"❌ Error exporting data: {e}", "error")
        return redirect(url_for("backup"))
# ---------------- STUDENT PROFILE & ID CARD ----------------
@app.route("/student/profile/<roll_no>")
@login_required
def student_profile(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("students"))
        
    # Fee Details
    bills = db_all("SELECT * FROM bills WHERE roll_no=%s ORDER BY month DESC", (roll_no,))
    total_due = sum(float(b['balance']) for b in bills)
    
    # Marks Details
    marks = db_all("SELECT * FROM marks WHERE roll_no=%s ORDER BY subject", (roll_no,))
    total_obtained = sum(float(m['marks'] or 0) for m in marks)
    total_max = sum(float(m['total'] or 0) for m in marks)
    percentage = round((total_obtained / total_max * 100), 2) if total_max > 0 else 0
    
    # Attendance Details
    total_att = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s", (roll_no,))["c"]
    present_att = one("SELECT COUNT(*) c FROM attendance WHERE roll_no=%s AND status='Present'", (roll_no,))["c"]
    att_pct = round((present_att / total_att * 100), 1) if total_att > 0 else 0
    
    return render_template("students/student_profile.html", 
                           student=student, bills=bills, total_due=total_due,
                           marks=marks, total_obtained=total_obtained, 
                           total_max=total_max, percentage=percentage, 
                           att_pct=att_pct)

@app.route("/student/id-card/<roll_no>")
@login_required
def student_id_card(roll_no):
    student = one("SELECT * FROM students WHERE roll_no=%s", (roll_no,))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("students"))
    return render_template("students/id_card.html", student=student)

# ---------------- APP START ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
