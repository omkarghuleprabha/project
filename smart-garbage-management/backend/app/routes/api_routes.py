from flask import Blueprint, jsonify
from app.utils.db import get_db

api_bp = Blueprint(
    "api_bp",
    __name__,
    url_prefix="/api"
)
# ---------------- LOCATION APIs ----------------

@api_bp.route("/districts/<state>")
def get_districts(state):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT d.name 
        FROM districts d
        JOIN states s ON d.state_id = s.id
        WHERE s.name = %s
    """, (state,))

    data = [row[0] for row in cursor.fetchall()]
    conn.close()

    return jsonify(data)


@api_bp.route("/talukas/<district>")
def get_talukas(district):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT t.name 
        FROM talukas t
        JOIN districts d ON t.district_id = d.id
        WHERE d.name = %s
    """, (district,))

    data = [row[0] for row in cursor.fetchall()]
    conn.close()

    return jsonify(data)


@api_bp.route("/villages/<taluka>")
def get_villages(taluka):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT v.name 
        FROM villages v
        JOIN talukas t ON v.taluka_id = t.id
        WHERE t.name = %s
    """, (taluka,))

    data = [row[0] for row in cursor.fetchall()]
    conn.close()

    return jsonify(data)