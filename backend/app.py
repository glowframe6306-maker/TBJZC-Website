import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import re
from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / 'frontend'
IMAGES_DIR = ROOT_DIR / 'images'
DB_PATH = ROOT_DIR / 'backend' / 'tbjzc_cms.db'

IS_VERCEL = os.environ.get('VERCEL') == '1'
if IS_VERCEL:
    FEEDBACK_DIR = Path('/tmp/feedback')
else:
    FEEDBACK_DIR = ROOT_DIR / 'Feedback'
FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'tbjzc-admin-secret-change-me')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def iso_now():
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')


def ensure_session_valid():
    expires_at = session.get('expires_at')
    if expires_at:
        try:
            if datetime.utcnow() > datetime.fromisoformat(expires_at):
                session.clear()
                return False
        except ValueError:
            session.clear()
            return False
    return 'admin_id' in session


def current_admin_record():
    if not ensure_session_valid():
        return None
    admin_id = session.get('admin_id')
    if not admin_id:
        return None
    conn = get_db()
    admin = conn.execute('SELECT * FROM admins WHERE id = ?', (admin_id,)).fetchone()
    conn.close()
    return dict(admin) if admin else None


def require_admin(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not ensure_session_valid():
            return jsonify(error='Authentication required.'), 401
        admin = current_admin_record()
        if not admin or admin.get('status') != 'active':
            session.clear()
            return jsonify(error='Session expired or account disabled.'), 401
        return f(*args, **kwargs)

    return wrapper


def require_roles(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            admin = current_admin_record()
            if not admin:
                return jsonify(error='Authentication required.'), 401
            if admin.get('role') not in roles:
                return jsonify(error='You do not have permission to perform this action.'), 403
            return f(*args, **kwargs)

        return wrapper

    return decorator


def log_activity(action, target=None, details=None, result='success', admin_id=None):
    conn = get_db()
    conn.execute(
        '''
        INSERT INTO activity_logs (admin_id, action, target, details, result, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        (
            admin_id,
            action,
            target,
            details,
            result,
            iso_now(),
        ),
    )
    conn.commit()
    conn.close()


def ensure_default_data():
    conn = get_db()
    conn.execute('PRAGMA foreign_keys = ON')
    conn.executescript(
        '''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'CONTENT_ADMIN',
            status TEXT DEFAULT 'active',
            created_at TEXT,
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS school (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            name TEXT,
            address TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            principal_name TEXT,
            vice_principal TEXT,
            founded_year INTEGER,
            description TEXT,
            mission TEXT,
            vision TEXT,
            motto TEXT,
            logo_url TEXT,
            favicon_url TEXT,
            facebook TEXT,
            twitter TEXT,
            instagram TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            short_description TEXT,
            content TEXT,
            category TEXT,
            author TEXT,
            status TEXT,
            featured_image TEXT,
            tags TEXT,
            publish_date TEXT,
            created_at TEXT,
            updated_at TEXT,
            views INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT,
            priority TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT,
            attachment TEXT,
            featured INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            original_name TEXT,
            url TEXT,
            mime_type TEXT,
            file_size INTEGER,
            width INTEGER,
            height INTEGER,
            category TEXT,
            uploaded_by TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS login_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            user_type TEXT,
            profile_info TEXT,
            request_id TEXT,
            status TEXT DEFAULT 'pending',
            rejection_reason TEXT,
            created_at TEXT,
            reviewed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            email TEXT,
            subject TEXT,
            message TEXT,
            status TEXT DEFAULT 'unread',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            body TEXT,
            type TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target TEXT,
            details TEXT,
            result TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            website_name TEXT,
            admin_email TEXT,
            timezone TEXT,
            date_format TEXT,
            theme TEXT,
            sidebar_style TEXT,
            session_timeout INTEGER,
            password_policy TEXT,
            login_attempt_limit INTEGER,
            created_at TEXT,
            updated_at TEXT
        );
        '''
    )

    admin_count = conn.execute('SELECT COUNT(*) FROM admins').fetchone()[0]
    if admin_count == 0:
        conn.execute(
            'INSERT INTO admins (username, email, full_name, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                'admin',
                'admin@tbjzc.com',
                'Super Administrator',
                generate_password_hash('admin123'),
                'SUPER_ADMIN',
                'active',
                iso_now(),
            ),
        )

    school_count = conn.execute('SELECT COUNT(*) FROM school').fetchone()[0]
    if school_count == 0:
        conn.execute(
            '''
            INSERT INTO school (
                id, name, address, phone, email, website, principal_name, vice_principal,
                founded_year, description, mission, vision, motto, logo_url, favicon_url,
                facebook, twitter, instagram, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                1,
                'T.B. Jaya Zahira College',
                '24, Sir James Peiris Mawatha, Colombo 02',
                '0112 300 338',
                'tbjzc2013@gmail.com',
                'https://tbjzc.edu.lk',
                'Mr. M.R.M. Manzil',
                'Vice Principal',
                1921,
                'A premier school dedicated to academic excellence, discipline and character formation.',
                'To nurture confident, responsible and knowledgeable learners.',
                'To be a leading centre of excellence in education and community development.',
                'The learned is one who practices what he knows.',
                '/images/LOGO.png',
                '/images/LOGO.png',
                'https://web.facebook.com/T.BJZAHIRAOFFICIAL',
                '',
                '',
                iso_now(),
            ),
        )

    settings_count = conn.execute('SELECT COUNT(*) FROM settings').fetchone()[0]
    if settings_count == 0:
        conn.execute(
            '''
            INSERT INTO settings (
                id, website_name, admin_email, timezone, date_format,
                theme, sidebar_style, session_timeout, password_policy,
                login_attempt_limit, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                1,
                'TBJZC Admin Portal',
                'admin@tbjzc.com',
                'Asia/Colombo',
                'YYYY-MM-DD',
                'system',
                'default',
                480,
                'Minimum 8 characters',
                5,
                iso_now(),
                iso_now(),
            ),
        )
    conn.commit()
    conn.close()


ensure_default_data()


def fetch_school():
    conn = get_db()
    row = conn.execute('SELECT * FROM school WHERE id = 1').fetchone()
    conn.close()
    return dict(row) if row else {}


@app.before_request
def check_session_timeout():
    public_admin_routes = {'/api/admin/login', '/api/admin/session', '/api/admin/health'}
    if request.path.startswith('/api/admin') and request.path not in public_admin_routes:
        if not ensure_session_valid():
            return jsonify(error='Authentication required.'), 401


@app.route('/')
def frontpage():
    return send_from_directory(str(FRONTEND_DIR), 'index.html')


@app.route('/admin')
@app.route('/admin/')
def admin_index():
    return send_from_directory(str(FRONTEND_DIR), 'admin.html')


@app.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(str(IMAGES_DIR), filename)


@app.route('/<path:filename>')
def serve_static(filename):
    file_path = FRONTEND_DIR / filename
    if file_path.exists() and file_path.is_file():
        return send_from_directory(str(FRONTEND_DIR), filename)
    return send_from_directory(str(FRONTEND_DIR), 'index.html')


@app.route('/health')
def health():
    return jsonify(status='ok', feedback_dir=str(FEEDBACK_DIR), is_vercel=IS_VERCEL)


@app.route('/info')
def info():
    return jsonify(fetch_school())


@app.route('/clubs')
def clubs():
    clubs_data = {
        'Sinhala Literary Association': {'teacher_in_charge': 'MRS. SRIYANI EKANAYAKE', 'president': 'M.A. ABDUL AZEEZ'},
        'Tamil Literary Association': {'teacher_in_charge': 'MRS. M. M. F. MINHA', 'president': 'M.I.A.ASLAM'},
        'English Literary Association': {'teacher_in_charge': 'MRS. FAZREEN MOHAMED', 'president': 'M.RM.ALFATH'},
    }
    q = request.args.get('q', '').lower()
    if q:
        filtered = {k: v for k, v in clubs_data.items() if q in k.lower()}
        return jsonify(filtered)
    return jsonify(clubs_data)


@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        email = (data.get('email') or '').strip()
        message = (data.get('message') or '').strip()

        if not name or not email or not message:
            return jsonify(error='Name, email, and feedback message are required.'), 400

        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            return jsonify(error='A valid email address is required.'), 400

        if len(message.split()) > 700:
            return jsonify(error='Feedback message must be 700 words or fewer.'), 400

        try:
            feedback_path = FEEDBACK_DIR / 'Feedback.txt'
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            feedback_entry = (
                f"Name - {name}\nEmail - {email}\nSubmitted - {timestamp}\n"
                "________________________________\nMessage:\n"
                f"{message}\n\n"
            )
            with open(feedback_path, 'a', encoding='utf-8') as f:
                f.write(feedback_entry)
        except IOError as io_err:
            return jsonify(error=f'Failed to save feedback: {str(io_err)}'), 500

        conn = get_db()
        conn.execute(
            'INSERT INTO messages (sender, email, subject, message, status, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (name, email, 'Website Feedback', message, 'unread', iso_now()),
        )
        conn.execute(
            'INSERT INTO notifications (title, body, type, is_read, created_at) VALUES (?, ?, ?, ?, ?)',
            ('New feedback received', f'{name} submitted website feedback.', 'feedback', 0, iso_now()),
        )
        conn.commit()
        conn.close()
        return jsonify(message='Feedback saved successfully.')
    except Exception as exc:
        import traceback
        error_msg = f'{str(exc)} | {traceback.format_exc()}'
        return jsonify(error=error_msg), 500


@app.route('/search')
def search():
    q = request.args.get('q', '').lower()
    results = {}
    if q:
        clubs_data = {
            'Sinhala Literary Association': {'teacher_in_charge': 'MRS. SRIYANI EKANAYAKE'},
            'Tamil Literary Association': {'teacher_in_charge': 'MRS. M. M. F. MINHA'},
            'English Literary Association': {'teacher_in_charge': 'MRS. FAZREEN MOHAMED'},
        }
        results = {k: v for k, v in clubs_data.items() if q in k.lower()}
    return jsonify(results)


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    password = payload.get('password') or ''
    if not username or not password:
        return jsonify(error='Username and password are required.'), 400

    conn = get_db()
    admin = conn.execute(
        'SELECT * FROM admins WHERE username = ? OR email = ?',
        (username, username),
    ).fetchone()
    conn.close()

    if not admin or not check_password_hash(admin['password_hash'], password):
        return jsonify(error='Invalid username or password.'), 401

    if admin['status'] != 'active':
        return jsonify(error='This account is not active.'), 403

    session.permanent = bool(payload.get('remember_me'))
    session['admin_id'] = admin['id']
    session['admin'] = {
        'id': admin['id'],
        'username': admin['username'],
        'email': admin['email'],
        'full_name': admin['full_name'],
        'role': admin['role'],
    }
    session['expires_at'] = (datetime.utcnow() + (timedelta(days=30) if payload.get('remember_me') else timedelta(hours=8))).isoformat()

    conn = get_db()
    conn.execute('UPDATE admins SET last_login = ? WHERE id = ?', (iso_now(), admin['id']))
    conn.commit(); conn.close()
    log_activity('admin_login', target='system', details='Admin logged in successfully.', admin_id=admin['id'])

    return jsonify({
        'message': 'Login successful.',
        'admin': session['admin'],
    })


@app.route('/api/admin/logout', methods=['POST'])
@require_admin
def admin_logout():
    admin = current_admin_record()
    log_activity('admin_logout', target='system', details='Admin logged out.', admin_id=admin['id'])
    session.clear()
    return jsonify(message='Logged out successfully.')


@app.route('/api/admin/session')
def admin_session():
    if not ensure_session_valid():
        return jsonify(logged_in=False), 200
    admin = current_admin_record()
    return jsonify({'logged_in': True, 'admin': session.get('admin', admin)})


@app.route('/api/admin/dashboard/summary')
@require_admin
def dashboard_summary():
    conn = get_db()
    stats = {
        'total_posts': conn.execute('SELECT COUNT(*) FROM posts').fetchone()[0],
        'total_announcements': conn.execute('SELECT COUNT(*) FROM announcements').fetchone()[0],
        'total_images': conn.execute('SELECT COUNT(*) FROM media').fetchone()[0],
        'pending_login_approvals': conn.execute("SELECT COUNT(*) FROM login_requests WHERE status = 'pending'").fetchone()[0],
        'messages': conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],
        'feedback': conn.execute("SELECT COUNT(*) FROM messages WHERE subject = 'Website Feedback'").fetchone()[0],
        'website_visitors': 0,
        'active_admins': conn.execute("SELECT COUNT(*) FROM admins WHERE status = 'active'").fetchone()[0],
    }

    recent_activity = []
    for table_name, select_sql, label in [
        ('posts', 'SELECT id, title AS name, status, created_at FROM posts ORDER BY created_at DESC LIMIT 5', 'post'),
        ('announcements', 'SELECT id, title AS name, status, created_at FROM announcements ORDER BY created_at DESC LIMIT 5', 'announcement'),
        ('media', 'SELECT id, original_name AS name, created_at FROM media ORDER BY created_at DESC LIMIT 5', 'media'),
        ('login_requests', 'SELECT id, name, status, created_at FROM login_requests ORDER BY created_at DESC LIMIT 5', 'login_request'),
        ('activity_logs', 'SELECT id, action AS name, created_at FROM activity_logs ORDER BY created_at DESC LIMIT 5', 'admin_activity'),
    ]:
        for row in conn.execute(select_sql).fetchall():
            recent_activity.append({
                'type': label,
                'name': row['name'] or 'Record',
                'status': row['status'] if 'status' in row.keys() else 'completed',
                'created_at': row['created_at'],
            })
    recent_activity = sorted(recent_activity, key=lambda item: item.get('created_at', ''), reverse=True)[:10]
    conn.close()
    return jsonify({'stats': stats, 'recent_activity': recent_activity})


@app.route('/api/admin/posts', methods=['GET', 'POST'])
@require_admin
def manage_posts():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
        return jsonify([dict(row) for row in rows])

    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    if not title:
        return jsonify(error='Post title is required.'), 400

    conn.execute(
        '''
        INSERT INTO posts (title, short_description, content, category, author, status, featured_image, tags, publish_date, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            title,
            payload.get('short_description') or '',
            payload.get('content') or '',
            payload.get('category') or 'General',
            payload.get('author') or session.get('admin', {}).get('full_name', 'Administrator'),
            payload.get('status') or 'draft',
            payload.get('featured_image') or '',
            ','.join(payload.get('tags') or []),
            payload.get('publish_date') or iso_now(),
            iso_now(),
            iso_now(),
        ),
    )
    conn.commit()
    post_id = conn.execute('SELECT last_insert_rowid() AS id').fetchone()['id']
    log_activity('create_post', target=f'post:{post_id}', details=f'Created post: {title}', admin_id=session['admin_id'])
    conn.close()
    return jsonify(message='Post created successfully.'), 201


@app.route('/api/admin/announcements', methods=['GET', 'POST'])
@require_admin
def manage_announcements():
    conn = get_db()
    if request.method == 'GET':
        rows = conn.execute('SELECT * FROM announcements ORDER BY created_at DESC').fetchall()
        return jsonify([dict(row) for row in rows])

    payload = request.get_json(silent=True) or {}
    title = (payload.get('title') or '').strip()
    if not title:
        return jsonify(error='Announcement title is required.'), 400

    conn.execute(
        '''
        INSERT INTO announcements (title, content, priority, start_date, end_date, status, attachment, featured, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            title,
            payload.get('content') or '',
            payload.get('priority') or 'Normal',
            payload.get('start_date') or iso_now(),
            payload.get('end_date') or '',
            payload.get('status') or 'published',
            payload.get('attachment') or '',
            1 if payload.get('featured') else 0,
            iso_now(),
            iso_now(),
        ),
    )
    conn.commit()
    announcement_id = conn.execute('SELECT last_insert_rowid() AS id').fetchone()['id']
    log_activity('create_announcement', target=f'announcement:{announcement_id}', details=f'Created announcement: {title}', admin_id=session['admin_id'])
    conn.close()
    return jsonify(message='Announcement created successfully.'), 201


@app.route('/api/admin/media', methods=['GET', 'POST'])
@require_admin
def manage_media():
    if request.method == 'GET':
        conn = get_db()
        rows = conn.execute('SELECT * FROM media ORDER BY created_at DESC').fetchall()
        conn.close()
        return jsonify([dict(row) for row in rows])

    if request.files and request.files.get('file'):
        uploaded = request.files['file']
        if uploaded.filename == '':
            return jsonify(error='Please choose a file to upload.'), 400
        filename = secure_filename(uploaded.filename)
        upload_dir = IMAGES_DIR / 'uploads'
        upload_dir.mkdir(parents=True, exist_ok=True)
        destination = upload_dir / filename
        uploaded.save(destination)
        url = f'/images/uploads/{filename}'
        conn = get_db()
        conn.execute(
            'INSERT INTO media (filename, original_name, url, mime_type, file_size, category, uploaded_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (
                filename,
                uploaded.filename,
                url,
                uploaded.mimetype or 'image/png',
                os.path.getsize(destination),
                request.form.get('category', 'general'),
                session.get('admin', {}).get('full_name', 'Administrator'),
                iso_now(),
            ),
        )
        conn.commit(); conn.close()
        log_activity('upload_media', target=url, details=f'Uploaded image {filename}', admin_id=session['admin_id'])
        return jsonify(message='Image uploaded successfully.', url=url)

    payload = request.get_json(silent=True) or {}
    url = payload.get('url') or ''
    if not url:
        return jsonify(error='Media URL is required.'), 400
    conn = get_db()
    conn.execute(
        'INSERT INTO media (filename, original_name, url, mime_type, file_size, category, uploaded_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (
            url.rsplit('/', 1)[-1],
            url.rsplit('/', 1)[-1],
            url,
            'image/webp',
            0,
            payload.get('category') or 'general',
            session.get('admin', {}).get('full_name', 'Administrator'),
            iso_now(),
        ),
    )
    conn.commit(); conn.close()
    return jsonify(message='Media saved successfully.')


@app.route('/api/admin/school')
@require_admin
def get_school():
    return jsonify(fetch_school())


@app.route('/api/admin/school', methods=['PUT'])
@require_admin
def update_school():
    payload = request.get_json(silent=True) or {}
    conn = get_db()
    conn.execute(
        '''
        UPDATE school SET
            name = ?, address = ?, phone = ?, email = ?, website = ?, principal_name = ?,
            vice_principal = ?, founded_year = ?, description = ?, mission = ?, vision = ?,
            motto = ?, logo_url = ?, favicon_url = ?, facebook = ?, twitter = ?, instagram = ?, updated_at = ?
        WHERE id = 1
        ''',
        (
            payload.get('name') or 'T.B. Jaya Zahira College',
            payload.get('address') or '',
            payload.get('phone') or '',
            payload.get('email') or '',
            payload.get('website') or '',
            payload.get('principal_name') or '',
            payload.get('vice_principal') or '',
            payload.get('founded_year') or 1921,
            payload.get('description') or '',
            payload.get('mission') or '',
            payload.get('vision') or '',
            payload.get('motto') or '',
            payload.get('logo_url') or '/images/LOGO.png',
            payload.get('favicon_url') or '/images/LOGO.png',
            payload.get('facebook') or '',
            payload.get('twitter') or '',
            payload.get('instagram') or '',
            iso_now(),
        ),
    )
    conn.commit(); conn.close()
    log_activity('update_school', target='school_details', details='School information updated.', admin_id=session['admin_id'])
    return jsonify(message='School details updated successfully.')


@app.route('/api/admin/login-requests', methods=['GET'])
@require_admin
def login_requests():
    conn = get_db()
    rows = conn.execute('SELECT * FROM login_requests ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/login-requests', methods=['POST'])
@require_admin
@require_roles('SUPER_ADMIN', 'CONTENT_ADMIN')
def create_login_request():
    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    email = (payload.get('email') or '').strip()
    if not name or not email:
        return jsonify(error='Name and email are required.'), 400
    request_id = str(uuid.uuid4())[:8]
    conn = get_db()
    conn.execute(
        'INSERT INTO login_requests (name, email, user_type, profile_info, request_id, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (name, email, payload.get('user_type') or 'Student', payload.get('profile_info') or '', request_id, 'pending', iso_now()),
    )
    conn.commit(); conn.close()
    return jsonify(message='Login request created successfully.', request_id=request_id)


@app.route('/api/admin/login-requests/<int:request_id>/approve', methods=['POST'])
@require_admin
@require_roles('SUPER_ADMIN')
def approve_login_request(request_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM login_requests WHERE id = ?', (request_id,)).fetchone()
    if not row:
        conn.close(); return jsonify(error='Login request not found.'), 404
    conn.execute("UPDATE login_requests SET status = 'approved', reviewed_at = ? WHERE id = ?", (iso_now(), request_id))
    conn.commit(); conn.close()
    log_activity('approve_login_request', target=f'login_request:{request_id}', details=f'Approved request for {row["email"]}', admin_id=session['admin_id'])
    return jsonify(message='Login request approved.')


@app.route('/api/admin/messages', methods=['GET'])
@require_admin
def list_messages():
    conn = get_db()
    rows = conn.execute('SELECT * FROM messages ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/notifications', methods=['GET'])
@require_admin
def list_notifications():
    conn = get_db()
    rows = conn.execute('SELECT * FROM notifications ORDER BY created_at DESC LIMIT 8').fetchall()
    conn.close()
    return jsonify({
        'items': [dict(row) for row in rows],
        'unread_count': sum(1 for row in rows if row['is_read'] == 0),
    })


@app.route('/api/admin/recent-activity', methods=['GET'])
@require_admin
def recent_activity():
    conn = get_db()
    rows = conn.execute('SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 10').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/users', methods=['GET'])
@require_admin
def list_users():
    conn = get_db()
    rows = conn.execute('SELECT id, username, email, full_name, role, status, last_login, created_at FROM admins ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/settings', methods=['GET', 'PUT'])
@require_admin
def admin_settings():
    conn = get_db()
    if request.method == 'GET':
        row = conn.execute('SELECT * FROM settings WHERE id = 1').fetchone()
        conn.close()
        return jsonify(dict(row) if row else {})

    payload = request.get_json(silent=True) or {}
    conn.execute(
        '''
        UPDATE settings SET website_name = ?, admin_email = ?, timezone = ?, date_format = ?, theme = ?, sidebar_style = ?,
        session_timeout = ?, password_policy = ?, login_attempt_limit = ?, updated_at = ? WHERE id = 1
        ''',
        (
            payload.get('website_name') or 'TBJZC Admin Portal',
            payload.get('admin_email') or 'admin@tbjzc.com',
            payload.get('timezone') or 'Asia/Colombo',
            payload.get('date_format') or 'YYYY-MM-DD',
            payload.get('theme') or 'system',
            payload.get('sidebar_style') or 'default',
            int(payload.get('session_timeout') or 480),
            payload.get('password_policy') or 'Minimum 8 characters',
            int(payload.get('login_attempt_limit') or 5),
            iso_now(),
        ),
    )
    conn.commit(); conn.close()
    return jsonify(message='Settings updated successfully.')


@app.route('/api/admin/health')
def admin_health_check():
    return jsonify(status='ok', db_path=str(DB_PATH))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
