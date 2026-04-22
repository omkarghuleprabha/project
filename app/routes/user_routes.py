import os
from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify
from app.utils.db import get_db
from app.utils.auth import build_auth_payload, make_login_response, make_logout_response
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


def save_uploaded_file(file, subfolder):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return None

    upload_folder = os.path.join("backend", "app", "static", "uploads", subfolder)
    os.makedirs(upload_folder, exist_ok=True)

    filename = secure_filename(file.filename)
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1

    while os.path.exists(os.path.join(upload_folder, candidate)):
        candidate = f"{base}_{counter}{ext}"
        counter += 1

    file.save(os.path.join(upload_folder, candidate))
    return candidate


def get_post_redirect(default_endpoint):
    next_url = (request.form.get("next") or "").strip()
    if next_url.startswith("/"):
        return next_url
    return url_for(default_endpoint)

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
            role = user.get("account_type") or "user"
            auth_payload = build_auth_payload(user, role)

            flash(f"Welcome back, {auth_payload['user_name']}!", "success")
            return make_login_response("user_bp.user_dashboard", auth_payload)
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


@user_bp.route("/complaint/add", methods=["POST"])
def add_complaint():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))
    redirect_target = get_post_redirect("auth_bp.citizen_complaints")

    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    district = request.form.get("district", "").strip()
    taluka = request.form.get("taluka", "").strip()
    village = request.form.get("village", "").strip()
    priority = request.form.get("priority", "Normal").strip() or "Normal"
    photo = request.files.get("garbage_img")

    if not all([title, description, district, taluka, village]):
        flash("Please fill in all complaint details.", "danger")
        return redirect(redirect_target)

    photo_name = save_uploaded_file(photo, "complaints")
    if photo and photo.filename and not photo_name:
        flash("Please upload a valid image file (PNG/JPG/JPEG).", "danger")
        return redirect(redirect_target)

    conn = get_db()
    cursor = conn.cursor()

    try:
        query = """
            INSERT INTO complaints
            (user_id, title, description, district, taluka, village, photo_path, priority, status, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pending', NOW())
        """
        cursor.execute(
            query,
            (session["user_id"], title, description, district, taluka, village, photo_name, priority)
        )
        conn.commit()
        flash("Complaint submitted successfully.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Complaint Save Error: {e}")
        flash("Failed to save complaint. Please try again.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@user_bp.route("/pickup/request", methods=["POST"])
def pickup_request():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))
    redirect_target = get_post_redirect("auth_bp.citizen_pickup")

    pickup_type = request.form.get("pickupType", "Door-to-Door").strip() or "Door-to-Door"
    waste_type = request.form.get("wasteType", "").strip()
    scheduled_time = request.form.get("scheduled_time", "").strip()

    if not waste_type or not scheduled_time:
        flash("Please complete the pickup form.", "danger")
        return redirect(redirect_target)

    amount = 150 if pickup_type == "Door-to-Door" else 500
    garbage_type = f"{pickup_type} | {waste_type} | {scheduled_time}"

    conn = get_db()
    cursor = conn.cursor()

    try:
        query = """
            INSERT INTO requests (user_id, garbage_type, weight, status, amount, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """
        cursor.execute(query, (session["user_id"], garbage_type, 0, "pending", amount))
        conn.commit()
        flash("Pickup request saved successfully.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Pickup Save Error: {e}")
        flash("Failed to save pickup request. Please try again.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)


@user_bp.route("/payment/process", methods=["POST"])
def process_payment():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))
    redirect_target = get_post_redirect("auth_bp.citizen_payments")

    amount = request.form.get("amount", "").strip()
    gateway = request.form.get("gateway", "").strip().lower()

    try:
        total = float(amount)
        if total <= 0:
            raise ValueError("Amount must be positive")
    except (TypeError, ValueError):
        flash("Enter a valid payment amount.", "danger")
        return redirect(redirect_target)

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT id FROM requests WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT 1",
            (session["user_id"],)
        )
        latest_request = cursor.fetchone()
        if not latest_request:
            conn.close()
            flash("Create a pickup request before making a payment so the payment stays linked to your account.", "warning")
            return redirect(redirect_target)

        request_id = latest_request["id"]

        owner_share = round(total * 0.50, 2)
        admin_share = round(total * 0.30, 2)
        worker_share = round(total * 0.20, 2)

        insert_cursor = conn.cursor()
        insert_cursor.execute(
            """
            INSERT INTO payments (request_id, total, owner_share, admin_share, worker_share, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (request_id, total, owner_share, admin_share, worker_share)
        )
        conn.commit()
        flash(f"Payment saved successfully via {gateway or 'UPI'}.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Payment Save Error: {e}")
        flash("Failed to save payment. Please try again.", "danger")
    finally:
        conn.close()

    return redirect(redirect_target)

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
    flash("You have been logged out.", "info")
    return make_logout_response("/", use_url=True)
