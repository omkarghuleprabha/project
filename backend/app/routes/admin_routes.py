from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.utils.db import get_db

# 1. Blueprint EKDACH define kara
admin_bp = Blueprint(
    "admin_bp",
    __name__,
    url_prefix="/admin",
    template_folder="../templates"
)

# ---------- SECURITY MIDDLEWARES ----------
def is_super_admin():
    return session.get('is_super_admin') == True

def is_admin_logged_in():
    return "admin_id" in session

# ---------- 👑 SUPER ADMIN (HEAD OF SYSTEM) ----------

@admin_bp.route('/super-admin-login', methods=['GET', 'POST'])
def super_admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # TUZA SPECIAL MASTER PASSWORD
        if username == "Omkar_Head" and password == "!@#$%^&Omkar!@#$%^&":
            session['is_super_admin'] = True
            return redirect(url_for('admin_bp.super_admin_dashboard'))
        else:
            flash("Invalid Master Credentials", "danger")

    return render_template('admin/super_login.html')

@admin_bp.route('/super-admin-dashboard')
def super_admin_dashboard():
    if not is_super_admin():
        return redirect(url_for('admin_bp.super_admin_login'))
    
    # Ithe tu purna city che stats dakhvu shakto
    return render_template('admin/super_admin.html')

# ---------- 🛡️ NORMAL ADMIN (STAFF) LOGIN ----------

@admin_bp.route("/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM admins WHERE email=%s AND password=%s AND status='approved'", (email, password))
        admin = cursor.fetchone()
        conn.close()

        if admin:
            session["admin_id"] = admin[0]
            session["admin_name"] = admin[1]
            return redirect(url_for('admin_bp.admin_dashboard'))
        else:
            flash("Invalid Credentials or Pending Approval", "danger")
            
    return render_template("admin/login.html")

# ---------- 📊 STAFF DASHBOARD & MANAGEMENT ----------

@admin_bp.route("/dashboard")
def admin_dashboard():
    if not is_admin_logged_in(): return redirect(url_for('admin_bp.admin_login'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM requests WHERE status='pending'")
    pending_req = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM requests WHERE status='completed'")
    completed_req = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM workers WHERE status='approved'")
    total_workers = cursor.fetchone()[0]
    conn.close()
    
    return render_template("admin/dashboard.html", pending=pending_req, completed=completed_req, workers=total_workers)

@admin_bp.route("/workers")
def admin_workers():
    if not is_admin_logged_in(): return redirect(url_for('admin_bp.admin_login'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workers WHERE status='pending'")
    workers = cursor.fetchall()
    conn.close()
    return render_template("admin/workers.html", workers=workers)

@admin_bp.route("/approve_worker/<id>")
def approve_worker(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE workers SET status='approved' WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_bp.admin_workers'))

# ---------- 🚪 LOGOUT ----------
@admin_bp.route("/logout")
def admin_logout():
    session.clear()
    return redirect(url_for('admin_bp.admin_login'))