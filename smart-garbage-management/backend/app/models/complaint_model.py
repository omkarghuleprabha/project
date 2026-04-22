from .. import db
from datetime import datetime

class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    area = db.Column(db.String(100), nullable=False)
    photo = db.Column(db.String(255), nullable=False) # Path to image
    status = db.Column(db.String(20), default='Pending') # Pending, Assigned, Completed
    worker_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)