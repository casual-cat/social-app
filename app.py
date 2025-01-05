# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "YOUR_SUPER_SECRET_KEY"  # Replace with something more secure in production

# --- DATABASE SETUP ---
DATABASE = "social.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# Create tables if they don't exist
def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db_connection()
        conn.execute('''CREATE TABLE users (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT UNIQUE NOT NULL,
                            password_hash TEXT NOT NULL
                        )''')
        conn.execute('''CREATE TABLE posts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            content TEXT NOT NULL,
                            FOREIGN KEY(user_id) REFERENCES users(id)
                        )''')
        conn.commit()
        conn.close()

init_db()  # Initialize DB on first run

# --- HELPER FUNCTIONS ---
def get_current_user():
    if "user_id" in session:
        return session["user_id"]
    return None

# --- ROUTES ---
@app.route("/")
def home():
    """If the user is logged in, show the feed; otherwise, show login."""
    if get_current_user():
        return redirect(url_for("feed"))
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_hash = generate_password_hash(password)

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                         (username, password_hash))
            conn.commit()
            flash("Sign-up successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists!", "error")
        finally:
            conn.close()
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Welcome back!", "success")
            return redirect(url_for("feed"))
        else:
            flash("Invalid username or password!", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/feed", methods=["GET", "POST"])
def feed():
    # Ensure user is logged in
    if not get_current_user():
        return redirect(url_for("login"))

    conn = get_db_connection()
    if request.method == "POST":
        content = request.form["content"]
        if content.strip():
            conn.execute("INSERT INTO posts (user_id, content) VALUES (?, ?)",
                         (session["user_id"], content))
            conn.commit()
    # Show all posts (newest first)
    posts = conn.execute("""
        SELECT p.id, p.content, u.username
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.id DESC
    """).fetchall()
    conn.close()

    return render_template("feed.html", posts=posts)

if __name__ == "__main__":
    # Use debug=True only in development
    app.run(debug=True, host="0.0.0.0", port=5001)
