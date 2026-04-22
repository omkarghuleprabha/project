from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from app.models.user_model import User
# Note: Assuming you have State, District, Taluka, and Village models defined 
# in your models folder as well.

main_bp = Blueprint('main_bp', __name__)

# --- 🚀 UPDATED: UNIFIED DASHBOARD TRAFFIC CONTROLLER (SQLAlchemy) ---
@main_bp.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('auth_bp.login'))

    role = session.get('role')
    redirect_map = {
        'district_admin': 'auth_bp.district_dashboard',
        'admin': 'auth_bp.taluka_dashboard',
        'worker': 'auth_bp.worker_dashboard',
        'user': 'auth_bp.citizen_dashboard',
    }
    return redirect(url_for(redirect_map.get(role, 'auth_bp.login')))

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
