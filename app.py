from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24).hex()

DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "school.db"))
DEFAULT_TEACHER_USERNAME = os.environ.get("DEFAULT_TEACHER_USERNAME", "admin")
DEFAULT_TEACHER_PASSWORD = os.environ.get("DEFAULT_TEACHER_PASSWORD")
DEFAULT_STUDENT_PASSWORD = os.environ.get("DEFAULT_STUDENT_PASSWORD")

def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Teachers
    cur.execute("""CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL
    )""")
    
    # Students
    cur.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        roll_no TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        class_name TEXT NOT NULL,
        section TEXT NOT NULL,
        password TEXT NOT NULL,
        result_published INTEGER DEFAULT 1
    )""")
    
    # Marks
    cur.execute("""CREATE TABLE IF NOT EXISTS marks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        marks INTEGER NOT NULL,
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    )""")
    
    # Seed demo data
    cur.execute("SELECT COUNT(*) FROM teachers")
    if cur.fetchone()[0] == 0 and DEFAULT_TEACHER_PASSWORD:
        cur.execute("INSERT INTO teachers (username, password, name) VALUES (?, ?, ?)",
                    (DEFAULT_TEACHER_USERNAME, generate_password_hash(DEFAULT_TEACHER_PASSWORD), "Mr. Rajesh Sharma"))
    
    cur.execute("SELECT COUNT(*) FROM students")
    if cur.fetchone()[0] == 0 and DEFAULT_STUDENT_PASSWORD:
        pw = generate_password_hash(DEFAULT_STUDENT_PASSWORD)
        cur.execute("INSERT INTO students (roll_no, name, class_name, section, password) VALUES (?, ?, ?, ?, ?)",
                    ("S001", "Aradhya Singh", "10", "A", pw))
        sid = cur.lastrowid
        subjects = ["English", "Hindi", "Mathematics", "Science", "Social Science"]
        for s in subjects:
            cur.execute("INSERT INTO marks (student_id, subject, marks) VALUES (?, ?, ?)", (sid, s, 85))
    
    conn.commit()
    conn.close()

# Decorator
def login_required(role):
    def decorator(f):
        def wrapper(*args, **kwargs):
            if "user_id" not in session or session.get("role") != role:
                return jsonify({"success": False, "message": "Unauthorized"}), 401
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    role = data.get("role")
    username = data.get("username")
    password = data.get("password")
    
    conn = get_db()
    cur = conn.cursor()
    
    if role == "teacher":
        cur.execute("SELECT * FROM teachers WHERE username = ?", (username,))
        user = cur.fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["role"] = "teacher"
            session["name"] = user["name"]
            conn.close()
            return jsonify({"success": True, "redirect": "/teacher/dashboard"})
    
    elif role == "student":
        cur.execute("SELECT * FROM students WHERE roll_no = ?", (username,))
        user = cur.fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["role"] = "student"
            session["name"] = user["name"]
            session["roll_no"] = user["roll_no"]
            conn.close()
            return jsonify({"success": True, "redirect": "/student/dashboard"})
    
    conn.close()
    return jsonify({"success": False, "message": "Invalid credentials"})

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ===================== STUDENT ROUTES =====================
@app.route("/student/dashboard")
@login_required("student")
def student_dashboard():
    return render_template("student_dashboard.html")

@app.route("/api/student/profile")
@login_required("student")
def api_student_profile():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE id = ?", (session["user_id"],))
    student = dict(cur.fetchone())
    conn.close()
    return jsonify(student)

@app.route("/api/student/marks")
@login_required("student")
def api_student_marks():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT subject, marks FROM marks WHERE student_id = ?", (session["user_id"],))
    marks_list = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    if not marks_list:
        return jsonify({"marks": [], "percentage": 0, "grade": "N/A"})
    
    total = sum(m["marks"] for m in marks_list)
    max_total = len(marks_list) * 100
    percentage = round(total / max_total * 100, 2)
    
    if percentage >= 90: grade = "A+"
    elif percentage >= 75: grade = "A"
    elif percentage >= 60: grade = "B"
    elif percentage >= 40: grade = "C"
    else: grade = "F"
    
    return jsonify({
        "marks": marks_list,
        "total": total,
        "max_total": max_total,
        "percentage": percentage,
        "grade": grade
    })

@app.route("/api/student/attendance")
@login_required("student")
def api_student_attendance():
    return jsonify({"overall": 92, "monthly": [{"month":"Mar","perc":95},{"month":"Feb","perc":89}]})

# ===================== TEACHER ROUTES =====================
@app.route("/teacher/dashboard")
@login_required("teacher")
def teacher_dashboard():
    return render_template("teacher_dashboard.html")

@app.route("/api/teacher/students")
@login_required("teacher")
def api_teacher_students():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, roll_no, name, class_name, section FROM students")
    students = [dict(row) for row in cur.fetchall()]
    conn.close()
    return jsonify(students)

@app.route("/api/teacher/add_student", methods=["POST"])
@login_required("teacher")
def api_add_student():
    data = request.get_json()
    initial_password = os.environ.get("NEW_STUDENT_DEFAULT_PASSWORD")
    if not initial_password:
        return jsonify({"success": False, "message": "NEW_STUDENT_DEFAULT_PASSWORD is not configured"}), 500
    pw_hash = generate_password_hash(initial_password)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""INSERT INTO students (roll_no, name, class_name, section, password)
                       VALUES (?, ?, ?, ?, ?)""",
                    (data["roll_no"], data["name"], data["class_name"], data["section"], pw_hash))
        sid = cur.lastrowid
        subjects = ["English", "Hindi", "Mathematics", "Science", "Social Science"]
        for s in subjects:
            cur.execute("INSERT INTO marks (student_id, subject, marks) VALUES (?, ?, 0)", (sid, s))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Student added successfully"})
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/teacher/enter_marks", methods=["POST"])
@login_required("teacher")
def api_enter_marks():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    for subject, marks in data["marks"].items():
        cur.execute("""INSERT OR REPLACE INTO marks (student_id, subject, marks)
                       VALUES (?, ?, ?)""", (data["student_id"], subject, int(marks)))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Marks saved successfully"})

init_db()

if __name__ == "__main__":
    print("Abhinav Public School web app started at http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
