import os
import mysql.connector
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Read SECRET_KEY from environment or default
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "YOUR_SUPER_SECRET_KEY")

# MySQL config from environment variables
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASS = os.environ.get("MYSQL_PASS", "password")
MYSQL_DB   = os.environ.get("MYSQL_DB", "socialdb")

# Folder for uploaded images/videos
UPLOAD_FOLDER = os.path.join("static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov", ".avi"}

def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def get_db_connection():
    """Create a new MySQL connection. For production, 
       consider using a connection pool or ORM.
    """
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        database=MYSQL_DB
    )

# ----------------- INIT DB -----------------
def init_db():
    """Create tables if they don't exist (harmless if called multiple times)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # USERS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            profile_picture VARCHAR(255),
            bio TEXT
        )
    """)
    # POSTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            content TEXT,
            media_filename VARCHAR(255),
            created_at DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # STORIES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            media_filename VARCHAR(255),
            created_at DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    # LIKES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            post_id INT NOT NULL,
            user_id INT NOT NULL
        )
    """)
    # SAVED_POSTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_posts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            post_id INT NOT NULL
        )
    """)
    # MESSAGES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sender_id INT NOT NULL,
            recipient_id INT NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME NOT NULL
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()

# Call init_db() once (each Pod can do it; it's idempotent).
init_db()

def get_current_user_id():
    return session.get("user_id")


# ------------- ROUTES -------------

@app.route("/")
def home():
    if get_current_user_id():
        return redirect(url_for("feed"))
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        password_hash = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO users (username, password_hash)
                VALUES (%s, %s)
            """, (username, password_hash))
            conn.commit()
            flash("Sign-up successful! Please log in.", "success")
            return redirect(url_for("login"))
        except mysql.connector.Error as e:
            # 1062 = duplicate entry in MySQL
            if e.errno == 1062:
                flash("Username already exists!", "error")
            else:
                flash(f"MySQL Error: {e}", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()
        cursor.close()
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

# ------------- FEED & POSTS -------------
@app.route("/feed", methods=["GET", "POST"])
def feed():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Create new post
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        media_file = request.files.get("media_file")
        media_filename = None

        if media_file and media_file.filename and allowed_file(media_file.filename):
            secure_name = secure_filename(media_file.filename)
            media_path = os.path.join(app.config["UPLOAD_FOLDER"], secure_name)
            media_file.save(media_path)
            media_filename = secure_name

        if content or media_filename:
            now = datetime.now()
            cursor.execute("""
                INSERT INTO posts (user_id, content, media_filename, created_at)
                VALUES (%s, %s, %s, %s)
            """, (user_id, content, media_filename, now))
            conn.commit()

    # Stories (<24h)
    cutoff = datetime.now() - timedelta(hours=24)
    cursor.execute("""
        SELECT s.id, s.media_filename, s.created_at,
               u.username, u.profile_picture
        FROM stories s
        JOIN users u ON s.user_id = u.id
        WHERE s.created_at >= %s
        ORDER BY s.created_at DESC
    """, (cutoff,))
    stories = cursor.fetchall()

    # All posts
    cursor.execute("""
        SELECT p.id, p.user_id, p.content, p.media_filename, p.created_at,
               u.username, u.profile_picture
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
    """)
    raw_posts = cursor.fetchall()

    posts = []
    for p in raw_posts:
        post_id = p["id"]
        # Count likes
        cursor.execute("SELECT COUNT(*) AS c FROM likes WHERE post_id=%s", (post_id,))
        lr = cursor.fetchone()
        like_count = lr["c"] if lr else 0

        # user has liked?
        cursor.execute("SELECT id FROM likes WHERE post_id=%s AND user_id=%s", (post_id, user_id))
        rlike = cursor.fetchone()
        user_has_liked = True if rlike else False

        # user has saved?
        cursor.execute("SELECT id FROM saved_posts WHERE post_id=%s AND user_id=%s", (post_id, user_id))
        rsave = cursor.fetchone()
        user_has_saved = True if rsave else False

        posts.append({
            "id": p["id"],
            "user_id": p["user_id"],
            "content": p["content"],
            "media_filename": p["media_filename"],
            "created_at": p["created_at"],
            "username": p["username"],
            "profile_picture": p["profile_picture"],
            "like_count": like_count,
            "user_has_liked": user_has_liked,
            "user_has_saved": user_has_saved
        })

    cursor.close()
    conn.close()
    return render_template("feed.html", stories=stories, posts=posts, current_user_id=user_id)

@app.route("/like_api/<int:post_id>", methods=["POST"])
def like_api(post_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM likes WHERE post_id=%s AND user_id=%s", (post_id, user_id))
    row = cursor.fetchone()

    if row:
        cursor.execute("DELETE FROM likes WHERE id=%s", (row["id"],))
        action = "unliked"
    else:
        cursor.execute("INSERT INTO likes (post_id, user_id) VALUES (%s, %s)", (post_id, user_id))
        action = "liked"
    conn.commit()

    cursor.execute("SELECT COUNT(*) AS c FROM likes WHERE post_id=%s", (post_id,))
    lr = cursor.fetchone()
    like_count = lr["c"] if lr else 0

    cursor.close()
    conn.close()
    return jsonify({"status": action, "like_count": like_count})

@app.route("/save_api/<int:post_id>", methods=["POST"])
def save_api(post_id):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM saved_posts WHERE post_id=%s AND user_id=%s", (post_id, user_id))
    row = cursor.fetchone()

    if row:
        cursor.execute("DELETE FROM saved_posts WHERE id=%s", (row["id"],))
        action = "unsaved"
    else:
        cursor.execute("INSERT INTO saved_posts (post_id, user_id) VALUES (%s, %s)", (post_id, user_id))
        action = "saved"
    conn.commit()

    cursor.close()
    conn.close()
    return jsonify({"status": action})

@app.route("/delete_post/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    user_id = get_current_user_id()
    if not user_id:
        flash("You must be logged in to delete a post.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id FROM posts WHERE id=%s", (post_id,))
    post = cursor.fetchone()

    if not post:
        flash("Post not found!", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("feed"))

    if post["user_id"] != user_id:
        flash("You cannot delete someone else's post!", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("feed"))

    cursor.execute("DELETE FROM posts WHERE id=%s", (post_id,))
    cursor.execute("DELETE FROM likes WHERE post_id=%s", (post_id,))
    cursor.execute("DELETE FROM saved_posts WHERE post_id=%s", (post_id,))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Post deleted!", "success")
    return redirect(url_for("feed"))

@app.route("/upload_story", methods=["POST"])
def upload_story():
    user_id = get_current_user_id()
    if not user_id:
        flash("You must be logged in to upload a story.", "error")
        return redirect(url_for("login"))

    story_file = request.files.get("story_file")
    if story_file and story_file.filename and allowed_file(story_file.filename):
        fname = secure_filename(story_file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
        story_file.save(path)

        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now()
        cursor.execute("""
            INSERT INTO stories (user_id, media_filename, created_at)
            VALUES (%s, %s, %s)
        """, (user_id, fname, now))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Story uploaded!", "success")
    else:
        flash("Invalid file or none selected.", "error")

    return redirect(url_for("feed"))

@app.route("/profile", methods=["GET", "POST"])
def profile():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if request.method == "POST":
        new_bio = request.form.get("bio", "")
        pfp_file = request.files.get("profile_picture")
        if pfp_file and pfp_file.filename and allowed_file(pfp_file.filename):
            sec_name = secure_filename(pfp_file.filename)
            path = os.path.join(app.config["UPLOAD_FOLDER"], sec_name)
            pfp_file.save(path)
            cursor.execute("UPDATE users SET profile_picture=%s WHERE id=%s", (sec_name, user_id))

        cursor.execute("UPDATE users SET bio=%s WHERE id=%s", (new_bio, user_id))
        conn.commit()
        flash("Profile updated!", "success")

        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        user = cursor.fetchone()

    # user posts
    cursor.execute("""
        SELECT p.*, u.username, u.profile_picture
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.user_id=%s
        ORDER BY p.created_at DESC
    """, (user_id,))
    raw_posts = cursor.fetchall()

    posts = []
    for p in raw_posts:
        cursor.execute("SELECT COUNT(*) AS c FROM likes WHERE post_id=%s", (p["id"],))
        lr = cursor.fetchone()
        like_count = lr["c"] if lr else 0

        posts.append({
            "id": p["id"],
            "content": p["content"],
            "media_filename": p["media_filename"],
            "created_at": p["created_at"],
            "username": p["username"],
            "profile_picture": p["profile_picture"],
            "like_count": like_count
        })

    # user saved
    cursor.execute("""
        SELECT p.*, u.username, u.profile_picture
        FROM saved_posts s
        JOIN posts p ON s.post_id = p.id
        JOIN users u ON p.user_id = u.id
        WHERE s.user_id=%s
        ORDER BY p.created_at DESC
    """, (user_id,))
    raw_saved = cursor.fetchall()

    saved_posts = []
    for sp in raw_saved:
        cursor.execute("SELECT COUNT(*) AS c FROM likes WHERE post_id=%s", (sp["id"],))
        lr = cursor.fetchone()
        lc = lr["c"] if lr else 0

        saved_posts.append({
            "id": sp["id"],
            "content": sp["content"],
            "media_filename": sp["media_filename"],
            "created_at": sp["created_at"],
            "username": sp["username"],
            "profile_picture": sp["profile_picture"],
            "like_count": lc
        })

    cursor.close()
    conn.close()

    user_post_count = len(posts)

    return render_template("profile.html",
                           user=user,
                           posts=posts,
                           saved_posts=saved_posts,
                           user_post_count=user_post_count)

@app.route("/user/<username>")
def user_profile(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()
    if not user:
        flash("User does not exist!", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("feed"))

    cursor.execute("""
        SELECT p.*, u.username, u.profile_picture
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE u.username=%s
        ORDER BY p.created_at DESC
    """, (username,))
    raw_posts = cursor.fetchall()
    cursor.close()
    conn.close()

    posts = []
    for p in raw_posts:
        posts.append({
            "id": p["id"],
            "content": p["content"],
            "media_filename": p["media_filename"],
            "created_at": p["created_at"],
            "username": p["username"],
            "profile_picture": p["profile_picture"]
        })

    user_post_count = len(raw_posts)

    return render_template("user_profile.html",
                           user=user,
                           posts=posts,
                           user_post_count=user_post_count)

@app.route("/messages")
def messages_list():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT DISTINCT u.id, u.username
        FROM messages m
        JOIN users u ON (u.id = m.sender_id OR u.id = m.recipient_id)
        WHERE (m.sender_id=%s OR m.recipient_id=%s)
          AND u.id<>%s
    """, (user_id, user_id, user_id))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    conversation_partners = rows
    return render_template("messages.html", conversation_partners=conversation_partners)

@app.route("/messages/<username>", methods=["GET", "POST"])
def direct_messages(username):
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    other_user = get_user_by_username(username)
    if not other_user:
        flash("User does not exist!", "error")
        return redirect(url_for("messages_list"))

    other_id = other_user["id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            now = datetime.now()
            cursor.execute("""
                INSERT INTO messages (sender_id, recipient_id, content, created_at)
                VALUES (%s, %s, %s, %s)
            """, (user_id, other_id, content, now))
            conn.commit()

    cursor.execute("""
        SELECT m.*, s.username as sender_name, r.username as recipient_name
        FROM messages m
        JOIN users s ON s.id = m.sender_id
        JOIN users r ON r.id = m.recipient_id
        WHERE (m.sender_id=%s AND m.recipient_id=%s)
           OR (m.sender_id=%s AND m.recipient_id=%s)
        ORDER BY m.created_at ASC
    """, (user_id, other_id, other_id, user_id))
    msgs = cursor.fetchall()
    cursor.close()
    conn.close()

    messages_list = []
    for msg in msgs:
        messages_list.append({
            "id": msg["id"],
            "content": msg["content"],
            "created_at": str(msg["created_at"]),
            "sender_id": msg["sender_id"],
            "sender_name": msg["sender_name"],
            "recipient_id": msg["recipient_id"],
            "recipient_name": msg["recipient_name"]
        })

    return render_template("messages.html",
                           conversation=True,
                           other_user=other_user,
                           messages_list=messages_list)

@app.route("/messages_api/<username>")
def messages_api(username):
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403

    other_user = get_user_by_username(username)
    if not other_user:
        return jsonify({"error": "User does not exist"}), 404

    other_id = other_user["id"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT m.*, s.username as sender_name, r.username as recipient_name
        FROM messages m
        JOIN users s ON s.id = m.sender_id
        JOIN users r ON r.id = m.recipient_id
        WHERE (m.sender_id=%s AND m.recipient_id=%s)
           OR (m.sender_id=%s AND m.recipient_id=%s)
        ORDER BY m.created_at ASC
    """, (user_id, other_id, other_id, user_id))
    msgs = cursor.fetchall()
    cursor.close()
    conn.close()

    data = []
    for msg in msgs:
        data.append({
            "id": msg["id"],
            "content": msg["content"],
            "created_at": str(msg["created_at"]),
            "sender_id": msg["sender_id"],
            "sender_name": msg["sender_name"],
            "recipient_id": msg["recipient_id"],
            "recipient_name": msg["recipient_name"]
        })

    return jsonify({"messages": data})

@app.route("/uploads/<filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
