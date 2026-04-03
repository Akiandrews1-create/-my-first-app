from flask import Flask, render_template, request, redirect, url_for, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "secret123"  # change later

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# change this if your admin username is different
ADMIN_USERNAME = "isaiah"


# ===== DATABASE SETUP =====
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
            user_id INTEGER NOT NULL,
            expression TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            ip_address TEXT,
            log_time TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ===== USER CLASS =====
class User(UserMixin):
    def __init__(self, user_id, username):
        self.id = str(user_id)
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()

    if user:
        return User(user[0], user[1])
    return None


# ===== HELPERS =====
def log_user_action(user_id, username, action):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO login_logs (user_id, username, action, ip_address, log_time)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (user_id, username, action, ip)
    )
    conn.commit()
    conn.close()


# ===== ROUTES =====
@app.route("/", methods=["GET", "POST"])
@login_required
def calculator():
    result = ""
    special_message = ""

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    if request.method == "POST":
        if "clear" in request.form:
            c.execute("DELETE FROM calculations WHERE user_id = ?", (current_user.id,))
            conn.commit()
        else:
            try:
                num1 = float(request.form["num1"])
                num2 = float(request.form["num2"])
                op = request.form["operation"]

                if op == "+":
                    result = num1 + num2
                elif op == "-":
                    result = num1 - num2
                elif op == "*":
                    result = num1 * num2
                elif op == "/":
                    if num2 == 0:
                        result = "Cannot divide by zero"
                    else:
                        result = num1 / num2
                else:
                    result = "Invalid operation"

                expression = f"{num1} {op} {num2} = {result}"
                c.execute(
                    "INSERT INTO calculations (user_id, expression) VALUES (?, ?)",
                    (current_user.id, expression)
                )
                conn.commit()

                if result == 69:
                    special_message = "SAYANGGGGG ❤️"

            except ValueError:
                result = "Invalid input"

    c.execute(
        "SELECT expression FROM calculations WHERE user_id = ? ORDER BY id DESC",
        (current_user.id,)
    )
    history_rows = c.fetchall()

    c.execute(
        "SELECT COUNT(*) FROM calculations WHERE user_id = ?",
        (current_user.id,)
    )
    total_calculations = c.fetchone()[0]

    conn.close()

    history = [row[0] for row in history_rows]

    return render_template(
        "index.html",
        result=result,
        history=history,
        user=current_user.username,
        special_message=special_message,
        total_calculations=total_calculations
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        if not username or not password:
            return "Username and password are required"

        if len(username) > 30:
            return "Username too long"

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        try:
            c.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "User already exists"

        conn.close()
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT id, username, password FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            login_user(User(user[0], user[1]))
            log_user_action(user[0], user[1], "login")
            return redirect(url_for("calculator"))

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    log_user_action(current_user.id, current_user.username, "logout")
    logout_user()
    return redirect(url_for("login"))


@app.route("/logs")
@login_required
def logs():
    if current_user.username.strip().lower() != ADMIN_USERNAME.strip().lower():
        abort(403)

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
        SELECT username, action, ip_address, log_time
        FROM login_logs
        ORDER BY id DESC
    """)
    rows = c.fetchall()

    c.execute("SELECT COUNT(*) FROM login_logs WHERE action = 'login'")
    total_logins = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM login_logs WHERE action = 'logout'")
    total_logouts = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT username) FROM login_logs")
    unique_users = c.fetchone()[0]

    conn.close()

    return render_template(
        "logs.html",
        logs=rows,
        user=current_user.username,
        total_logins=total_logins,
        total_logouts=total_logouts,
        unique_users=unique_users
    )


# ===== RUN =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)