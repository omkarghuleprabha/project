from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from app import db
from app.models.user_model import User, Complaint, Task
# Note: Assuming you have State, District, Taluka, and Village models defined 
# in your models folder as well.

main_bp = Blueprint('main_bp', __name__)

# --- 🚀 UPDATED: UNIFIED DASHBOARD TRAFFIC CONTROLLER (SQLAlchemy) ---
@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth_bp.login'))

    role = session.get('role')
    user_id = session.get('user_id')
    user_name = session.get('user_name')
    
    data = {"name": user_name, "role": role}

    try:
        if role == 'district_admin':
            dist_id = session.get('district_id')
            # Using SQLAlchemy count instead of Raw SQL
            # Note: Requires a 'Taluka' model to be defined
            from app.models.user_model import Taluka # Import locally if needed
            data['total_talukas'] = Taluka.query.filter_by(district_id=dist_id).count() if dist_id else 0
            return render_template('dashboard/district_admin.html', data=data)

        elif role == 'admin': # Taluka Admin
            tal_id = session.get('taluka_id')
            if tal_id:
                # Query workers belonging to villages within the selected taluka
                from app.models.user_model import Village, VillageWorker
                workers = db.session.query(VillageWorker).join(Village).filter(Village.taluka_id == tal_id).all()
                data['workers'] = workers
            else:
                data['workers'] = []
            return render_template('dashboard/taluka_admin.html', data=data)

        elif role == 'worker':
            # Simplified task fetching
            data['tasks'] = Task.query.filter_by(worker_id=user_id).filter(Task.status != 'completed').all()
            return render_template('dashboard/worker_dash.html', data=data)

        else: # Citizen / User
            # Simplified complaint fetching
            data['my_complaints'] = Complaint.query.filter_by(user_id=user_id).all()
            return render_template('dashboard/citizen_dash.html', data=data)

    except Exception as e:
        print(f"Dashboard Error: {e}")
        return f"Dashboard Error: {str(e)}", 500

# --- 🏠 HOME ROUTE ---
@main_bp.route('/')
def home():
    try:
        u_count = User.query.count()
    except Exception as e:
        print(f"Stats Retrieval Error: {e}")
        u_count = 120 # Fallback demo value
    
    return render_template('main/home.html', user_count=u_count)

# --- ℹ️ ABOUT & SERVICES ---
@main_bp.route('/about')
def about():
    return render_template('main/about.html')

@main_bp.route('/services')
def services():
    return render_template('main/services.html')

# --- 🎯 PORTAL SELECTION ---
@main_bp.route('/portal-selection')
def portal_selection():
    from app.models.user_model import State
    all_states = State.query.order_by(State.name.asc()).all()
    return render_template('main/portal_selection.html', states=all_states)

# --- 🌍 AJAX DROPDOWN API ROUTES ---

@main_bp.route('/get_districts/<int:state_id>')
def get_districts(state_id):
    from app.models.user_model import District
    districts = District.query.filter_by(state_id=state_id).all()
    # Convert SQLAlchemy objects to dictionary for JSON
    return jsonify([{"id": d.id, "name": d.name} for d in districts])

@main_bp.route('/get_talukas/<int:district_id>')
def get_talukas(district_id):
    from app.models.user_model import Taluka
    talukas = Taluka.query.filter_by(district_id=district_id).all()
    return jsonify([{"id": t.id, "name": t.name} for t in talukas])

@main_bp.route('/get_villages/<int:taluka_id>')
def get_villages(taluka_id):
    from app.models.user_model import Village
    villages = Village.query.filter_by(taluka_id=taluka_id).all()
    return jsonify([{"id": v.id, "name": v.name} for v in villages])