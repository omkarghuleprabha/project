import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from datetime import datetime
from .. import db 

complaint_bp = Blueprint('complaint_bp', __name__)

@complaint_bp.route('/add', methods=['POST'])
def add_complaint():
    if 'user_id' not in session:
        flash("Please login first", "warning")
        return redirect(url_for('auth_bp.login'))

    # 1. Capture Form Data (Matching your HTML 'name' attributes)
    title = request.form.get('title')
    description = request.form.get('description')
    district = request.form.get('district')
    taluka = request.form.get('taluka')
    village = request.form.get('village')
    priority = request.form.get('priority')
    file = request.files.get('garbage_img') # Match name="garbage_img" from HTML

    if not all([title, description, district, taluka, village, file]):
        flash("Please fill in all required fields and upload a photo.", "danger")
        return redirect(url_for('auth_bp.citizen_dashboard'))

    # 2. Handle File Upload Professionally
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'jpg'
    unique_filename = f"{uuid.uuid4().hex}.{ext}" # Use UUID to prevent overwriting
    
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'complaints')
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
        
    file.save(os.path.join(upload_folder, unique_filename))

    # 3. Save to Database (Matching your Model columns)
    new_complaint = 'Complaint'(
        ticket_id=f"TKT-{uuid.uuid4().hex[:8].upper()}", # Automatic Ticket Generation
        citizen_id=session.get('user_id'),
        title=title,
        description=description,
        district=district,
        taluka=taluka,
        village=village,
        image_path=unique_filename,
        priority=priority,
        status='pending'
    )

    try:
        db.session.add(new_complaint)
        db.session.commit()
        flash("Complaint registered successfully! Your Ticket ID is: " + new_complaint.ticket_id, "success")
    except Exception as e:
        db.session.rollback()
        print(f"Database Error: {e}")
        flash("Could not save to database. Please check your model fields.", "danger")

    return redirect(url_for('auth_bp.citizen_dashboard'))