from flask import Blueprint, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from app.utils.db import get_db
from app.utils.complaints import ensure_complaint_workflow_columns, get_complaint_columns
import os
import uuid

complaint_bp = Blueprint('complaint_bp', __name__, url_prefix='/complaint')


def _get_redirect_target():
    next_page = (request.form.get('next_page') or '').strip()
    if next_page.startswith('/'):
        return next_page

    referrer = (request.referrer or '').strip()
    if referrer.startswith(request.host_url):
        return referrer

    return url_for('user_bp.user_complaints')


def _resolve_complaint_image_column(cursor):
    for column_name in ('photo_path', 'garbage_img'):
        cursor.execute(f"SHOW COLUMNS FROM complaints LIKE '{column_name}'")
        if cursor.fetchone():
            return column_name
    return None


@complaint_bp.route('/add', methods=['POST'])
def add_complaint():
    # 🔐 Check login
    if 'user_id' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('auth_bp.login'))

    redirect_target = _get_redirect_target()

    # 📥 Get form data
    title = (request.form.get('title') or '').strip()
    description = (request.form.get('description') or '').strip()
    district = (request.form.get('district') or '').strip()
    taluka = (request.form.get('taluka') or '').strip()
    village = (request.form.get('village') or '').strip()
    priority = (request.form.get('priority') or 'Normal').strip() or 'Normal'
    file = request.files.get('garbage_img')

    # ✅ Validation
    if not all([title, description, district, taluka, village]):
        flash("Title, description, district, taluka, and village are required.", "danger")
        return redirect(redirect_target)

    # 📸 File Upload Handling
    unique_filename = None
    if file and file.filename:
        try:
            filename = secure_filename(file.filename)

            if '.' in filename:
                ext = filename.rsplit('.', 1)[1].lower()
            else:
                ext = 'jpg'

            unique_filename = f"{uuid.uuid4().hex}.{ext}"

            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'complaints')

            # create folder if not exists
            os.makedirs(upload_folder, exist_ok=True)

            file.save(os.path.join(upload_folder, unique_filename))

        except Exception as e:
            flash(f"File upload error: {str(e)}", "danger")
            return redirect(redirect_target)

    # 🗄️ Save to DB
    conn = None
    cursor = None
    try:
        conn = get_db()
        if not conn:
            flash("Database connection failed. Please try again.", "danger")
            return redirect(redirect_target)

        cursor = conn.cursor()
        ensure_complaint_workflow_columns(cursor)
        complaint_columns = get_complaint_columns(cursor)

        image_column = _resolve_complaint_image_column(cursor)
        columns = ['user_id', 'title', 'description', 'district', 'taluka', 'village']
        values = [session['user_id'], title, description, district, taluka, village]

        if image_column:
            columns.append(image_column)
            values.append(unique_filename)

        columns.extend(['priority', 'status', 'created_at'])
        placeholders = ['%s'] * len(values) + ['%s', '%s', 'NOW()']

        if 'updated_at' in complaint_columns:
            columns.append('updated_at')
            placeholders.append('NOW()')

        cursor.execute(f"""
            INSERT INTO complaints
                ({', '.join(columns)})
            VALUES
                ({', '.join(placeholders)})
        """, tuple(values + [priority, 'Pending']))
        conn.commit()
        flash("Complaint submitted successfully.", "success")
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print("DB ERROR:", e)
        flash("Complaint could not be saved right now. Please try again.", "danger")
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    return redirect(redirect_target)
