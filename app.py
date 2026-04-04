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
DB_PATH = "users.db"


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                expression TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                ip_address TEXT,
                log_time TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


init_db()


class User(UserMixin):
    def __init__(self, user_id, username):
        self.id = str(user_id)
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    with get_db_connection() as conn:
        user = conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

    if user:
        return User(user["id"], user["username"])
    return None


def log_action(user_id, username, action):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO login_logs (user_id, username, action, ip_address)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, username, action, ip)
        )


@app.before_request
def keep_session_alive():
    session.permanent = True


@app.route("/", methods=["GET", "POST"])
@login_required
def home():
    result = ""
    special_message = ""
    error_message = ""
    success_message = ""
    num1_value = ""
    num2_value = ""
    operation_value = "+"

    if request.method == "POST":
        if "clear" in request.form:
            with get_db_connection() as conn:
                conn.execute(
                    "DELETE FROM calculations WHERE user_id = ?",
                    (current_user.id,)
                )
            success_message = "History cleared successfully."
        else:
            num1_value = request.form.get("num1", "").strip()
            num2_value = request.form.get("num2", "").strip()
            operation_value = request.form.get("operation", "+")

            try:
                num1 = float(num1_value)
                num2 = float(num2_value)
                op = operation_value

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

                with get_db_connection() as conn:
                    conn.execute(
                        "INSERT INTO calculations (user_id, expression) VALUES (?, ?)",
                        (current_user.id, expression)
                    )

                success_message = "Calculation saved."

                if result == 69:
                    special_message = "SAYANGGGGG ❤️"

            except ValueError:
                error_message = "Please enter valid numbers."

    with get_db_connection() as conn:
        history_rows = conn.execute(
            "SELECT expression FROM calculations WHERE user_id = ? ORDER BY id DESC",
            (current_user.id,)
        ).fetchall()

        total_calculations = conn.execute(
            "SELECT COUNT(*) AS count FROM calculations WHERE user_id = ?",
            (current_user.id,)
        ).fetchone()["count"]

    history = [row["expression"] for row in history_rows]

    return render_template(
        "index.html",
        result=result,
        history=history,
        total_calculations=total_calculations,
        special_message=special_message,
        error_message=error_message,
        success_message=success_message,
        user=current_user.username,
        num1_value=num1_value,
        num2_value=num2_value,
        operation_value=operation_value
    )


@app.route("/profile")
@login_required
def profile():
    with get_db_connection() as conn:
        total_calculations = conn.execute(
            "SELECT COUNT(*) AS count FROM calculations WHERE user_id = ?",
            (current_user.id,)
        ).fetchone()["count"]

        total_logins = conn.execute(
            "SELECT COUNT(*) AS count FROM login_logs WHERE username = ? AND action = 'login'",
            (current_user.username,)
        ).fetchone()["count"]

        total_logouts = conn.execute(
            "SELECT COUNT(*) AS count FROM login_logs WHERE username = ? AND action = 'logout'",
            (current_user.username,)
        ).fetchone()["count"]

        recent_rows = conn.execute(
            "SELECT expression FROM calculations WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (current_user.id,)
        ).fetchall()

    recent_history = [row["expression"] for row in recent_rows]

    return render_template(
        "profile.html",
        user=current_user.username,
        total_calculations=total_calculations,
        total_logins=total_logins,
        total_logouts=total_logouts,
        recent_history=recent_history
    )


@app.route("/logs")
@login_required
def logs():
    if current_user.username.lower() != ADMIN_USERNAME:
        abort(403)

    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT username, action, ip_address, log_time
            FROM login_logs
            ORDER BY id DESC
        """).fetchall()

        total_logins = conn.execute(
            "SELECT COUNT(*) AS count FROM login_logs WHERE action = 'login'"
        ).fetchone()["count"]

        total_logouts = conn.execute(
            "SELECT COUNT(*) AS count FROM login_logs WHERE action = 'logout'"
        ).fetchone()["count"]

        unique_users = conn.execute(
            "SELECT COUNT(DISTINCT username) AS count FROM login_logs"
        ).fetchone()["count"]

        chart_rows = conn.execute("""
            SELECT date(log_time) AS day,
                   SUM(CASE WHEN action = 'login' THEN 1 ELSE 0 END) AS login_count
            FROM login_logs
            GROUP BY date(log_time)
            ORDER BY date(log_time)
        """).fetchall()

    chart_labels = [row["day"] for row in chart_rows]
    chart_values = [row["login_count"] for row in chart_rows]

    return render_template(
        "logs.html",
        logs=rows,
        total_logins=total_logins,
        total_logouts=total_logouts,
        unique_users=unique_users,
        chart_labels=chart_labels,
        chart_values=chart_values,
        user=current_user.username
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    error_message = ""

    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        if not username or not password:
            error_message = "Username and password are required."
            return render_template("register.html", error_message=error_message)

        if len(username) > 30:
            error_message = "Username must be 30 characters or fewer."
            return render_template("register.html", error_message=error_message)

        hashed_password = generate_password_hash(password)

        try:
            with get_db_connection() as conn:
                conn.execute(
                    "INSERT INTO users (username, password) VALUES (?, ?)",
                    (username, hashed_password)
                )
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            error_message = "That username is already taken."

    return render_template("register.html", error_message=error_message)


@app.route("/login", methods=["GET", "POST"])
def login():
    error_message = ""

    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"]

        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):
            login_user(User(user["id"], user["username"]))
            log_action(user["id"], user["username"], "login")
            return redirect(url_for("home"))

        error_message = "Invalid username or password."

    return render_template("login.html", error_message=error_message)


@app.route("/logout")
@login_required
def logout():
    log_action(current_user.id, current_user.username, "logout")
    logout_user()
    return redirect(url_for("login"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)