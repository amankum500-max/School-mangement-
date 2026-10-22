from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import all as db_all, one, run
from app.auth.routes import login_required
from datetime import datetime

students_bp = Blueprint('students', __name__)

@students_bp.route("/dashboard")
@login_required
def dashboard():
    # Dashboard ka data yahan fetch hoga
    return render_template("school_admin/dashboard.html")

@students_bp.route("/students")
@login_required
def students():
    current_school_id = session.get("school_id")
    # Multi-tenancy filter (Sirf apne school ka data)
    students_list = db_all("SELECT * FROM students WHERE school_id=%s ORDER BY roll_no", (current_school_id,))
    return render_template("students/students.html", students=students_list)

@students_bp.route("/student/profile/<roll_no>")
@login_required
def profile(roll_no):
    school_id = session.get("school_id")
    # Pehle roll_no se student_id (UUID) nikaalein
    student = one("SELECT * FROM students WHERE roll_no=%s AND school_id=%s", (roll_no, school_id))
    if not student:
        flash("Student not found", "error")
        return redirect(url_for("students.students"))
    
    student_id = student['id']
    
    # Fees data nikaalein (student_id use karke)
    total_due = one("SELECT COALESCE(SUM(back_dues),0) t FROM student_fees WHERE student_id=%s", (student_id,))['t']
    
    return render_template("students/student_profile.html", student=student, total_due=total_due)
