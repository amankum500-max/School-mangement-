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
    
# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
