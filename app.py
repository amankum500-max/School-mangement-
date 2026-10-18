from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from datetime import datetime
from database import init_db, run, all as db_all, one, current_month, today
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "school-secret-key-2026")

# ---------------- AUTH ----------------
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
    except:
        students_count, total_due, today_collection = 0, 0, 0

    return render_template("dashboard/dashboard.html",
        students=students_count, total_due=total_due,
        today_collection=today_collection
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
# ---------------- ADD STUDENT ----------------
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

# ---------------- COLLECT FEE (Basic) ----------------
@app.route("/collect/<roll_no>", methods=["GET", "POST"])
@login_required
def collect(roll_no):
    if request.method == "POST":
        amount = float(request.form.get("amount") or 0)
        try:
            # Payment insert
            run("""INSERT INTO payments (receipt_no, roll_no, amount, mode, pay_date, remark)
                   VALUES (%s, %s, %s, 'Cash', %s, 'Fee Payment')""",
                (f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}", roll_no, amount, today()))
            
            # Agar bills me balance hai, toh usko update karo (basic logic)
            bills = db_all("SELECT id, balance FROM bills WHERE roll_no=%s AND balance>0 ORDER BY id", (roll_no,))
            rem = amount
            for b in bills:
                if rem <= 0: break
                deduct = min(rem, float(b['balance']))
                run("UPDATE bills SET paid = paid + %s, balance = balance - %s WHERE id=%s", (deduct, deduct, b['id']))
                rem -= deduct
                
            flash(f"✅ ₹{amount} collected successfully!", "success")
            return redirect(url_for("fees"))
        except Exception as e:
            flash(f"❌ Error: {e}", "error")
            
    return redirect(url_for("fees"))
   # ---------------- BILLS ----------------
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
    students = db_all("SELECT roll_no, name FROM students")
    created = skipped = 0
    
    for s in students:
        roll = s["roll_no"]
        # Check if bill already exists for this month
        ex = one("SELECT id FROM bills WHERE roll_no=%s AND month=%s", (roll, month))
        if ex:
            skipped += 1; continue
            
        fs = one("SELECT * FROM student_fees WHERE roll_no=%s", (roll,))
        if not fs:
            skipped += 1; continue
            
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
        
        # Fetch previous dues
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

# ---------------- DEFAULTERS ----------------
@app.route("/defaulters")
@login_required
def defaulters():
    try:
        rows = db_all("""SELECT s.roll_no, s.name, s.class_name, s.section,
                         s.parent_contact, b.month, b.balance
                         FROM bills b JOIN students s ON b.roll_no = s.roll_no
                         WHERE b.balance > 0 ORDER BY b.balance DESC""")
        total = sum(float(r["balance"]) for r in rows)
    except:
        rows = []
        total = 0
    return render_template("fees/defaulters.html", defaulters=rows, total=total) 
# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
