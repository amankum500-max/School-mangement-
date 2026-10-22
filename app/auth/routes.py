from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from database import one
from functools import wraps

auth_bp = Blueprint('auth', __name__)

# Decorator
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*a, **kw)
    return wrapper

@auth_bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        
        if u == "admin" and p == "admin123":
            session["user"] = u
            session["role"] = "admin"
            session["name"] = "System Admin"
            
            # School ID Set karein
            default_school = one("SELECT id FROM schools WHERE subdomain='default'")
            session["school_id"] = str(default_school["id"]) if default_school else None
            
            # Login ke baad Dashboard par bhejein
            return redirect(url_for("students.dashboard"))
            
        flash("Invalid credentials!", "error")
    
    # HTML path change hoga
    return render_template("auth/login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
