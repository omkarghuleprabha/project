from app import create_app, db

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        # DATABASE TABLES CREATE KARNE
        db.create_all()
    print("🚀 Smart Garbage System Started on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)