import os
import sqlite3
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "YOUR_SUPER_SECRET_KEY"  # Replace with something more secure

# ---------------- CONFIG ----------------
DATABASE = "social.db"
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov", ".avi"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- INIT DB ----------------
def init_db():
    if not os.path.exists(DATABASE):
        conn = get_db_connection()
        # USERS
        conn.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                profile_picture TEXT,
                bio TEXT,
                theme_preference TEXT DEFAULT 'light'  -- new column for theme
            )
        """)
        # POSTS
        conn.execute("""
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT,
                media_filename TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        # STORIES
        conn.execute("""
            CREATE TABLE stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                media_filename TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        # LIKES
        conn.execute("""
            CREATE TABLE likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL
            )
        """)
        # MESSAGES (for Direct Messaging)
        conn.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(sender_id) REFERENCES users(id),
                FOREIGN KEY(recipient_id) REFERENCES users(id)
            )
        """)
        conn.commit()
        conn.close()

init_db()

# ---------------- HELPERS ----------------
def get_current_user_id():
    return session.get("user_id")

def get_user_by_id(user_id):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return user

def get_user_by_username(username):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return user

# Get theme (light/dark) for current user or default "light"
def get_current_theme():
    user_id = get_current_user_id()
    if user_id:
        user = get_user_by_id(user_id)
        if user:
            return user["theme_preference"] or "light"
    return "light"

# ---------------- AUTH ROUTES ----------------
@app.route("/")
def home():
    """Go to feed if logged in, else login."""
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
        try:
            conn.execute("""
                INSERT INTO users (username, password_hash)
                VALUES (?, ?)
            """, (username, password_hash))
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
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
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

# ---------------- THEME TOGGLE ----------------
@app.route("/toggle_theme", methods=["POST"])
def toggle_theme():
    """Toggle user's theme_preference between 'light' and 'dark'."""
    user_id = get_current_user_id()
    if not user_id:
        flash("You must be logged in to toggle theme.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute("SELECT theme_preference FROM users WHERE id=?", (user_id,)).fetchone()
    current = user["theme_preference"] if user else "light"

    new_theme = "dark" if current == "light" else "light"
    conn.execute("UPDATE users SET theme_preference=? WHERE id=?", (new_theme, user_id))
    conn.commit()
    conn.close()

    flash(f"Theme changed to {new_theme} mode!", "success")
    return redirect(url_for("feed"))

# ---------------- FEED & POSTS ----------------
@app.route("/feed", methods=["GET", "POST"])
def feed():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db_connection()
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
            conn.execute("""
                INSERT INTO posts (user_id, content, media_filename, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, content, media_filename, datetime.now()))
            conn.commit()

    # Fetch stories (<24h)
    cutoff = datetime.now() - timedelta(hours=24)
    stories = conn.execute("""
        SELECT s.id, s.media_filename, s.created_at,
               u.username, u.profile_picture
        FROM stories s
        JOIN users u ON s.user_id = u.id
        WHERE s.created_at >= ?
        ORDER BY s.created_at DESC
    """, (cutoff,)).fetchall()

    # Fetch posts with like counts
    raw_posts = conn.execute("""
        SELECT p.*, u.username, u.profile_picture
        FROM posts p
        JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC
    """).fetchall()

    posts = []
    for p in raw_posts:
        # Count likes
        like_row = conn.execute(
            "SELECT COUNT(*) AS c FROM likes WHERE post_id=?",
            (p["id"],)
        ).fetchone()
        like_count = like_row["c"] if like_row else 0

        # Has user liked it?
        user_like = conn.execute(
            "SELECT id FROM likes WHERE post_id=? AND user_id=?",
            (p["id"], user_id)
        ).fetchone()
        user_has_liked = True if user_like else False

        posts.append({
            "id": p["id"],
            "user_id": p["user_id"],
            "content": p["content"],
            "media_filename": p["media_filename"],
            "created_at": p["created_at"],
            "username": p["username"],
            "profile_picture": p["profile_picture"],
            "like_count": like_count,
            "user_has_liked": user_has_liked
        })

    conn.close()
    current_theme = get_current_theme()
    return render_template("feed.html",
                           stories=stories,
                           posts=posts,
                           current_user_id=user_id,
                           current_theme=current_theme)

@app.route("/like/<int:post_id>", methods=["POST"])
def like_post(post_id):
    user_id = get_current_user_id()
    if not user_id:
        flash("You must be logged in to like a post.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM likes WHERE post_id=? AND user_id=?",
        (post_id, user_id)
    ).fetchone()
    if existing:
        # unlike
        conn.execute("DELETE FROM likes WHERE id=?", (existing["id"],))
    else:
        # like
        conn.execute("INSERT INTO likes (post_id, user_id) VALUES (?, ?)",
                     (post_id, user_id))
    conn.commit()
    conn.close()
    return redirect(url_for("feed"))

@app.route("/delete_post/<int:post_id>", methods=["POST"])
def delete_post(post_id):
    """Owner can delete post."""
    user_id = get_current_user_id()
    if not user_id:
        flash("You must be logged in to delete a post.", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    post = conn.execute(
        "SELECT user_id FROM posts WHERE id=?",
        (post_id,)
    ).fetchone()
    if not post:
        flash("Post not found!", "error")
        conn.close()
        return redirect(url_for("feed"))

    if post["user_id"] != user_id:
        flash("You cannot delete someone else's post!", "error")
        conn.close()
        return redirect(url_for("feed"))

    # Delete post + associated likes
    conn.execute("DELETE FROM posts WHERE id=?", (post_id,))
    conn.execute("DELETE FROM likes WHERE post_id=?", (post_id,))
    conn.commit()
    conn.close()
    flash("Post deleted successfully!", "success")
    return redirect(url_for("feed"))

# ---------------- STORIES ----------------
@app.route("/upload_story", methods=["POST"])
def upload_story():
    user_id = get_current_user_id()
    if not user_id:
        flash("You must be logged in to upload a story.", "error")
        return redirect(url_for("login"))

    story_file = request.files.get("story_file")
    if story_file and story_file.filename and allowed_file(story_file.filename):
        secure_name = secure_filename(story_file.filename)
        story_path = os.path.join(app.config["UPLOAD_FOLDER"], secure_name)
        story_file.save(story_path)

        conn = get_db_connection()
        conn.execute("""
            INSERT INTO stories (user_id, media_filename, created_at)
            VALUES (?, ?, ?)
        """, (user_id, secure_name, datetime.now()))
        conn.commit()
        conn.close()

        flash("Story uploaded!", "success")
    else:
        flash("Invalid image/video file.", "error")

    return redirect(url_for("feed"))

# ---------------- PROFILE (self) ----------------
@app.route("/profile", methods=["GET", "POST"])
def profile():
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    # Upload new profile pic or update bio
    if request.method == "POST":
        pfp_file = request.files.get("profile_picture")
        new_bio = request.form.get("bio", "").strip()

        # Update PFP if uploaded
        if pfp_file and pfp_file.filename and allowed_file(pfp_file.filename):
            secure_name = secure_filename(pfp_file.filename)
            pfp_path = os.path.join(app.config["UPLOAD_FOLDER"], secure_name)
            pfp_file.save(pfp_path)
            conn.execute("""
                UPDATE users SET profile_picture=? WHERE id=?
            """, (secure_name, user_id))

        # Update Bio
        if new_bio:
            conn.execute("""
                UPDATE users SET bio=? WHERE id=?
            """, (new_bio, user_id))

        conn.commit()
        flash("Profile updated!", "success")

    # Re-fetch updated user
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    # Posts by user
    raw_posts = conn.execute("""
        SELECT p.*, u.username, u.profile_picture
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.user_id=?
        ORDER BY p.created_at DESC
    """, (user_id,)).fetchall()

    posts = []
    for p in raw_posts:
        like_row = conn.execute(
            "SELECT COUNT(*) AS c FROM likes WHERE post_id=?",
            (p["id"],)
        ).fetchone()
        like_count = like_row["c"] if like_row else 0
        posts.append({
            "id": p["id"],
            "content": p["content"],
            "media_filename": p["media_filename"],
            "created_at": p["created_at"],
            "username": p["username"],
            "profile_picture": p["profile_picture"],
            "like_count": like_count
        })

    conn.close()
    current_theme = get_current_theme()
    return render_template("profile.html", user=user, posts=posts, current_theme=current_theme)

# ---------------- PUBLIC PROFILE (others) ----------------
@app.route("/user/<username>")
def user_profile(username):
    user = get_user_by_username(username)
    if not user:
        flash("User does not exist!", "error")
        return redirect(url_for("feed"))

    conn = get_db_connection()
    raw_posts = conn.execute("""
        SELECT p.*, u.username, u.profile_picture
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE u.username=?
        ORDER BY p.created_at DESC
    """, (username,)).fetchall()

    posts = []
    for p in raw_posts:
        like_row = conn.execute(
            "SELECT COUNT(*) AS c FROM likes WHERE post_id=?",
            (p["id"],)
        ).fetchone()
        like_count = like_row["c"] if like_row else 0
        posts.append({
            "id": p["id"],
            "content": p["content"],
            "media_filename": p["media_filename"],
            "created_at": p["created_at"],
            "username": p["username"],
            "profile_picture": p["profile_picture"],
            "like_count": like_count
        })

    conn.close()

    # For demo, we just show post count. We could do followers/following if you implement it.
    user_post_count = len(posts)

    current_theme = get_current_theme()
    return render_template(
        "user_profile.html",
        user=user,
        posts=posts,
        user_post_count=user_post_count,
        user_followers_count=0,  # placeholders
        user_following_count=0,
        current_theme=current_theme
    )

# ---------------- MESSAGES / DIRECT MESSAGING ----------------
@app.route("/messages", methods=["GET"])
def messages_list():
    """Shows a list of conversations or a 'select user to chat' interface."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    conn = get_db_connection()
    # get all distinct users who have chatted with or from user_id
    rows = conn.execute("""
        SELECT DISTINCT u.id, u.username
        FROM messages m
        JOIN users u 
         ON (u.id = m.sender_id OR u.id = m.recipient_id)
        WHERE m.sender_id=? OR m.recipient_id=?
          AND u.id <> ?
    """, (user_id, user_id, user_id)).fetchall()

    # This is a naive approach: just gather unique conversation partners
    conversation_partners = [dict(row) for row in rows]
    conn.close()

    current_theme = get_current_theme()
    return render_template("messages.html", 
                           conversation_partners=conversation_partners,
                           current_theme=current_theme)

@app.route("/messages/<username>", methods=["GET", "POST"])
def direct_messages(username):
    """Direct messaging between the current user and user with <username>."""
    user_id = get_current_user_id()
    if not user_id:
        return redirect(url_for("login"))

    # find the other user
    other_user = get_user_by_username(username)
    if not other_user:
        flash("User does not exist!", "error")
        return redirect(url_for("messages_list"))

    other_user_id = other_user["id"]

    conn = get_db_connection()

    if request.method == "POST":
        # send a new message
        content = request.form.get("content", "").strip()
        if content:
            conn.execute("""
                INSERT INTO messages (sender_id, recipient_id, content, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, other_user_id, content, datetime.now()))
            conn.commit()

    # fetch conversation (both directions)
    msgs = conn.execute("""
        SELECT m.*, s.username as sender_name, r.username as recipient_name
        FROM messages m
        JOIN users s ON s.id = m.sender_id
        JOIN users r ON r.id = m.recipient_id
        WHERE (m.sender_id=? AND m.recipient_id=?)
           OR (m.sender_id=? AND m.recipient_id=?)
        ORDER BY m.created_at ASC
    """, (user_id, other_user_id, other_user_id, user_id)).fetchall()
    conn.close()

    # convert to list of dict for easy usage
    messages_list = []
    for msg in msgs:
        messages_list.append({
            "id": msg["id"],
            "content": msg["content"],
            "created_at": msg["created_at"],
            "sender_id": msg["sender_id"],
            "sender_name": msg["sender_name"],
            "recipient_id": msg["recipient_id"],
            "recipient_name": msg["recipient_name"]
        })

    current_theme = get_current_theme()
    return render_template("messages.html",
                           conversation=True,
                           other_user=other_user,
                           messages_list=messages_list,
                           current_theme=current_theme)

# ---------------- SERVE UPLOADS ----------------
@app.route("/uploads/<filename>")
def uploads(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
