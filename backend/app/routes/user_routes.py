import os
from flask import Blueprint, render_template, request, redirect, session, url_for, flash, jsonify
from app.utils.db import get_db
from app.utils.location import ensure_request_location_columns, parse_submitted_location
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from app.routes.auth_routes import _get_citizen_dashboard_data, _get_user_complaints

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


def _get_post_redirect_target(default_endpoint):
    next_page = (request.form.get("next_page") or "").strip()
    if next_page.startswith("/"):
        return next_page
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
            session.clear()
            session["user_id"] = user['id']
            session["user_name"] = user.get('name') or user.get('full_name')
            session["user_email"] = user['email']
            session["email"] = user['email']
            session["role"] = user.get('role') or user.get('account_type') or 'user'
            
            flash(f"Welcome back, {session['user_name']}!", "success")
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
    
    data = _get_citizen_dashboard_data(session["user_id"], cursor)
    
    conn.close()
    
    return render_template("dashboard/citizen_dash.html", **data, citizen_page='dashboard')

# ---------- NEW COMPLAINT / REQUEST ----------
@user_bp.route("/new_request", methods=["POST"])
def new_request():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))

    redirect_target = _get_post_redirect_target("user_bp.user_dashboard")
    
    pickup_type = request.form.get("pickupType", "Door-to-Door")
    waste_type = request.form.get("wasteType", "Mixed Waste")
    scheduled_time = request.form.get("scheduled_time")
    garbage_type = f"{pickup_type} - {waste_type}"
    try:
        location = parse_submitted_location(request.form)
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(redirect_target)
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        amount = 300 if pickup_type.lower() == "bulk" else 150
        request_columns = ensure_request_location_columns(cursor)

        columns = ["user_id", "garbage_type", "status", "amount", "created_at"]
        values = [session["user_id"], garbage_type, "pending", amount]
        placeholders = ["%s", "%s", "%s", "%s", "NOW()"]

        if "latitude" in request_columns:
            columns.append("latitude")
            values.append(location.get("latitude"))
            placeholders.append("%s")
        if "longitude" in request_columns:
            columns.append("longitude")
            values.append(location.get("longitude"))
            placeholders.append("%s")
        if "location_accuracy_meters" in request_columns:
            columns.append("location_accuracy_meters")
            values.append(location.get("location_accuracy_meters"))
            placeholders.append("%s")

        query = f"""
            INSERT INTO requests ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
        """
        cursor.execute(query, tuple(values))
        conn.commit()
        conn.close()
        flash("Your garbage pickup request has been filed successfully.", "success")
    except Exception as e:
        print(f"Error: {e}")
        flash("Failed to file request. Try again.", "danger")
        
    return redirect(redirect_target)


@user_bp.route("/process-payment", methods=["POST"])
def process_dashboard_payment():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))

    request_id = request.form.get("request_id", type=int)
    amount = request.form.get("amount", type=float)
    gateway = request.form.get("gateway", "upi")

    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        if request_id:
            cursor.execute("SELECT id, amount, user_id FROM requests WHERE id=%s AND user_id=%s", (request_id, session["user_id"]))
            order = cursor.fetchone()
            if not order:
                conn.close()
                flash("Selected request was not found.", "danger")
                return redirect(url_for("user_bp.user_dashboard"))
            amount = float(order.get("amount") or amount or 0)
        else:
            cursor.execute(
                "SELECT id FROM requests WHERE user_id=%s ORDER BY created_at DESC, id DESC LIMIT 1",
                (session["user_id"],)
            )
            latest_request = cursor.fetchone()
            if not latest_request:
                conn.close()
                flash("Create a pickup request before making a payment so the payment stays linked to your account.", "warning")
                return redirect(url_for("user_bp.user_dashboard"))
            request_id = latest_request["id"]

        if not amount or amount <= 0:
            conn.close()
            flash("Enter a valid payment amount.", "warning")
            return redirect(url_for("user_bp.user_dashboard"))

        owner_share = round(amount * 0.5, 2)
        admin_share = round(amount * 0.3, 2)
        worker_share = round(amount * 0.2, 2)

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO payments (request_id, total, owner_share, admin_share, worker_share, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (request_id, amount, owner_share, admin_share, worker_share))
        conn.commit()
        conn.close()

        flash(f"Payment recorded successfully via {gateway.title()}.", "success")
    except Exception as e:
        print(f"Payment error: {e}")
        flash("Payment could not be recorded right now.", "danger")

    return redirect(url_for("user_bp.user_dashboard"))


@user_bp.route("/complaints")
def user_complaints():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    data = _get_citizen_dashboard_data(session["user_id"], cursor)
    data["recent_complaints"] = _get_user_complaints(session["user_id"], cursor, limit=None)
    conn.close()

    return render_template("dashboard/user_complaints.html", **data, citizen_page="complaints")


@user_bp.route("/requests")
def user_requests_page():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    data = _get_citizen_dashboard_data(session["user_id"], cursor)
    conn.close()

    return render_template("dashboard/user_requests.html", **data, citizen_page="requests")


@user_bp.route("/payments")
def user_payments_page():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    data = _get_citizen_dashboard_data(session["user_id"], cursor)
    conn.close()

    total_paid = sum(float(payment.get("total") or 0) for payment in data["payment_history"])
    pending_due = sum(float(req.get("amount") or 0) for req in data["user_requests"] if (req.get("status") or "").lower() != "completed")

    return render_template(
        "dashboard/user_payments.html",
        **data,
        total_paid=total_paid,
        pending_due=pending_due,
        citizen_page="payments"
    )


@user_bp.route("/profile")
def user_profile_page():
    if "user_id" not in session:
        return redirect(url_for("user_bp.user_login"))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    data = _get_citizen_dashboard_data(session["user_id"], cursor)
    conn.close()

    request_stats = {
        "total_requests": len(data["user_requests"]),
        "pending_requests": sum(1 for req in data["user_requests"] if (req.get("status") or "").lower() == "pending"),
        "in_progress_requests": sum(1 for req in data["user_requests"] if (req.get("status") or "").lower() == "in_progress"),
        "completed_requests": sum(1 for req in data["user_requests"] if (req.get("status") or "").lower() == "completed"),
    }

    return render_template(
        "dashboard/user_profile.html",
        **data,
        request_stats=request_stats,
        citizen_page="profile"
    )

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
