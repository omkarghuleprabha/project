from flask import Blueprint, render_template, request, redirect, session
from app.utils.db import get_db

worker_bp = Blueprint(
    "worker_bp",
    __name__,
    url_prefix="/worker",
    template_folder="../templates"
)

# ---------- WORKER LOGIN ----------
@worker_bp.route("/login", methods=["GET", "POST"])
def worker_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE email=%s AND password=%s AND status='approved'", (email, password))
        worker = cursor.fetchone()
        conn.close()

        if worker:
            session["worker_id"] = worker[0]
            session["worker_name"] = worker[1]
            return redirect("/worker/tasks")
        else:
            return "Account not approved or invalid credentials"
    return render_template("auth/login.html")

# ---------- MY TASKS (Assigned by Admin) ----------
@worker_bp.route("/tasks")
def worker_tasks():
    if "worker_id" not in session: return redirect("/worker/login")
    
    conn = get_db()
    cursor = conn.cursor()
    # Fakt 'assigned' status aslele tasks dakhvane
    query = """
        SELECT r.id, u.name, r.area, r.photo, r.description, r.status 
        FROM requests r 
        JOIN users u ON r.user_id = u.id 
        WHERE r.worker_id = %s AND r.status = 'assigned'
    """
    cursor.execute(query, (session["worker_id"],))
    tasks = cursor.fetchall()
    conn.close()
    
    return render_template("worker/tasks.html", tasks=tasks)

# ---------- TASK COMPLETE EXECUTION ----------
@worker_bp.route("/complete_task/<int:req_id>", methods=["POST"])
def complete_task(req_id):
    if "worker_id" not in session: return redirect("/worker/login")
    
    conn = get_db()
    cursor = conn.cursor()
    # Task status 'completed' karne
    cursor.execute("UPDATE requests SET status='completed' WHERE id=%s", (req_id,))
    conn.commit()
    conn.close()
    
    return redirect("/worker/tasks")

# ---------- LOGOUT ----------
@worker_bp.route("/logout")
def worker_logout():
    session.clear()
    return redirect("/worker/login")