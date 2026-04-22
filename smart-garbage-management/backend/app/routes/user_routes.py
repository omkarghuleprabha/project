import os
from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify
from app.utils.db import get_db
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

user_bp = Blueprint(
    "user_bp",
    __name__,
    url_prefix="/user",
    template_folder="../templates"
)

# Configuration for File Upload
UPLOAD_FOLDER = 'app/static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Helper to check file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- USER LOGIN ----------
@user_bp.route("/login", methods=["GET", "POST"])
def user_login():
    if request.method == "POST":
        identifier = request.form.get("identifier") # Email or Phone
        password = request.form.get("password")
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        # Check by email or phone in the single 'users' table
        query = "SELECT * FROM users WHERE email=%s OR phone=%s"
        cursor.execute(query, (identifier, identifier))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session.clear()
            session["user_id"] = user['id']
            session["user_name"] = user['full_name']
            session["user_email"] = user['email']
            session["role"] = user['account_type']
            
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("user_bp.user_dashboard"))
        else:
            flash("Invalid email/phone or password.", "danger")
            
    return render_template("auth/login.html")

# ---------- USER DASHBOARD ----------
@user_bp.route("/dashboard")
def user_dashboard():
    if "user_id" not in session: 
        return redirect(url_for("user_bp.user_login"))
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch all complaints/requests filed by this user
    cursor.execute("SELECT * FROM requests WHERE user_id=%s ORDER BY created_at DESC", (session["user_id"],))
    my_requests = cursor.fetchall()
    
    # Calculate stats for the dashboard cards
    cursor.execute("SELECT COUNT(*) as total FROM requests WHERE user_id=%s", (session["user_id"],))
    total_count = cursor.fetchone()['total']
    
    conn.close()
    
    return render_template("dashboard/citizen_dash.html", requests=my_requests, total=total_count)

# ---------- NEW COMPLAINT / REQUEST ----------
@user_bp.route("/new_request", methods=["POST"])
def new_request():
    if "user_id" not in session: return redirect(url_for("user_bp.user_login"))
    
    title = request.form.get("title")
    description = request.form.get("description")
    area = request.form.get("area")
    file = request.files.get('photo')
    
    filename = "no_image.png"
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Ensure upload folder exists
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
        file.save(os.path.join(UPLOAD_FOLDER, filename))
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        query = """
            INSERT INTO requests (user_id, area, photo, description, status, amount, created_at) 
            VALUES (%s, %s, %s, %s, 'pending', 150.00, NOW())
        """
        cursor.execute(query, (session["user_id"], area, filename, description))
        conn.commit()
        conn.close()
        flash("Your garbage pickup request has been filed!", "success")
    except Exception as e:
        print(f"Error: {e}")
        flash("Failed to file request. Try again.", "danger")
        
    return redirect(url_for("user_bp.user_dashboard"))

# ---------- PAYMENT (UPI QR Logic) ----------
@user_bp.route("/payment/<int:req_id>")
def user_payment(req_id):
    if "user_id" not in session: return redirect(url_for("user_bp.user_login"))
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM requests WHERE id=%s AND user_id=%s", (req_id, session["user_id"]))
    order = cursor.fetchone()
    conn.close()

    if order:
        upi_id = "municipality@upi" 
        amount = order['amount'] 
        upi_url = f"upi://pay?pa={upi_id}&pn=SmartGarbage&am={amount}&cu=INR"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={upi_url}"
        return render_template("dashboard/payment_modal_content.html", order=order, qr_url=qr_url)
    
    flash("Request not found.", "danger")
    return redirect(url_for("user_bp.user_dashboard"))

# ---------- LOGOUT ----------
@user_bp.route("/logout")
def user_logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect("http://127.0.0.1:5000/")