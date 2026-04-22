import os

base = "smart-garbage-management"


paths = [

    # backend
    "backend/app/models",
    "backend/app/routes",
    "backend/app/utils",
    "backend/app/decorators",

    "backend/app/templates/layout",
    "backend/app/templates/auth",
    "backend/app/templates/owner",
    "backend/app/templates/admin",
    "backend/app/templates/worker",
    "backend/app/templates/user",

    "backend/app/static/css",
    "backend/app/static/js",
    "backend/app/static/images",
    "backend/app/static/qr",

    # database
    "database",

    # docs
    "docs",

    # uploads
    "uploads/images",
    "uploads/qr",
]


files = [

    # models
    "backend/app/models/user_model.py",
    "backend/app/models/admin_model.py",
    "backend/app/models/worker_model.py",
    "backend/app/models/request_model.py",
    "backend/app/models/payment_model.py",
    "backend/app/models/complaint_model.py",
    "backend/app/models/feedback_model.py",

    # routes
    "backend/app/routes/auth_routes.py",
    "backend/app/routes/owner_routes.py",
    "backend/app/routes/admin_routes.py",
    "backend/app/routes/worker_routes.py",
    "backend/app/routes/user_routes.py",
    "backend/app/routes/api_routes.py",

    # utils
    "backend/app/utils/qr.py",
    "backend/app/utils/mail.py",
    "backend/app/utils/payment.py",
    "backend/app/utils/location.py",

    # decorators
    "backend/app/decorators/auth.py",

    # templates layout
    "backend/app/templates/layout/base.html",
    "backend/app/templates/layout/navbar.html",
    "backend/app/templates/layout/sidebar.html",

    # auth
    "backend/app/templates/auth/login.html",
    "backend/app/templates/auth/register.html",

    # owner
    "backend/app/templates/owner/dashboard.html",
    "backend/app/templates/owner/admins.html",
    "backend/app/templates/owner/payments.html",
    "backend/app/templates/owner/complaints.html",
    "backend/app/templates/owner/feedback.html",
    "backend/app/templates/owner/reports.html",

    # admin
    "backend/app/templates/admin/dashboard.html",
    "backend/app/templates/admin/workers.html",
    "backend/app/templates/admin/requests.html",
    "backend/app/templates/admin/vehicles.html",
    "backend/app/templates/admin/payments.html",
    "backend/app/templates/admin/complaints.html",

    # worker
    "backend/app/templates/worker/dashboard.html",
    "backend/app/templates/worker/requests.html",
    "backend/app/templates/worker/weight.html",
    "backend/app/templates/worker/qr.html",
    "backend/app/templates/worker/earnings.html",

    # user
    "backend/app/templates/user/dashboard.html",
    "backend/app/templates/user/request.html",
    "backend/app/templates/user/track.html",
    "backend/app/templates/user/payment.html",
    "backend/app/templates/user/complaint.html",
    "backend/app/templates/user/feedback.html",

    # static
    "backend/app/static/css/style.css",
    "backend/app/static/js/script.js",

    # backend main
    "backend/app/config.py",
    "backend/app/__init__.py",
    "backend/run.py",
    "backend/requirements.txt",
    "backend/.env",

    # database
    "database/schema.sql",
    "database/data.sql",

    # docs
    "docs/project_report.docx",
    "docs/diagrams.png",
    "docs/api_docs.txt",

    # root
    "README.md",
    ".gitignore",
]


def create_structure():
    for path in paths:
        full_path = os.path.join(base, path)
        os.makedirs(full_path, exist_ok=True)

    for file in files:
        full_path = os.path.join(base, file)

        folder = os.path.dirname(full_path)
        os.makedirs(folder, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            pass

    print("✅ Structure Created Successfully")


if __name__ == "__main__":
    create_structure()