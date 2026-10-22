
# app/fees/routes.py mein yeh routes update karein:

# 1. PDF Receipt (Ab URL mein student_id aayega)
@fees_bp.route("/fees/pdf/<student_id>")
@login_required
def fee_pdf(student_id):
    school_id = session.get("school_id")
    student = one("SELECT * FROM students WHERE id=%s AND school_id=%s", (student_id, school_id))
    fee = one("SELECT * FROM student_fees WHERE student_id=%s", (student_id,))
    if not student or not fee:
        flash("Record not found", "error")
        return redirect(url_for("fees.fees_list"))
    # ... baaki PDF generation code waisa hi rahega ...
    return send_file(io.BytesIO(pdf.output(dest='S').encode('latin-1')), mimetype="application/pdf", as_attachment=True, download_name=f"Receipt_{student['roll_no']}.pdf")


# 2. AI Reminder
@fees_bp.route("/fees/ai-reminder/<student_id>")
@login_required
def fees_ai_reminder(student_id):
    student = one("SELECT name, class_name, parent_contact FROM students WHERE id=%s", (student_id,))
    fee = one("SELECT back_dues FROM student_fees WHERE student_id=%s", (student_id,))
    dues = fee['back_dues'] if fee else 0
    msg = f"Dear Parent, {student['name']} (Class {student['class_name']}) ki fees me Rs {dues} pending hai. Kripya jaldi jama karein. - School ERP"
    # ... AI logic waisa hi rahega ...
    return jsonify({"message": msg, "contact": student['parent_contact']})


# 3. UPI QR Code
@fees_bp.route("/fees/upi-qr/<student_id>")
@login_required
def generate_upi_qr(student_id):
    fee = one("SELECT back_dues FROM student_fees WHERE student_id=%s", (student_id,))
    amount = fee['back_dues'] if fee else 0
    # ... QR generation logic waisa hi rahega ...
    return jsonify({"qr_code": base64.b64encode(buffered.getvalue()).decode(), "amount": amount})

# 4. Waive Off (Form se student_id aa rahi hai)
@fees_bp.route("/fees/waive-off", methods=["POST"])
@login_required
def waive_off_fees():
    student_id = request.form.get("student_id") # Roll no nahi, ID aayegi
    run("UPDATE student_fees SET back_dues=0 WHERE student_id=%s", (student_id,))
    flash(f"⚖️ Dues maaf kar diye gaye hain.", "success")
    return redirect(url_for('fees.fees_list'))

# 5. Bulk Action (Delete)
@fees_bp.route("/fees/bulk-action", methods=["POST"])
@login_required
def bulk_action():
    if request.form.get("action") == "delete":
        selected_ids = request.form.getlist("selected_students") # UUIDs ki list
        for sid in selected_ids:
            run("DELETE FROM student_fees WHERE student_id=%s", (sid,))
        flash(f"🗑️ {len(selected_ids)} fee records deleted!", "success")
    return redirect(url_for('fees.fees_list'))
