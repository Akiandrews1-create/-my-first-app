from flask import Flask, render_template, request, redirect, url_for, abort, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "secret123"
app.permanent_session_lifetime = timedelta(minutes=30)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ADMIN_USERNAME = "isaiah"


# ===== DATABASE =====
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            expression TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            ip_address TEXT,
            log_time TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()


# ===== USER =====
class User(UserMixin):
    def __init__(self, id, username):
        self.id = str(id)
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()

    if user:
        return User(user[0], user[1])
    return None


# ===== HELPERS =====
def log_action(user_id, username, action):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO login_logs (user_id, username, action, ip_address, log_time)
        VALUES (?, ?, ?, ?, datetime('now'))
    """, (user_id, username, action, ip))
    conn.commit()
    conn.close()


@app.before_request
def keep_alive():
    session.permanent = True


# ===== ROUTES =====
@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    result = ""
    special_message = ""

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    if request.method == "POST":
        if "clear" in request.form:
            c.execute("DELETE FROM calculations WHERE user_id=?", (current_user.id,))
            conn.commit()
        else:
            try:
                n1 = float(request.form["num1"])
                n2 = float(request.form["num2"])
                op = request.form["operation"]

                if op == "+": result = n1 + n2
                elif op == "-": result = n1 - n2
                elif op == "*": result = n1 * n2
                elif op == "/": result = n1 / n2 if n2 != 0 else "Cannot divide by zero"

                expr = f"{n1} {op} {n2} = {result}"
                c.execute("INSERT INTO calculations (user_id, expression) VALUES (?, ?)", (current_user.id, expr))
                conn.commit()

                if result == 69:
                    special_message = "SAYANGGGGG ❤️"

            except:
                result = "Invalid input"

    c.execute("SELECT expression FROM calculations WHERE user_id=? ORDER BY id DESC", (current_user.id,))
    history = [row[0] for row in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM calculations WHERE user_id=?", (current_user.id,))
    total = c.fetchone()[0]

    conn.close()

    return render_template("index.html",
                           result=result,
                           history=history,
                           total_calculations=total,
                           special_message=special_message,
                           user=current_user.username)


@app.route("/profile")
@login_required
def profile():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM calculations WHERE user_id=?", (current_user.id,))
    total_calc = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM login_logs WHERE username=? AND action='login'", (current_user.username,))
    logins = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM login_logs WHERE username=? AND action='logout'", (current_user.username,))
    logouts = c.fetchone()[0]

    c.execute("SELECT expression FROM calculations WHERE user_id=? ORDER BY id DESC LIMIT 5", (current_user.id,))
    recent = [row[0] for row in c.fetchall()]

    conn.close()

    return render_template("profile.html",
                           user=current_user.username,
                           total_calculations=total_calc,
                           total_logins=logins,
                           total_logouts=logouts,
                           recent_history=recent)


@app.route("/logs")
@login_required
def logs():
    if current_user.username.lower() != ADMIN_USERNAME:
        abort(403)

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT username, action, ip_address, log_time FROM login_logs ORDER BY id DESC")
    rows = c.fetchall()

    c.execute("SELECT COUNT(*) FROM login_logs WHERE action='login'")
    total_logins = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM login_logs WHERE action='logout'")
    total_logouts = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT username) FROM login_logs")
    unique_users = c.fetchone()[0]

    conn.close()

    return render_template("logs.html",
                           logs=rows,
                           total_logins=total_logins,
                           total_logouts=total_logouts,
                           unique_users=unique_users)


@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].lower()
        password = generate_password_hash(request.form["password"])

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (username,password) VALUES (?,?)", (username,password))
            conn.commit()
        except:
            return "User exists"

        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].lower()
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()

        if user and check_password_hash(user[2], password):
            login_user(User(user[0], user[1]))
            log_action(user[0], user[1], "login")
            return redirect("/")

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    log_action(current_user.id, current_user.username, "logout")
    logout_user()
    return redirect("/login")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)