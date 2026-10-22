from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from database import all as db_all, one, run, today
from app.auth.routes import login_required
from datetime import datetime, date
import qrcode
import io
import base64

fees_bp = Blueprint('fees', __name__)

# 1. FEES DASHBOARD (List View)
@fees_bp.route("/fees")
@login_required
def fees_list():
    school_id = session.get("school_id")
    
    # Query mein humne 's.id = f.student_id' use kiya hai
    rows = db_all("""
        SELECT s.roll_no, s.name, s.class_name, s.section, s.father_name, s.id AS student_id,
               COALESCE(f.tuition_fee, 0) AS tuition_fee, 
               COALESCE(f.transport_fee, 0) AS transport_fee, 
               COALESCE(f.discount, 0) AS discount, 
               COALESCE(f.back_dues, 0) AS back_dues, 
               f.due_date, 
               COALESCE(f.wallet_balance, 0) AS wallet_balance
        FROM students s
        LEFT JOIN student_fees f ON s.id = f.student_id
        WHERE s.school_id = %s
        ORDER BY s.roll_no
    """, (school_id,))
    
    # Aging Logic (Purana code)
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
                if days_overdue <= 0: aging_bucket = "Current"
                elif days_overdue <= 30: aging_bucket = "0-30 Days"; aging_stats["0-30"] += dues
                elif days_overdue <= 60: aging_bucket = "30-60 Days"; aging_stats["30-60"] += dues
                else: aging_bucket = "60+ Days"; aging_stats["60+"] += dues
            except: aging_bucket = "N/A"
                
        r_dict['aging_bucket'] = aging_bucket
        processed_rows.append(r_dict)
        
    return render_template("fees/fees.html", fees=processed_rows, aging_stats=aging_stats)


# 2. SAVE / UPDATE FEES
@fees_bp.route("/fees/save", methods=["POST"])
@login_required
def save_fees():
    d = request.form
    roll = d["roll_no"]
    school_id = session.get("school_id")
    
    # Roll no se student_id (UUID) nikaalein
    student = one("SELECT id FROM students WHERE roll_no=%s AND school_id=%s", (roll, school_id))
    if not student:
        flash("Student not found!", "error")
        return redirect(url_for("fees.fees_list"))
        
    student_id = student['id']

    # Check existing record
    existing = one("SELECT id FROM student_fees WHERE student_id=%s", (student_id,))
    
    vals = (
        float(d.get("tuition_fee") or 0), float(d.get("transport_fee") or 0), 
        float(d.get("hostel_fee") or 0), float(d.get("misc_fee") or 0), 
        float(d.get("discount") or 0), float(d.get("late_fee") or 0),
        float(d.get("back_dues") or 0), d.get("due_date") or None, 
        float(d.get("wallet_balance") or 0), student_id, school_id
    )
    
    if existing:
        run("""UPDATE student_fees SET tuition_fee=%s, transport_fee=%s, hostel_fee=%s, misc_fee=%s,
            discount=%s, late_fee=%s, back_dues=%s, due_date=%s, wallet_balance=%s 
            WHERE student_id=%s AND school_id=%s""", vals)
        flash("✅ Fee structure updated!", "success")
    else:
        run("""INSERT INTO student_fees (tuition_fee,transport_fee,hostel_fee,misc_fee,
             discount,late_fee,back_dues,due_date,wallet_balance,student_id, school_id) 
             VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", vals)
        flash("✅ New Fee structure added!", "success")
        
    return redirect(url_for("fees.fees_list"))


# 3. COLLECT FEE (Payment)
@fees_bp.route("/collect/<roll_no>", methods=["GET", "POST"])
@login_required
def collect(roll_no):
    school_id = session.get("school_id")
    student = one("SELECT * FROM students WHERE roll_no=%s AND school_id=%s", (roll_no, school_id))
    if not student:
        flash("Student not found", "error")
        return redirect(url_for("students.students"))

    if request.method == "POST":
        amount = float(request.form.get("amount") or 0)
        mode = request.form.get("mode", "Cash")
        remark = request.form.get("remark", "")
        
        if amount <= 0:
            flash("Amount must be greater than 0", "error")
            return redirect(url_for("fees.collect", roll_no=roll_no))

        try:
            receipt_no = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Payments table mein entry
            run("""INSERT INTO payments (receipt_no, school_id, student_id, amount, mode, pay_date, remark)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (receipt_no, school_id, student['id'], amount, mode, today(), remark))
            
            # Back Dues update logic (student_id se)
            fee_record = one("SELECT back_dues FROM student_fees WHERE student_id=%s", (student['id'],))
            if fee_record and fee_record['back_dues'] > 0:
                new_dues = max(0, float(fee_record['back_dues']) - amount)
                run("UPDATE student_fees SET back_dues=%s WHERE student_id=%s", (new_dues, student['id']))
                
            flash(f"✅ ₹{amount} collected successfully!", "success")
            return redirect(url_for("fees.receipt", roll_no=roll_no, receipt_no=receipt_no))
        except Exception as e:
            flash(f"❌ Error: {e}", "error")
            
    # Fetch dues for the form
    fee_record = one("SELECT * FROM student_fees WHERE student_id=%s", (student['id'],))
    total_due = fee_record['back_dues'] if fee_record else 0
    
    return render_template("fees/collect.html", student=student, total_due=total_due)


# 4. PRINT RECEIPT
@fees_bp.route("/receipt/<roll_no>/<receipt_no>")
@login_required
def receipt(roll_no, receipt_no):
    school_id = session.get("school_id")
    student = one("SELECT * FROM students WHERE roll_no=%s AND school_id=%s", (roll_no, school_id))
    payment = one("SELECT * FROM payments WHERE receipt_no=%s AND school_id=%s", (receipt_no, school_id))
    
    if not student or not payment:
        flash("Receipt not found", "error")
        return redirect(url_for("students.students"))
        
    return render_template("fees/receipt.html", student=student, payment=payment, now=datetime.now())
