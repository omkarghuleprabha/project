from flask import Blueprint, redirect, url_for

complaint_bp = Blueprint('complaint_bp', __name__, url_prefix='/complaint')


@complaint_bp.route('/add', methods=['POST'])
def add_complaint():
    return redirect(url_for('user_bp.add_complaint'), code=307)
