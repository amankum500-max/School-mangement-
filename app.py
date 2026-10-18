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
    return render_template("SHARED/AUTH (4)/login.html")
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

    return render_template("SHARED/dashboard.html",
        students=students_count, total_due=total_due,
        today_collection=today_collection, lifetime_profit=0,
        fee_status={"paid":0, "partial":0, "unpaid":0}, top_defaulters=[],
        class_strength=[], performers_list=[], birthdays=[], recent=[], 
        recent_admissions=[], monthly_trend=[], ai_insight="AI loading...",
        monthly_target=100000, progress_pct=0, current_collection=0
    )

# ---------------- STUDENTS ----------------
@app.route("/students")
@login_required
def students():
    try:
        rows = db_all("SELECT * FROM students ORDER BY roll_no")
    except:
        rows = []
      return render_template("STUDENTS (6)/students.html", students=rows, classes=[], q="", class_filter="", fee_filter="", page=1, total_pages=1)  

# ---------------- FEES ----------------
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
        return render_template("FEES (8)/fees.html", fees=rows)

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
