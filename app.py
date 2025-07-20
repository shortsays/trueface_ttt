from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
import os
import cv2
import sqlite3
import random
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
DB_FILE = 'users.db'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['STATIC_FOLDER'] = STATIC_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max upload

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize database
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Index
@app.route('/')
def index():
    return render_template('index.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[0], password):
            session['user'] = username
            return redirect('/home')
        else:
            return render_template('login_error.html')
    return render_template('login.html')

# Signup
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        if not email.endswith("@gmail.com"):
            return render_template('signup_error.html', message="Only Gmail addresses are allowed!")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                           (username, email, password))
            conn.commit()
        except sqlite3.IntegrityError:
            return render_template('signup_error.html', message="Username or Gmail already exists!")
        finally:
            conn.close()

        return render_template('signup_success.html', username=username)

    return render_template('signup.html')

# Home
@app.route('/home')
def home():
    if 'user' not in session:
        return redirect('/')
    return render_template('index.html')

# Logout
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# Select mode
@app.route('/select_mode')
def select_mode():
    if 'user' not in session:
        return redirect('/')
    return render_template('select_mode.html')

# Video Upload Page
@app.route('/video_upload_page')
def video_upload_page():
    if 'user' not in session:
        return redirect('/')
    return render_template('video_upload.html')

# Upload & Detect
@app.route('/upload', methods=['POST'])
def upload():
    if 'user' not in session:
        return redirect('/')

    video = request.files['video']
    if not video or not allowed_file(video.filename):
        return render_template('result.html', message="❌ Invalid file type.", from_photo=False)

    filename = secure_filename(video.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    video.save(filepath)

    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        return render_template('result.html', message="⚠️ Unable to open video.", from_photo=False)

    original_fps = cap.get(cv2.CAP_PROP_FPS)
    target_fps = 5
    frame_interval = max(1, int(original_fps / target_fps))
    max_frames = 50

    prev_gray = None
    total_blur_score = 0
    total_edge_change = 0
    frame_count = 0
    is_suspected = False

    while frame_count < max_frames and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (3, 3), 0)

            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
            total_blur_score += blur_score

            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                diff_score = diff.mean()
                total_edge_change += diff_score
                if diff_score < 3.0:
                    is_suspected = True

            prev_gray = gray
        frame_count += 1

    cap.release()

    avg_blur = total_blur_score / frame_count if frame_count > 0 else 0
    avg_motion = total_edge_change / (frame_count - 1) if frame_count > 1 else 0

    blur_threshold = 50
    motion_threshold = 3.0

    result = (avg_blur < blur_threshold and avg_motion < motion_threshold) or is_suspected

    message = "🛑 Deepfake Detected!" if result else "✅ Video Looks Real."
    detail = f"Frames: {frame_count}, Avg Blur: {avg_blur:.2f}, Motion: {avg_motion:.2f}"
    processing_delay = random.randint(3, 6)

    return render_template(
        'result.html',
        message=message,
        detail=detail,
        processing_delay=processing_delay,
        from_photo=False
    )

# Static files
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.config['STATIC_FOLDER'], filename)


if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    if not os.path.exists(STATIC_FOLDER):
        os.makedirs(STATIC_FOLDER)
    init_db()
    app.run(debug=True)
