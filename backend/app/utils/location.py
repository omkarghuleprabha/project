from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.db import get_db

auth_bp = Blueprint('auth_bp', __name__)

# Route to load the File Complaint Page
@auth_bp.route('/file-complaint', methods=['GET'])
def file_complaint_page():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    # Fetch states to populate the first dropdown
    cursor.execute("SELECT id, name FROM states ORDER BY name ASC")
    states = cursor.fetchall()
    conn.close()
    return render_template('auth/file_complaint.html', states=states)

# API: Get Districts
@auth_bp.route('/get_districts/<int:state_id>')
def get_districts(state_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM districts WHERE state_id = %s ORDER BY name ASC", (state_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

# API: Get Talukas
@auth_bp.route('/get_talukas/<int:district_id>')
def get_talukas(district_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM talukas WHERE district_id = %s ORDER BY name ASC", (district_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

# API: Get Villages
@auth_bp.route('/get_villages/<int:taluka_id>')
def get_villages(taluka_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM villages WHERE taluka_id = %s ORDER BY name ASC", (taluka_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)