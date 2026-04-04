from flask import Flask, render_template, request, redirect, url_for, abort, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta
import sqlite3
import os
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production")
app.permanent_session_lifetime = timedelta(minutes=30)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

ADMIN_USERNAME = "isaiah"
DB_PATH = "users.db"
MIN_PASSWORD_LENGTH = 8
MAX_LOGIN_ATTEMPTS = 5
LOGIN_BLOCK_MINUTES = 10


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
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                attempt_time TEXT NOT NULL DEFAULT (datetime('now'))
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


def get_client_ip():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    return ip or "unknown"


def log_action(user_id, username, action):
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO login_logs (user_id, username, action, ip_address)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, username, action, get_client_ip())
        )


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": get_csrf_token()}


@app.before_request
def keep_session_alive():
    session.permanent = True


def require_valid_csrf():
    if request.method != "POST":
        return

    form_token = request.form.get("csrf_token", "")
    session_token = session.get("_csrf_token", "")

    if not (form_token and session_token and secrets.compare_digest(form_token, session_token)):
        abort(400)


def clear_old_failed_attempts(ip_address):
    with get_db_connection() as conn:
        conn.execute(
            """
            DELETE FROM login_attempts
            WHERE ip_address = ?
              AND attempt_time < datetime('now', ?)
            """,
            (ip_address, f"-{LOGIN_BLOCK_MINUTES} minutes")
        )


def record_failed_login(ip_address):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO login_attempts (ip_address) VALUES (?)",
            (ip_address,)
        )


def clear_failed_logins(ip_address):
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM login_attempts WHERE ip_address = ?",
            (ip_address,)
        )


def is_ip_blocked(ip_address):
    clear_old_failed_attempts(ip_address)
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM login_attempts WHERE ip_address = ?",
            (ip_address,)
        ).fetchone()
    return row["count"] >= MAX_LOGIN_ATTEMPTS


def password_is_valid(password):
    return len(password) >= MIN_PASSWORD_LENGTH


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
        require_valid_csrf()

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


@app.route("/admin")
@login_required
def admin():
    if current_user.username.lower() != ADMIN_USERNAME:
        abort(403)

    with get_db_connection() as conn:
        users = conn.execute("""
            SELECT
                u.id,
                u.username,
                COALESCE(c.calc_count, 0) AS calc_count,
                COALESCE(l.login_count, 0) AS login_count,
                COALESCE(o.logout_count, 0) AS logout_count
            FROM users u
            LEFT JOIN (
                SELECT user_id, COUNT(*) AS calc_count
                FROM calculations
                GROUP BY user_id
            ) c ON u.id = c.user_id
            LEFT JOIN (
                SELECT username, COUNT(*) AS login_count
                FROM login_logs
                WHERE action = 'login'
                GROUP BY username
            ) l ON u.username = l.username
            LEFT JOIN (
                SELECT username, COUNT(*) AS logout_count
                FROM login_logs
                WHERE action = 'logout'
                GROUP BY username
            ) o ON u.username = o.username
            ORDER BY u.username ASC
        """).fetchall()

        total_users = conn.execute(
            "SELECT COUNT(*) AS count FROM users"
        ).fetchone()["count"]

        total_calculations = conn.execute(
            "SELECT COUNT(*) AS count FROM calculations"
        ).fetchone()["count"]

    return render_template(
        "admin.html",
        users=users,
        total_users=total_users,
        total_calculations=total_calculations,
        user=current_user.username
    )


@app.route("/admin/delete-user/<int:user_id>", methods=["POST"])
@login_required
def admin_delete_user(user_id):
    if current_user.username.lower() != ADMIN_USERNAME:
        abort(403)

    require_valid_csrf()

    with get_db_connection() as conn:
        target_user = conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

        if not target_user:
            return redirect(url_for("admin"))

        if target_user["username"].lower() == ADMIN_USERNAME:
            return redirect(url_for("admin"))

        conn.execute("DELETE FROM calculations WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM login_logs WHERE user_id = ? OR username = ?", (user_id, target_user["username"]))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    return redirect(url_for("admin"))


@app.route("/admin/reset-password/<int:user_id>", methods=["POST"])
@login_required
def admin_reset_password(user_id):
    if current_user.username.lower() != ADMIN_USERNAME:
        abort(403)

    require_valid_csrf()

    new_password = request.form.get("new_password", "").strip()

    if not password_is_valid(new_password):
        return redirect(url_for("admin"))

    hashed_password = generate_password_hash(new_password)

    with get_db_connection() as conn:
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hashed_password, user_id)
        )

    return redirect(url_for("admin"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    error = ""
    success = ""

    if request.method == "POST":
        require_valid_csrf()

        old_password = request.form["old_password"]
        new_password = request.form["new_password"]

        if not password_is_valid(new_password):
            error = f"New password must be at least {MIN_PASSWORD_LENGTH} characters long."
            return render_template("change_password.html", error=error, success=success)

        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT password FROM users WHERE id = ?",
                (current_user.id,)
            ).fetchone()

            if not check_password_hash(user["password"], old_password):
                error = "Old password is incorrect."
            elif check_password_hash(user["password"], new_password):
                error = "New password must be different from your current password."
            else:
                hashed = generate_password_hash(new_password)
                conn.execute(
                    "UPDATE users SET password = ? WHERE id = ?",
                    (hashed, current_user.id)
                )
                success = "Password updated successfully."

    return render_template("change_password.html", error=error, success=success)


@app.route("/register", methods=["GET", "POST"])
def register():
    error_message = ""

    if request.method == "POST":
        require_valid_csrf()

        username = request.form["username"].strip().lower()
        password = request.form["password"]

        if not username or not password:
            error_message = "Username and password are required."
            return render_template("register.html", error_message=error_message)

        if len(username) > 30:
            error_message = "Username must be 30 characters or fewer."
            return render_template("register.html", error_message=error_message)

        if not password_is_valid(password):
            error_message = f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
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
        require_valid_csrf()

        ip_address = get_client_ip()

        if is_ip_blocked(ip_address):
            error_message = f"Too many failed attempts. Try again in {LOGIN_BLOCK_MINUTES} minutes."
            return render_template("login.html", error_message=error_message)

        username = request.form["username"].strip().lower()
        password = request.form["password"]

        with get_db_connection() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ).fetchone()

        if user and check_password_hash(user["password"], password):
            clear_failed_logins(ip_address)
            login_user(User(user["id"], user["username"]))
            log_action(user["id"], user["username"], "login")
            return redirect(url_for("home"))

        record_failed_login(ip_address)
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