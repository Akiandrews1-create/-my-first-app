from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "secret123"  # change later

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

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

    conn.commit()
    conn.close()

init_db()

# ===== USER CLASS =====
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()

    if user:
        return User(user[0], user[1])
    return None

# ===== ROUTES =====
@app.route("/", methods=["GET", "POST"])
@login_required
def calculator():
    result = ""

    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    if request.method == "POST":
        if "clear" in request.form:
            c.execute("DELETE FROM calculations WHERE user_id=?", (current_user.id,))
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
                    result = num1 / num2 if num2 != 0 else "Cannot divide by zero"
                else:
                    result = "Invalid operation"

                expression = f"{num1} {op} {num2} = {result}"
                c.execute(
                    "INSERT INTO calculations (user_id, expression) VALUES (?, ?)",
                    (current_user.id, expression)
                )
                conn.commit()

            except:
                result = "Invalid input"

    c.execute(
        "SELECT expression FROM calculations WHERE user_id=? ORDER BY id DESC",
        (current_user.id,)
    )
    history_rows = c.fetchall()
    conn.close()

    history = [row[0] for row in history_rows]

    return render_template(
        "index.html",
        result=result,
        history=history,
        user=current_user.username
    )

# ===== REGISTER =====
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])

        conn = sqlite3.connect("users.db")
        c = conn.cursor()

        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
        except:
            conn.close()
            return "User already exists"

        conn.close()
        return redirect(url_for("login"))

    return render_template("register.html")

# ===== LOGIN =====
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            login_user(User(user[0], user[1]))
            return redirect(url_for("calculator"))

        return "Invalid credentials"

    return render_template("login.html")

# ===== LOGOUT =====
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ===== RUN =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)