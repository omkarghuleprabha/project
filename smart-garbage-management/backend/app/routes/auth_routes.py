from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import os

# 1. DEFINE THE BLUEPRINT
auth_bp = Blueprint('auth_bp', __name__)

# --- 🛠️ DATABASE HELPER ---
def get_dynamic_db():
    """Connects to Database using SQLAlchemy URI from Config (Aiven Cloud)"""
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI')
    # Automatically handles SSL and cloud parameters via URI
    return mysql.connector.connect(option_files=None, uri=db_uri)

# --- 🟢 REGISTRATION ROUTE ---
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        role = request.form.get('role')
        
        # Numeric IDs matching your actual database table structure
        state_id = request.form.get('state_id')
        dist_id = request.form.get('district_id')
        tal_id = request.form.get('taluka_id')
        vil_id = request.form.get('village_id')

        if not name or not email or not password:
            flash("All fields are required!", "danger")
            return redirect(url_for('auth_bp.register'))

        hashed_pw = generate_password_hash(password)
        
        try:
            conn = get_dynamic_db()
            cursor = conn.cursor(dictionary=True)

            role_to_table = {
                'district_admin': 'district_admins',
                'admin': 'taluka_admins',
                'worker': 'village_workers',
                'user': 'users'
            }
            target_table = role_to_table.get(role, 'users')

            # 🔴 DUPLICATE CHECK
            cursor.execute(f"SELECT id FROM {target_table} WHERE email=%s OR phone=%s", (email, phone))
            if cursor.fetchone():
                flash("Email or Mobile already exists!", "danger")
                return redirect(url_for('auth_bp.register'))

            # 🔹 INSERT LOGIC (Structured to match your table columns)
            if role == 'district_admin':
                query = f"INSERT INTO {target_table} (name, email, phone, password, district_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, dist_id))
            elif role == 'admin':
                query = f"INSERT INTO {target_table} (name, email, phone, password, taluka_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, tal_id))
            elif role == 'worker':
                query = f"INSERT INTO {target_table} (name, email, phone, password, village_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, vil_id))
            else:
                # Regular User
                query = f"INSERT INTO {target_table} (name, email, phone, password, role, state_id, district_id, taluka_id, village_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, 'user', state_id, dist_id, tal_id, vil_id))

            conn.commit()
            flash("Registration Successful! Please login.", "success")
            return redirect(url_for('auth_bp.login'))

        except Exception as e:
            print(f"Error: {e}")
            flash(f"Registration failed: {str(e)}", "danger")
        finally:
            if 'conn' in locals() and conn.is_connected():
                conn.close()

    # GET logic: Initial Load of States
    states = []
    try:
        conn = get_dynamic_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM states ORDER BY name ASC")
        states = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"Fetch Error: {e}")

    # Fallback: If DB is empty or connection fails, ensure Maharashtra is visible
    if not states:
        states = [{'id': 1, 'name': 'Maharashtra'}]
        
    return render_template('auth/register.html', states=states)


# --- 🟡 API ROUTES FOR DYNAMIC DROPDOWNS (Optimized) ---

@auth_bp.route('/get_districts/<state_id>')
def get_districts(state_id):
    try:
        conn = get_dynamic_db()
        cursor = conn.cursor(dictionary=True)
        # %s पायथन आपोआप डेटा टाईप हँडल करेल
        cursor.execute("SELECT id, name FROM districts WHERE state_id = %s ORDER BY name ASC", (state_id,))
        data = cursor.fetchall()
        conn.close()
        return jsonify(data)
    except Exception as e:
        print(f"Districts Error: {e}")
        return jsonify([])

@auth_bp.route('/get_talukas/<district_id>')
def get_talukas(district_id):
    try:
        conn = get_dynamic_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM talukas WHERE district_id = %s ORDER BY name ASC", (district_id,))
        data = cursor.fetchall()
        conn.close()
        return jsonify(data)
    except Exception as e:
        print(f"Talukas Error: {e}")
        return jsonify([])

@auth_bp.route('/get_villages/<taluka_id>')
def get_villages(taluka_id):
    try:
        conn = get_dynamic_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM villages WHERE taluka_id = %s ORDER BY name ASC", (taluka_id,))
        data = cursor.fetchall()
        conn.close()
        return jsonify(data)
    except Exception as e:
        print(f"Villages Error: {e}")
        return jsonify([])

# --- 🔵 LOGIN ROUTE ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')  # Email or Phone
        password = request.form.get('password')
        form_role = request.form.get('role') 

        role_to_table = {
            'district_admin': 'district_admins',
            'admin': 'taluka_admins',
            'worker': 'village_workers',
            'user': 'users'
        }
        table_name = role_to_table.get(form_role, 'users')
        
        try:
            conn = get_dynamic_db()
            cursor = conn.cursor(dictionary=True)
            query = f"SELECT * FROM {table_name} WHERE email = %s OR phone = %s"
            cursor.execute(query, (identifier, identifier))
            user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                session.clear()
                session['user_id'] = user['id']
                session['user_name'] = user['name']
                session['role'] = form_role
                
                flash(f"Welcome back, {user['name']}!", "success")
                
                redirect_map = {
                    'district_admin': 'auth_bp.district_dashboard',
                    'admin': 'auth_bp.taluka_dashboard',
                    'worker': 'auth_bp.worker_dashboard'
                }
                return redirect(url_for(redirect_map.get(form_role, 'auth_bp.citizen_dashboard')))
            else:
                flash("Invalid credentials for the selected role.", "danger")
        except Exception as e:
            print(f"Login Error: {e}")
            flash("Login failed. Please try again.", "danger")
        finally:
            if 'conn' in locals() and conn.is_connected():
                conn.close()
                
    return render_template('auth/login.html')


# --- 🔴 LOGOUT ROUTE ---
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("Successfully logged out.", "success")
    return redirect(url_for('auth_bp.login'))


# --- 🟡 DASHBOARD ROUTES ---
@auth_bp.route('/citizen-dashboard')
def citizen_dashboard():
    if session.get('role') != 'user': return redirect(url_for('auth_bp.login'))
    return render_template('dashboard/citizen_dash.html')

@auth_bp.route('/district-dashboard')
def district_dashboard():
    if session.get('role') != 'district_admin': return redirect(url_for('auth_bp.login'))
    return render_template('dashboard/district_admin.html')

@auth_bp.route('/taluka-dashboard')
def taluka_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('auth_bp.login'))
    return render_template('dashboard/taluka_admin.html')

@auth_bp.route('/worker-dashboard')
def worker_dashboard():
    if session.get('role') != 'worker': return redirect(url_for('auth_bp.login'))
    return render_template('dashboard/worker_dash.html')