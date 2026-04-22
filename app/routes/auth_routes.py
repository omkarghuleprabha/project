from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.db import get_db
from app.utils.auth import build_auth_payload, make_login_response, make_logout_response

auth_bp = Blueprint('auth_bp', __name__)

# Helper to map roles to table names
ROLE_MAP = {
    'district_admin': 'district_admins',
    'admin': 'taluka_admins',
    'worker': 'village_workers',
    'user': 'users'
}


def get_citizen_context(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT id, name, email, phone, district_id, taluka_id, village_id, created_at
            FROM users
            WHERE id = %s
        """, (user_id,))
        user_profile = cursor.fetchone() or {}

        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END), 0) AS in_progress,
                COALESCE(SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END), 0) AS completed
            FROM complaints
            WHERE user_id = %s
        """, (user_id,))
        stats = cursor.fetchone() or {
            'total': 0,
            'pending': 0,
            'in_progress': 0,
            'completed': 0,
        }

        cursor.execute("""
            SELECT id, title, district, taluka, village, priority, status, created_at
            FROM complaints
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """, (user_id,))
        complaints = cursor.fetchall()

        complaint_rows = []
        for comp in complaints:
            raw_status = (comp.get('status') or 'Pending').strip()
            status_key = raw_status.lower().replace(' ', '-')
            progress_map = {
                'pending': 25,
                'in-progress': 70,
                'completed': 100
            }
            bar_map = {
                'pending': 'bg-warning',
                'in-progress': 'bg-info',
                'completed': 'bg-success'
            }
            complaint_rows.append({
                'id': comp['id'],
                'ticket_id': f"CMP-{comp['id']:04d}",
                'title': comp.get('title') or 'Complaint',
                'district': comp.get('district') or 'Unknown District',
                'village': comp.get('village') or 'Unknown Village',
                'taluka': comp.get('taluka') or 'Unknown Taluka',
                'priority': comp.get('priority') or 'Normal',
                'status_text': raw_status,
                'status_class': status_key,
                'progress': progress_map.get(status_key, 25),
                'bar_color': bar_map.get(status_key, 'bg-secondary'),
                'date': comp['created_at'].strftime('%d %b %Y %I:%M %p') if comp.get('created_at') else 'N/A'
            })

        cursor.execute("""
            SELECT id, garbage_type, status, amount, created_at
            FROM requests
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 20
        """, (user_id,))
        pickup_requests = cursor.fetchall()

        cursor.execute("""
            SELECT
                p.id,
                p.request_id,
                p.total,
                p.owner_share,
                p.admin_share,
                p.worker_share,
                p.created_at,
                r.garbage_type
            FROM payments p
            INNER JOIN requests r ON r.id = p.request_id
            WHERE r.user_id = %s
            ORDER BY p.created_at DESC, p.id DESC
            LIMIT 20
        """, (user_id,))
        payments = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching citizen data: {e}")
        user_profile = {}
        stats = {'total': 0, 'pending': 0, 'in_progress': 0, 'completed': 0}
        complaint_rows = []
        pickup_requests = []
        payments = []
    finally:
        conn.close()

    return {
        'user_profile': user_profile,
        'stats': stats,
        'recent_complaints': complaint_rows[:5],
        'complaints': complaint_rows,
        'pickup_requests': pickup_requests,
        'payments': payments,
        'recent_payments': payments[:5],
        'recent_pickup_requests': pickup_requests[:5],
    }


def require_user_role():
    if session.get('role') == 'user' and session.get('user_id'):
        return None
    next_path = request.path
    return redirect(url_for('auth_bp.login', next=next_path))


def require_worker_role():
    if session.get('role') == 'worker' and session.get('worker_id'):
        return None
    next_path = request.path
    return redirect(url_for('auth_bp.login', next=next_path))


def redirect_worker_dashboard():
    next_section = (request.form.get('next_section') or '').strip()
    if next_section.startswith('#'):
        return redirect(f"{url_for('auth_bp.worker_dashboard')}{next_section}")
    return redirect(url_for('auth_bp.worker_dashboard'))


def get_worker_context(worker_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT vw.id, vw.name, vw.email, vw.phone, vw.vehicle_no, vw.status, vw.created_at, v.name AS village_name
            FROM village_workers vw
            LEFT JOIN villages v ON v.id = vw.village_id
            WHERE vw.id = %s
        """, (worker_id,))
        worker_profile = cursor.fetchone() or {}

        cursor.execute("""
            SELECT id, worker_id, location_name, description, status, priority, assigned_at
            FROM tasks
            WHERE worker_id = %s
            ORDER BY assigned_at DESC, id DESC
        """, (worker_id,))
        tasks = cursor.fetchall()

        started_ids = set(session.get('worker_started_tasks', []))
        active_tasks = []
        completed_tasks = []

        for task in tasks:
            priority = (task.get('priority') or 'medium').lower()
            status = (task.get('status') or 'pending').strip().lower()
            is_started = task['id'] in started_ids or status in {'in_progress', 'in progress', 'started'}
            task_view = {
                'id': task['id'],
                'ticket_id': f"TASK-{task['id']:03d}",
                'location_name': task.get('location_name') or 'Assigned Location',
                'description': task.get('description') or 'No description provided.',
                'priority': priority,
                'priority_label': f"{priority.upper()} PRIORITY",
                'assigned_at_text': task['assigned_at'].strftime('%d %b %Y %I:%M %p') if task.get('assigned_at') else 'N/A',
                'is_started': is_started,
                'status': status,
            }
            if status == 'completed':
                completed_tasks.append(task_view)
            else:
                active_tasks.append(task_view)

        # Drop stale started-task flags after tasks are completed or removed.
        active_task_ids = {task['id'] for task in active_tasks}
        cleaned_started_ids = [task_id for task_id in started_ids if task_id in active_task_ids]
        if cleaned_started_ids != session.get('worker_started_tasks', []):
            session['worker_started_tasks'] = cleaned_started_ids

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS worker_equipment_requests (
                id INT NOT NULL AUTO_INCREMENT,
                worker_id INT DEFAULT NULL,
                item_type VARCHAR(100) DEFAULT NULL,
                quantity INT DEFAULT NULL,
                priority VARCHAR(20) DEFAULT NULL,
                reason TEXT,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id)
            )
        """)

        cursor.execute("""
            SELECT id, item_type, quantity, priority, reason, created_at
            FROM worker_equipment_requests
            WHERE worker_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 10
        """, (worker_id,))
        equipment_requests = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching worker data: {e}")
        worker_profile = {}
        active_tasks = []
        completed_tasks = []
        equipment_requests = []
    finally:
        conn.close()

    attendance_state = session.get('worker_attendance_state', 'checked_out')
    attendance_since = session.get('worker_attendance_since')

    return {
        'worker_profile': worker_profile,
        'active_tasks': active_tasks,
        'recent_active_tasks': active_tasks[:3],
        'completed_tasks': completed_tasks,
        'recent_completed_tasks': completed_tasks[:5],
        'equipment_requests': equipment_requests,
        'recent_equipment_requests': equipment_requests[:5],
        'worker_stats': {
            'assigned': len(active_tasks) + len(completed_tasks),
            'pending': len([task for task in active_tasks if not task['is_started']]),
            'in_progress': len([task for task in active_tasks if task['is_started']]),
            'completed': len(completed_tasks),
            'rating': 4.5,
        },
        'attendance_state': attendance_state,
        'attendance_since': attendance_since,
        'checklist_items': [
            {'id': 'route_1', 'label': 'House #1 - Akole Main Road', 'done': True},
            {'id': 'route_2', 'label': 'House #2 - School Lane', 'done': True},
            {'id': 'route_3', 'label': 'House #3 - Market Street', 'done': False},
            {'id': 'route_4', 'label': 'Shop #1 - Main Bazaar', 'done': False},
            {'id': 'route_5', 'label': 'Shop #2 - Community Center', 'done': False},
        ],
    }

# --- 🟢 REGISTRATION ROUTE ---
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        
        # Location IDs
        dist_id = request.form.get('district_id')
        tal_id = request.form.get('taluka_id')
        vil_id = request.form.get('village_id')

        if not name or not email or not password:
            flash("Name, Email, and Password are required!", "danger")
            return redirect(url_for('auth_bp.register'))

        table_name = ROLE_MAP.get(role, 'users')
        hashed_pw = generate_password_hash(password)
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        try:
            # 🔴 DUPLICATE CHECK (Dynamic)
            check_query = f"SELECT id FROM {table_name} WHERE email=%s OR phone=%s"
            cursor.execute(check_query, (email, phone))
            if cursor.fetchone():
                flash(f"User with this Email or Mobile already exists in {role.replace('_', ' ').title()}.", "danger")
                return redirect(url_for('auth_bp.register'))

            # 🔹 INSERT LOGIC
            if role == 'district_admin':
                query = "INSERT INTO district_admins (name, email, phone, password, district_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, dist_id))
            elif role == 'admin':
                query = "INSERT INTO taluka_admins (name, email, phone, password, taluka_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, tal_id))
            elif role == 'worker':
                query = "INSERT INTO village_workers (name, email, phone, password, village_id) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, vil_id))
            else:
                query = "INSERT INTO users (name, email, phone, password, role, village_id) VALUES (%s, %s, %s, %s, %s, %s)"
                cursor.execute(query, (name, email, phone, hashed_pw, 'user', vil_id))

            conn.commit()
            flash("Registration Successful! Please login.", "success")
            return redirect(url_for('auth_bp.login'))

        except Exception as e:
            conn.rollback()
            print(f"Database Error: {e}")
            flash("Registration failed due to a server error.", "danger")
        finally:
            conn.close()

    # GET Request: Fetch states for the dropdown
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM states ORDER BY name ASC")
    states = cursor.fetchall()
    conn.close()
    return render_template('auth/register.html', states=states)


# --- 🔵 LOGIN ROUTE ---
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next', '').strip()
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        password = request.form.get('password')
        form_role = request.form.get('role') 

        table_name = ROLE_MAP.get(form_role, 'users')
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        try:
            # Using f-string for table name is okay here since it's mapped from a hardcoded dict
            query = f"SELECT * FROM {table_name} WHERE email = %s OR phone = %s"
            cursor.execute(query, (identifier, identifier))
            user = cursor.fetchone()

            if user and check_password_hash(user['password'], password):
                auth_payload = build_auth_payload(user, form_role)
                
                flash(f"Welcome back, {user['name']}!", "success")
                
                # Redirect Map
                redirect_map = {
                    'district_admin': 'auth_bp.district_dashboard',
                    'admin': 'auth_bp.taluka_dashboard',
                    'worker': 'auth_bp.worker_dashboard',
                    'user': 'auth_bp.citizen_dashboard'
                }
                if form_role == 'user' and next_url.startswith('/auth/citizen'):
                    return make_login_response(next_url, auth_payload, use_url=True)
                return make_login_response(redirect_map.get(form_role, 'auth_bp.citizen_dashboard'), auth_payload)
            
            flash("Invalid credentials for the selected role.", "danger")
        except Exception as e:
            print(f"Login Error: {e}")
            flash("An error occurred during login.", "danger")
        finally:
            conn.close()
            
    return render_template('auth/login.html')

# --- 🔴 LOGOUT ROUTE ---
@auth_bp.route('/logout')
def logout():
    flash("Successfully logged out.", "success")
    return make_logout_response('auth_bp.login')

# --- 🟡 DASHBOARD ROUTES (Unified Check) ---

@auth_bp.route('/citizen-dashboard')
def citizen_dashboard():
    auth_redirect = require_user_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/citizen_dash.html',
        active_page='dashboard',
        **get_citizen_context(session.get('user_id'))
    )


@auth_bp.route('/citizen/file-complaint')
def citizen_file_complaint():
    auth_redirect = require_user_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/citizen_file_complaint.html',
        active_page='file_complaint',
        **get_citizen_context(session.get('user_id'))
    )


@auth_bp.route('/citizen/complaints')
def citizen_complaints():
    auth_redirect = require_user_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/citizen_complaints.html',
        active_page='complaints',
        **get_citizen_context(session.get('user_id'))
    )


@auth_bp.route('/citizen/pickup')
def citizen_pickup():
    auth_redirect = require_user_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/citizen_pickup.html',
        active_page='pickup',
        **get_citizen_context(session.get('user_id'))
    )


@auth_bp.route('/citizen/payments')
def citizen_payments():
    auth_redirect = require_user_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/citizen_payments.html',
        active_page='payments',
        **get_citizen_context(session.get('user_id'))
    )


@auth_bp.route('/citizen/transactions')
def citizen_transactions():
    auth_redirect = require_user_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/citizen_transactions.html',
        active_page='transactions',
        **get_citizen_context(session.get('user_id'))
    )


@auth_bp.route('/citizen/profile')
def citizen_profile():
    auth_redirect = require_user_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/citizen_profile.html',
        active_page='profile',
        **get_citizen_context(session.get('user_id'))
    )

@auth_bp.route('/district-dashboard')
def district_dashboard():
    if session.get('role') != 'district_admin':
        return redirect(url_for('auth_bp.login'))
    return render_template('dashboard/district_admin.html')

@auth_bp.route('/taluka-dashboard')
def taluka_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('auth_bp.login'))
    return render_template('dashboard/taluka_admin.html')

@auth_bp.route('/worker-dashboard')
def worker_dashboard():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect
    return render_template(
        'dashboard/worker_dash.html',
        active_page='dashboard',
        **get_worker_context(session.get('worker_id'))
    )


@auth_bp.route('/api/worker/stats')
def worker_stats_api():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return jsonify({'message': 'Login required', 'error': 'unauthorized'}), 401

    context = get_worker_context(session.get('worker_id'))
    stats = context.get('worker_stats', {})

    # Enhanced stats for advanced dashboard
    worker_id = session.get('worker_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get today's earnings from requests table
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as today_earnings
            FROM requests
            WHERE worker_id = %s AND status = 'completed' AND DATE(created_at) = CURDATE()
        """, (worker_id,))
        today_earnings = cursor.fetchone()['today_earnings']

        # Get monthly earnings from requests table
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as monthly_earnings
            FROM requests
            WHERE worker_id = %s AND status = 'completed' AND MONTH(created_at) = MONTH(CURDATE()) AND YEAR(created_at) = YEAR(CURDATE())
        """, (worker_id,))
        monthly_earnings = cursor.fetchone()['monthly_earnings']

        # Calculate efficiency (completed tasks / total assigned tasks * 100)
        total_assigned = stats.get('assigned', 0)
        completed = stats.get('completed', 0)
        efficiency = (completed / total_assigned * 100) if total_assigned > 0 else 0

        # Get completed tasks today from requests table
        cursor.execute("""
            SELECT COUNT(*) as completed_today
            FROM requests
            WHERE worker_id = %s AND status = 'completed' AND DATE(created_at) = CURDATE()
        """, (worker_id,))
        completed_today = cursor.fetchone()['completed_today']

    except Exception as e:
        print(f"Error fetching enhanced stats: {e}")
        today_earnings = monthly_earnings = efficiency = completed_today = 0
    finally:
        conn.close()

    return jsonify({
        'assigned': stats.get('assigned', 0),
        'pending': stats.get('pending', 0),
        'in_progress': stats.get('in_progress', 0),
        'completed': stats.get('completed', 0),
        'rating': stats.get('rating', 0),
        'attendance_state': context.get('attendance_state', 'checked_out'),
        'attendance_since': context.get('attendance_since'),
        'today_earnings': float(today_earnings),
        'monthly_earnings': float(monthly_earnings),
        'efficiency': round(efficiency, 1),
        'completed_today': completed_today
    })


@auth_bp.route('/api/worker/tasks')
def worker_tasks_api():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return jsonify({'message': 'Login required', 'error': 'unauthorized'}), 401

    context = get_worker_context(session.get('worker_id'))
    return jsonify({
        'active_tasks': context.get('active_tasks', []),
        'completed_tasks': context.get('completed_tasks', []),
    })


@auth_bp.route('/worker/check-in', methods=['POST'])
def worker_check_in():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect
    session['worker_attendance_state'] = 'checked_in'
    session['worker_attendance_since'] = datetime.now().strftime('Checked in at %I:%M %p')
    flash("Attendance marked successfully.", "success")
    return redirect_worker_dashboard()


@auth_bp.route('/worker/check-out', methods=['POST'])
def worker_check_out():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect
    session['worker_attendance_state'] = 'checked_out'
    session['worker_attendance_since'] = datetime.now().strftime('Checked out at %I:%M %p')
    flash("You have checked out for the day.", "info")
    return redirect_worker_dashboard()


@auth_bp.route('/worker/task/<int:task_id>/start', methods=['POST'])
def worker_start_task(task_id):
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect

    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, status FROM tasks WHERE id = %s AND worker_id = %s",
            (task_id, session.get('user_id'))
        )
        task = cursor.fetchone()
        if not task:
            flash("Task not found for this worker.", "danger")
            return redirect_worker_dashboard()

        if (task.get('status') or '').strip().lower() == 'completed':
            flash(f"Task #{task_id} is already completed.", "info")
            return redirect_worker_dashboard()

        started = session.get('worker_started_tasks', [])
        if task_id not in started:
            started.append(task_id)
            session['worker_started_tasks'] = started
            flash(f"Task #{task_id} is now in progress.", "success")
        else:
            flash(f"Task #{task_id} is already marked in progress.", "info")
    except Exception as e:
        print(f"Worker Task Start Error: {e}")
        flash("Unable to start task right now.", "danger")
    finally:
        conn.close()

    return redirect_worker_dashboard()


@auth_bp.route('/worker/task/<int:task_id>/complete', methods=['POST'])
def worker_complete_task(task_id):
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE tasks SET status='completed' WHERE id = %s AND worker_id = %s", (task_id, session.get('user_id')))
        conn.commit()
        started = session.get('worker_started_tasks', [])
        session['worker_started_tasks'] = [item for item in started if item != task_id]
        flash(f"Task #{task_id} marked as completed.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Worker Task Complete Error: {e}")
        flash("Unable to complete task right now.", "danger")
    finally:
        conn.close()

    return redirect_worker_dashboard()


@auth_bp.route('/worker/equipment-request', methods=['POST'])
def worker_equipment_request():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect

    item_type = request.form.get('item_type', '').strip()
    quantity = request.form.get('quantity', '').strip()
    priority = request.form.get('priority', 'Normal').strip()
    reason = request.form.get('reason', '').strip()

    if not item_type or not quantity:
        flash("Please fill in the equipment request details.", "danger")
        return redirect_worker_dashboard()

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS worker_equipment_requests (
                id INT NOT NULL AUTO_INCREMENT,
                worker_id INT DEFAULT NULL,
                item_type VARCHAR(100) DEFAULT NULL,
                quantity INT DEFAULT NULL,
                priority VARCHAR(20) DEFAULT NULL,
                reason TEXT,
                created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id)
            )
        """)
        cursor.execute("""
            INSERT INTO worker_equipment_requests (worker_id, item_type, quantity, priority, reason)
            VALUES (%s, %s, %s, %s, %s)
        """, (session.get('user_id'), item_type, int(quantity), priority, reason))
        conn.commit()
        flash("Equipment request submitted successfully.", "success")
    except Exception as e:
        conn.rollback()
        print(f"Equipment Request Error: {e}")
        flash("Unable to submit equipment request.", "danger")
    finally:
        conn.close()

    return redirect_worker_dashboard()

# --- 🟡 API ROUTES FOR DROPDOWNS ---

@auth_bp.route('/get_districts/<int:state_id>')
def get_districts(state_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM districts WHERE state_id = %s ORDER BY name ASC", (state_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

@auth_bp.route('/get_talukas/<int:district_id>')
def get_talukas(district_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM talukas WHERE district_id = %s ORDER BY name ASC", (district_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)

@auth_bp.route('/get_villages/<int:taluka_id>')
def get_villages(taluka_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name FROM villages WHERE taluka_id = %s ORDER BY name ASC", (taluka_id,))
    data = cursor.fetchall()
    conn.close()
    return jsonify(data)


# --- 🚛 WORKER DASHBOARD ROUTES ---

@auth_bp.route('/worker/earnings')
def worker_earnings():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect

    worker_id = session.get('worker_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get earnings data from requests table
        cursor.execute("""
            SELECT
                DATE(created_at) as date,
                COUNT(*) as tasks_completed,
                COALESCE(SUM(amount), 0) as daily_earnings
            FROM requests
            WHERE worker_id = %s AND status = 'completed'
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 30
        """, (worker_id,))
        earnings_data = cursor.fetchall()

        # Get total earnings
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as total_earnings
            FROM requests
            WHERE worker_id = %s AND status = 'completed'
        """, (worker_id,))
        total_earnings = cursor.fetchone()['total_earnings']

        # Get pending payments (requests that are completed but not paid yet)
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) as pending_payments
            FROM requests
            WHERE worker_id = %s AND status = 'completed'
        """, (worker_id,))
        pending_payments = cursor.fetchone()['pending_payments']

    except Exception as e:
        print(f"Earnings data error: {e}")
        earnings_data = []
        total_earnings = 0
        pending_payments = 0
    finally:
        conn.close()

    return render_template('worker/earnings.html',
                         earnings_data=earnings_data,
                         total_earnings=total_earnings,
                         pending_payments=pending_payments,
                         active_page='earnings')


@auth_bp.route('/worker/requests')
def worker_requests():
    auth_redirect = require_worker_role()
    if auth_redirect:
        return auth_redirect

    worker_id = session.get('worker_id')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get assigned requests/tasks
        cursor.execute("""
            SELECT
                t.id,
                t.location_name,
                t.description,
                t.status,
                t.priority,
                t.assigned_at,
                t.created_at
            FROM tasks t
            WHERE t.worker_id = %s
            ORDER BY
                CASE
                    WHEN t.status = 'pending' THEN 1
                    WHEN t.status = 'in_progress' THEN 2
                    WHEN t.status = 'completed' THEN 3
                END,
                t.priority DESC,
                t.assigned_at DESC
        """, (worker_id,))
        requests_data = cursor.fetchall()

    except Exception as e:
        print(f"Requests data error: {e}")
        requests_data = []
    finally:
        conn.close()

    return render_template('worker/requests.html',
                         requests_data=requests_data,
                         active_page='requests')
