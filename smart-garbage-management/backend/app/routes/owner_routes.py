from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.utils.db import get_db

owner_bp = Blueprint(
    "owner_bp",
    __name__,
    url_prefix="/owner",
    template_folder="../templates"
)

# --- 🔐 OWNER LOGIN ---
@owner_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Super Admin Hardcoded Credentials
        if email == "owner@gmail.com" and password == "1234":
            session.clear()
            session['user_id'] = 0
            session['user_name'] = "Master Admin"
            session['role'] = "super_admin"
            flash("Welcome to the Master Control Panel", "success")
            return redirect(url_for("owner_bp.dashboard"))
        
        flash("Invalid Owner Credentials", "danger")
        return redirect(url_for("owner_bp.login"))

    return render_template("owner/login.html")

# --- 📊 MASTER DASHBOARD ---
@owner_bp.route("/dashboard")
def dashboard():
    # Security: Ensure only the Super Admin can enter
    if session.get('role') != 'super_admin':
        flash("Unauthorized Access!", "danger")
        return redirect(url_for("owner_bp.login"))

    conn = get_db()
    cur = conn.cursor()

    # 1. Total Citizens
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    # 2. Total Workers across all villages
    cur.execute("SELECT COUNT(*) FROM village_workers")
    workers = cur.fetchone()[0]

    # 3. Total Complaints/Requests
    cur.execute("SELECT COUNT(*) FROM complaints")
    req = cur.fetchone()[0]

    # 4. Total Payments/Revenue
    # Using COALESCE to return 0 if there are no payments yet
    cur.execute("SELECT COALESCE(SUM(amount), 0) FROM payments")
    pay = cur.fetchone()[0]

    # 5. Admin Counts (New Feature for Owner)
    cur.execute("SELECT COUNT(*) FROM district_admins")
    dist_admins = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM taluka_admins")
    tal_admins = cur.fetchone()[0]

    conn.close()

    return render_template(
        "dashboard/owner_dash.html", # Using the new advanced dashboard folder
        users=users,
        workers=workers,
        req=req,
        pay=pay,
        dist_admins=dist_admins,
        tal_admins=tal_admins
    )