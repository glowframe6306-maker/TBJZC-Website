import logging
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_USER_ROLES = {'DEVELOPER', 'CYBER SECURITY', 'MAIN ADMIN', 'ADMIN'}
ALL_ADMIN_ROLES = {'SUPER_ADMIN', *ALLOWED_USER_ROLES}
POST_SECTIONS = [
    {'value': 'houses', 'label': 'HOUSES'},
    {'value': 'clubs-and-societies', 'label': 'CLUBS AND SOCIETIES'},
    {'value': 'achievements', 'label': 'ACHIEVEMENTS'},
    {'value': 'latest-news', 'label': 'LATEST NEWS'},
    {'value': 'sports', 'label': 'SPORTS'},
]
POST_SECTION_VALUES = {section['value'] for section in POST_SECTIONS}
EXCLUDED_POST_SECTIONS = {
    'about-us', 'academic-staff', 'visions-and-missions', 'examination-results', 'feedback-and-suggestions',
}

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / 'frontend'
IMAGES_DIR = ROOT_DIR / 'images'

IS_VERCEL = os.environ.get('VERCEL') == '1'
if IS_VERCEL:
    DATA_DIR = Path('/tmp')
    FEEDBACK_DIR = Path('/tmp/feedback')
else:
    DATA_DIR = ROOT_DIR / 'backend'
    FEEDBACK_DIR = ROOT_DIR / 'Feedback'

DATA_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'tbjzc_cms.db'
UPLOADS_DIR = DATA_DIR / 'uploads' if IS_VERCEL else IMAGES_DIR / 'uploads'

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path='')
secret_key = os.environ.get('FLASK_SECRET_KEY')
if not secret_key:
    if IS_VERCEL:
        logger.error('FLASK_SECRET_KEY is missing in the Vercel runtime. Set FLASK_SECRET_KEY in Vercel to keep admin sessions stable across requests.')
        raise RuntimeError('FLASK_SECRET_KEY must be configured in Vercel for secure admin sessions.')
    logger.warning('FLASK_SECRET_KEY is missing; generating a temporary development-only key.')
    secret_key = os.urandom(32).hex()
app.secret_key = secret_key
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = IS_VERCEL
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['SESSION_REFRESH_EACH_REQUEST'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)


def normalize_env_value(value):
    if value is None:
        return ''
    return value.strip().strip('"').strip("'")


def get_admin_credentials():
    username = normalize_env_value(os.environ.get('ADMIN_USERNAME'))
    password = normalize_env_value(os.environ.get('ADMIN_PASSWORD'))
    logger.info('ADMIN_USERNAME configured: %s', bool(username))
    logger.info('ADMIN_PASSWORD configured: %s', bool(password))
    return username, password


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
                logger.info('Session expired for admin request: %s', request.path)
                return False
        except ValueError:
            session.clear()
            logger.warning('Session timestamp invalid for request: %s', request.path)
            return False
    is_valid = 'admin_id' in session
    if not is_valid:
        logger.info('No active admin session for request: %s', request.path)
    return is_valid


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


def request_device_info():
    user_agent = request.headers.get('User-Agent', 'Unknown')[:240]
    lowered = user_agent.lower()
    browser = 'Other'
    for marker, label in [('edg/', 'Edge'), ('chrome/', 'Chrome'), ('firefox/', 'Firefox'), ('safari/', 'Safari')]:
        if marker in lowered:
            browser = label
            break
    operating_system = 'Other'
    for marker, label in [('windows', 'Windows'), ('android', 'Android'), ('iphone', 'iOS'), ('ipad', 'iOS'), ('mac os', 'macOS'), ('linux', 'Linux')]:
        if marker in lowered:
            operating_system = label
            break
    device_type = 'Mobile' if any(marker in lowered for marker in ('mobile', 'android', 'iphone', 'ipad')) else 'Desktop'
    return f'{operating_system} / {browser} / {device_type}'


def save_post_images(files):
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    upload_dir = UPLOADS_DIR
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    try:
        for uploaded in files[:10]:
            if not uploaded or not uploaded.filename:
                continue
            filename = secure_filename(uploaded.filename)
            extension = Path(filename).suffix.lower()
            if extension not in allowed_extensions or not (uploaded.mimetype or '').startswith('image/'):
                raise ValueError('Only JPG, PNG, GIF, and WEBP images are allowed.')
            stored_name = f'{uuid.uuid4().hex}{extension}'
            destination = upload_dir / stored_name
            uploaded.save(destination)
            if destination.stat().st_size > 5 * 1024 * 1024:
                destination.unlink(missing_ok=True)
                raise ValueError('Each image must be 5 MB or smaller.')
            saved.append(f'/api/uploads/{stored_name}' if IS_VERCEL else f'/images/uploads/{stored_name}')
    except OSError as error:
        for url in saved:
            (upload_dir / Path(url).name).unlink(missing_ok=True)
        raise ValueError(f'Unable to store uploaded images: {error}') from error
    except Exception:
        for url in saved:
            (upload_dir / Path(url).name).unlink(missing_ok=True)
        raise
    return saved


def serialize_post(row):
    post = dict(row)
    try:
        post['images'] = json.loads(post.get('images') or '[]')
    except (TypeError, json.JSONDecodeError):
        post['images'] = []
    if not post['images'] and post.get('featured_image'):
        post['images'] = [post['featured_image']]
    if IS_VERCEL:
        post['images'] = [
            f'/api/uploads/{Path(image).name}' if isinstance(image, str) and image.startswith('/images/uploads/') else image
            for image in post['images']
        ]
    return post


def log_security_alert(alert_type, description, severity='medium', module=None, admin_id=None, account=None):
    conn = get_db()
    conn.execute(
        '''
        INSERT INTO security_alerts (
            alert_type, description, account, device_info, module, severity, is_read, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        ''',
        (alert_type, description, account, request_device_info(), module or request.path, severity, iso_now()),
    )
    conn.commit()
    conn.close()


def record_activity(action, target=None, details=None, result='success', admin_id=None, actor_name=None, actor_email=None):
    conn = get_db()
    if admin_id and not actor_name:
        actor = conn.execute('SELECT full_name, email FROM admins WHERE id = ?', (admin_id,)).fetchone()
        if actor:
            actor_name = actor['full_name']
            actor_email = actor['email']
    conn.execute(
        '''
        INSERT INTO activity_logs (
            admin_id, action, target, details, result, actor_name, actor_email, device_info, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (admin_id, action, target, details, result, actor_name, actor_email, request_device_info(), iso_now()),
    )
    conn.commit()
    conn.close()


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
                log_security_alert(
                    'PERMISSION ALERT',
                    f'{admin.get("full_name", "An admin")} attempted {request.method} {request.path}.',
                    severity='high',
                    module=request.path,
                    admin_id=admin.get('id'),
                    account=admin.get('email'),
                )
                record_activity(
                    'permission_denied', target=request.path,
                    details='Protected action denied by role policy.', result='denied',
                    admin_id=admin.get('id'),
                )
                return jsonify(error='You do not have permission to perform this action.'), 403
            return f(*args, **kwargs)

        return wrapper

    return decorator


def log_activity(action, target=None, details=None, result='success', admin_id=None):
    record_activity(action, target, details, result, admin_id)


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
            section TEXT,
            author_id INTEGER,
            author TEXT,
            status TEXT,
            featured_image TEXT,
            images TEXT,
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
            username TEXT,
            email TEXT,
            user_type TEXT,
            profile_info TEXT,
            request_id TEXT,
            requested_role TEXT,
            device_info TEXT,
            admin_id INTEGER,
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
            actor_name TEXT,
            actor_email TEXT,
            device_info TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS security_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            description TEXT NOT NULL,
            account TEXT,
            device_info TEXT,
            module TEXT,
            severity TEXT DEFAULT 'medium',
            is_read INTEGER DEFAULT 0,
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

    for table_name, column_name, column_definition in [
        ('login_requests', 'requested_role', 'TEXT'),
        ('login_requests', 'username', 'TEXT'),
        ('login_requests', 'device_info', 'TEXT'),
        ('login_requests', 'admin_id', 'INTEGER'),
        ('activity_logs', 'actor_name', 'TEXT'),
        ('activity_logs', 'actor_email', 'TEXT'),
        ('activity_logs', 'device_info', 'TEXT'),
        ('posts', 'section', 'TEXT'),
        ('posts', 'author_id', 'INTEGER'),
        ('posts', 'images', 'TEXT'),
    ]:
        existing_columns = {row['name'] for row in conn.execute(f'PRAGMA table_info({table_name})').fetchall()}
        if column_name not in existing_columns:
            conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}')
    admin_columns = {row['name'] for row in conn.execute('PRAGMA table_info(admins)').fetchall()}
    if 'profile_picture' in admin_columns:
        conn.execute('ALTER TABLE admins DROP COLUMN profile_picture')
    for section in POST_SECTIONS:
        conn.execute(
            "UPDATE posts SET section = ? WHERE (section IS NULL OR section = '') AND lower(replace(category, ' ', '-')) = ?",
            (section['value'], section['value']),
        )

    admin_username, admin_password = get_admin_credentials()
    admin_count = conn.execute('SELECT COUNT(*) FROM admins').fetchone()[0]
    if admin_count == 0 and admin_username and admin_password:
        conn.execute(
            'INSERT INTO admins (username, email, full_name, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                admin_username,
                f'{admin_username}@tbjzc.com',
                'Super Administrator',
                generate_password_hash(admin_password),
                'SUPER_ADMIN',
                'active',
                iso_now(),
            ),
        )
    elif admin_username and admin_password:
        default_admin = conn.execute('SELECT * FROM admins ORDER BY id LIMIT 1').fetchone()
        if default_admin:
            normalized_email = f'{admin_username}@tbjzc.com'
            stored_hash = default_admin['password_hash']
            should_update = (
                default_admin['username'] != admin_username
                or default_admin['email'] != normalized_email
                or not check_password_hash(stored_hash, admin_password)
                or default_admin['role'] != 'SUPER_ADMIN'
                or default_admin['status'] != 'active'
            )
            if should_update:
                conn.execute(
                    'UPDATE admins SET username = ?, email = ?, password_hash = ?, full_name = ?, role = ?, status = ? WHERE id = ?',
                    (
                        admin_username,
                        normalized_email,
                        generate_password_hash(admin_password),
                        'Super Administrator',
                        'SUPER_ADMIN',
                        'active',
                        default_admin['id'],
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


try:
    ensure_default_data()
except Exception:
    logger.exception('Database initialization failed during app startup.')
    raise


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    logger.exception('Unhandled application exception: %s', error)
    if request.path.startswith('/api/'):
        return jsonify(error='A server error occurred. Please try again later.'), 500
    return error


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
            log_security_alert(
                'SECURITY ALERT',
                'Unauthenticated request to a protected admin endpoint.',
                severity='high',
                module=request.path,
            )
            logger.info('Blocked protected admin request without valid session: %s', request.path)
            return jsonify(error='Authentication required.'), 401


@app.route('/')
def frontpage():
    return send_from_directory(str(FRONTEND_DIR), 'index.html')


@app.route('/admin')
@app.route('/admin/')
def admin_index():
    return send_from_directory(str(FRONTEND_DIR), 'admin.html')


@app.route('/images/uploads/<path:filename>')
def serve_uploaded_image(filename):
    return send_from_directory(str(UPLOADS_DIR), filename)


@app.route('/api/uploads/<path:filename>')
def serve_api_uploaded_image(filename):
    return send_from_directory(str(UPLOADS_DIR), filename)


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


@app.route('/api/register', methods=['POST'])
def register_user():
    payload = request.get_json(silent=True) or {}
    username = (payload.get('username') or '').strip()
    email = (payload.get('email') or '').strip().lower()
    role = (payload.get('role') or '').strip().upper()
    password = payload.get('password') or ''
    confirm_password = payload.get('confirm_password') or ''

    if not re.match(r'^[A-Za-z0-9_.-]{2,50}$', username):
        return jsonify(error='Username must be 2-50 characters and use only letters, numbers, dots, underscores, or hyphens.'), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify(error='A valid email address is required.'), 400
    if role not in ALLOWED_USER_ROLES:
        return jsonify(error='A valid role is required.'), 400
    if len(password) < 8 or password != confirm_password:
        return jsonify(error='Passwords must match and be at least 8 characters.'), 400

    conn = get_db()
    try:
        cursor = conn.execute(
            '''
            INSERT INTO admins (username, email, full_name, password_hash, role, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            ''',
            (username, email, username, generate_password_hash(password), role, iso_now()),
        )
        admin_id = cursor.lastrowid
        conn.execute(
            '''
            INSERT INTO login_requests (username, email, user_type, profile_info, request_id, requested_role, device_info, admin_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            ''',
            (username, email, 'Admin', '', str(uuid.uuid4())[:8], role, request_device_info(), admin_id, iso_now()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify(error='An account with that email already exists.'), 409
    conn.close()
    record_activity('user_registration', target=f'admin:{admin_id}', details=f'New user registration requested for {username}.', actor_name=username, actor_email=email)
    return jsonify(message='Registration submitted for Super Admin approval.', status='pending'), 202


@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    payload = request.get_json(silent=True) or {}
    username = normalize_env_value(payload.get('username'))
    password = normalize_env_value(payload.get('password'))
    env_username, env_password = get_admin_credentials()

    if not username or not password:
        return jsonify(error='Username and password are required.'), 400

    if not env_username or not env_password:
        logger.warning('Admin login blocked because ADMIN_USERNAME/ADMIN_PASSWORD are not configured.')
        return jsonify(error='Admin credentials are not configured for this deployment.'), 500

    conn = get_db()
    admin = None
    if username == env_username and password == env_password:
        admin = conn.execute('SELECT * FROM admins WHERE username = ?', (env_username,)).fetchone()
        if not admin:
            conn.execute(
                'INSERT INTO admins (username, email, full_name, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (env_username, f'{env_username}@tbjzc.com', 'Super Administrator', generate_password_hash(env_password), 'SUPER_ADMIN', 'active', iso_now()),
            )
            conn.commit()
            admin = conn.execute('SELECT * FROM admins WHERE username = ?', (env_username,)).fetchone()
    else:
        admin = conn.execute('SELECT * FROM admins WHERE username = ? OR email = ?', (username, username)).fetchone()
        if admin and not check_password_hash(admin['password_hash'], password):
            admin = None

    if not admin:
        conn.close()
        log_security_alert('SECURITY ALERT', 'Failed admin login attempt.', severity='high', module='/api/admin/login', account=username)
        record_activity('login_failed', target='system', details='Invalid admin credentials.', result='denied', actor_name=username, actor_email=username if '@' in username else None)
        return jsonify(error='Invalid username or password.'), 401

    if admin['status'] == 'pending':
        conn.close()
        log_security_alert('SECURITY ALERT', 'Pending account attempted to log in.', severity='medium', module='/api/admin/login', account=admin['email'])
        record_activity('login_blocked', target=f'admin:{admin["id"]}', details='Pending account login blocked.', result='denied', actor_name=admin['full_name'], actor_email=admin['email'])
        return jsonify(error='This account is awaiting Super Admin approval.'), 403
    if admin['status'] != 'active':
        conn.close()
        log_security_alert('SECURITY ALERT', 'Inactive account attempted to log in.', severity='high', module='/api/admin/login', account=admin['email'])
        record_activity('login_blocked', target=f'admin:{admin["id"]}', details='Inactive account login blocked.', result='denied', actor_name=admin['full_name'], actor_email=admin['email'])
        return jsonify(error='This account is not active.'), 403

    conn.execute('UPDATE admins SET last_login = ? WHERE id = ?', (iso_now(), admin['id']))
    conn.commit()
    admin = conn.execute('SELECT * FROM admins WHERE id = ?', (admin['id'],)).fetchone()
    conn.close()

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

    log_activity('user_login', target='system', details='User logged in successfully.', admin_id=admin['id'])

    return jsonify({
        'message': 'Login successful.',
        'admin': session['admin'],
    })


@app.route('/api/admin/users', methods=['POST'])
@require_admin
@require_roles('SUPER_ADMIN')
def create_admin_user():
    payload = request.get_json(silent=True) or {}
    actor = current_admin_record()
    username = (payload.get('username') or '').strip()
    email = (payload.get('email') or '').strip().lower()
    role = (payload.get('role') or '').strip().upper()
    password = payload.get('password') or ''
    confirm_password = payload.get('confirm_password') or ''
    if not re.match(r'^[A-Za-z0-9_.-]{2,50}$', username):
        return jsonify(error='Username must be 2-50 characters and use only letters, numbers, dots, underscores, or hyphens.'), 400
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify(error='A valid email address is required.'), 400
    if role not in ALLOWED_USER_ROLES:
        return jsonify(error='A valid role is required.'), 400
    if len(password) < 8 or password != confirm_password:
        return jsonify(error='Passwords must match and be at least 8 characters.'), 400

    conn = get_db()
    try:
        cursor = conn.execute(
            'INSERT INTO admins (username, email, full_name, password_hash, role, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (username, email, username, generate_password_hash(password), role, 'active', iso_now()),
        )
        user_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify(error='An account with that email already exists.'), 409
    conn.close()
    record_activity('user_created', target=f'admin:{user_id}', details=f'Created active {role} account for {username}.', admin_id=actor['id'])
    return jsonify(message='User created successfully.', user_id=user_id, status='active'), 201


@app.route('/api/admin/logout', methods=['POST'])
@require_admin
def admin_logout():
    admin = current_admin_record()
    log_activity('user_logout', target='system', details='User logged out.', admin_id=admin['id'])
    session.clear()
    return jsonify(message='Logged out successfully.')


@app.route('/api/admin/me', methods=['GET'])
def admin_me():
    if not ensure_session_valid():
        return jsonify(logged_in=False), 401
    admin = current_admin_record()
    return jsonify({'logged_in': True, 'admin': session.get('admin', admin)})


@app.route('/api/admin/session')
def admin_session():
    return admin_me()


@app.route('/api/post-sections', methods=['GET'])
def post_sections():
    return jsonify(POST_SECTIONS)


@app.route('/api/posts', methods=['GET'])
def public_posts():
    section = (request.args.get('section') or '').strip().lower()
    if section and section not in POST_SECTION_VALUES:
        return jsonify(error='Unknown post section.'), 400
    conn = get_db()
    if section:
        rows = conn.execute(
            "SELECT * FROM posts WHERE section = ? AND status = 'published' ORDER BY created_at DESC",
            (section,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM posts WHERE status = 'published' ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([serialize_post(row) for row in rows])


@app.route('/api/admin/posts', methods=['GET', 'POST'])
@require_admin
def manage_posts():
    if request.method == 'GET':
        conn = get_db()
        rows = conn.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
        conn.close()
        return jsonify([serialize_post(row) for row in rows])

    if request.content_type and request.content_type.startswith('multipart/form-data'):
        payload = request.form
        uploaded_files = request.files.getlist('photos')
    else:
        payload = request.get_json(silent=True) or {}
        uploaded_files = []

    section = (payload.get('section') or '').strip().lower()
    title = (payload.get('title') or payload.get('heading') or '').strip()
    description = (payload.get('description') or payload.get('content') or payload.get('short_description') or '').strip()
    if section not in POST_SECTION_VALUES or section in EXCLUDED_POST_SECTIONS:
        return jsonify(error='A valid news/content section is required.'), 400
    if not title or len(title) > 200:
        return jsonify(error='Post heading is required and must be 200 characters or fewer.'), 400
    if not description:
        return jsonify(error='Post description is required.'), 400

    images = []
    try:
        if uploaded_files:
            images = save_post_images(uploaded_files)
        elif isinstance(payload, dict):
            images = payload.get('images') or []
            if not isinstance(images, list) or any(not isinstance(image, str) or not image.startswith('/images/') for image in images):
                return jsonify(error='Post images must be stored image paths.'), 400
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except OSError as error:
        return jsonify(error=f'Unable to store uploaded images: {error}'), 503

    now = iso_now()
    admin = current_admin_record()
    author_id = admin['id'] if admin else None
    author = admin['username'] if admin else 'Administrator'
    conn = get_db()
    cursor = conn.execute(
        '''
        INSERT INTO posts (title, short_description, content, category, section, author_id, author, status, featured_image, images, tags, publish_date, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (title, description, description, section, section, author_id, author, payload.get('status') or 'published', images[0] if images else '', json.dumps(images), '', now, now, now),
    )
    conn.commit()
    post_id = cursor.lastrowid
    conn.close()
    log_activity('create_post', target=f'post:{post_id}', details=f'Created post in {section}: {title}', admin_id=session['admin_id'])
    return jsonify(message='Post published successfully.', id=post_id, section=section, images=images), 201


@app.route('/api/admin/posts/<int:post_id>', methods=['PUT', 'DELETE'])
@require_admin
def edit_or_delete_post(post_id):
    conn = get_db()
    post = conn.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post:
        conn.close()
        return jsonify(error='Post not found.'), 404
    if request.method == 'DELETE':
        conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        conn.commit()
        conn.close()
        log_activity('delete_post', target=f'post:{post_id}', details=f'Deleted post: {post["title"]}', admin_id=session['admin_id'])
        return jsonify(message='Post deleted successfully.')

    payload = request.get_json(silent=True) or {}
    section = (payload.get('section') or '').strip().lower()
    title = (payload.get('title') or payload.get('heading') or '').strip()
    description = (payload.get('description') or payload.get('content') or '').strip()
    if section not in POST_SECTION_VALUES or section in EXCLUDED_POST_SECTIONS:
        conn.close()
        return jsonify(error='A valid news/content section is required.'), 400
    if not title or not description:
        conn.close()
        return jsonify(error='Post heading and description are required.'), 400
    conn.execute(
        'UPDATE posts SET title = ?, short_description = ?, content = ?, category = ?, section = ?, status = ?, updated_at = ? WHERE id = ?',
        (title, description, description, section, section, payload.get('status') or post['status'], iso_now(), post_id),
    )
    conn.commit()
    conn.close()
    log_activity('edit_post', target=f'post:{post_id}', details=f'Updated post in {section}: {title}', admin_id=session['admin_id'])
    return jsonify(message='Post updated successfully.', section=section)


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
        upload_dir = UPLOADS_DIR
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
@require_roles('SUPER_ADMIN')
def login_requests():
    conn = get_db()
    rows = conn.execute('SELECT * FROM login_requests ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/pending-approvals', methods=['GET'])
@require_admin
@require_roles('SUPER_ADMIN')
def pending_approvals():
    conn = get_db()
    rows = conn.execute(
        '''
        SELECT lr.id, COALESCE(lr.username, lr.name) AS username, lr.email, lr.requested_role, lr.device_info, lr.created_at,
               lr.admin_id, a.status AS account_status
        FROM login_requests lr
        LEFT JOIN admins a ON a.id = lr.admin_id
        WHERE lr.status = 'pending' AND lr.admin_id IS NOT NULL
        ORDER BY lr.created_at DESC
        ''',
    ).fetchall()
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
    if row['status'] != 'pending':
        conn.close(); return jsonify(error='This request has already been reviewed.'), 409
    if row['admin_id']:
        conn.execute("UPDATE admins SET status = 'active' WHERE id = ?", (row['admin_id'],))
    conn.execute("UPDATE login_requests SET status = 'approved', reviewed_at = ? WHERE id = ?", (iso_now(), request_id))
    conn.commit(); conn.close()
    log_activity('account_approved', target=f'login_request:{request_id}', details=f'Approved account for {row["email"]}', admin_id=session['admin_id'])
    return jsonify(message='Login request approved.')


@app.route('/api/admin/login-requests/<int:request_id>/deny', methods=['POST'])
@require_admin
@require_roles('SUPER_ADMIN')
def deny_login_request(request_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM login_requests WHERE id = ?', (request_id,)).fetchone()
    if not row:
        conn.close(); return jsonify(error='Login request not found.'), 404
    if row['status'] != 'pending':
        conn.close(); return jsonify(error='This request has already been reviewed.'), 409
    if row['admin_id']:
        conn.execute("UPDATE admins SET status = 'denied' WHERE id = ?", (row['admin_id'],))
    conn.execute(
        "UPDATE login_requests SET status = 'denied', rejection_reason = ?, reviewed_at = ? WHERE id = ?",
        ('Denied by Super Admin', iso_now(), request_id),
    )
    conn.commit(); conn.close()
    log_activity('account_denied', target=f'login_request:{request_id}', details=f'Denied account for {row["email"]}', admin_id=session['admin_id'], result='denied')
    return jsonify(message='Login request denied.')


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
    rows = conn.execute(
        'SELECT id, actor_name, actor_email, action, target, details, result, device_info, created_at FROM activity_logs ORDER BY created_at DESC LIMIT 50',
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/alerts', methods=['GET'])
@require_admin
def list_security_alerts():
    conn = get_db()
    rows = conn.execute(
        'SELECT id, alert_type, description, account, device_info, module, severity, is_read, created_at FROM security_alerts ORDER BY created_at DESC LIMIT 50',
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/alerts/<int:alert_id>/read', methods=['POST'])
@require_admin
@require_roles('SUPER_ADMIN')
def mark_security_alert_read(alert_id):
    conn = get_db()
    cursor = conn.execute('UPDATE security_alerts SET is_read = 1 WHERE id = ?', (alert_id,))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        return jsonify(error='Alert not found.'), 404
    return jsonify(message='Alert marked as read.')


@app.route('/api/admin/users', methods=['GET'])
@require_admin
@require_roles('SUPER_ADMIN')
def list_users():
    conn = get_db()
    rows = conn.execute('SELECT id, username, email, full_name, role, status, last_login, created_at FROM admins ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route('/api/admin/users/<int:user_id>', methods=['PATCH', 'DELETE'])
@require_admin
@require_roles('SUPER_ADMIN')
def manage_admin_user(user_id):
    admin = current_admin_record()
    if user_id == admin['id']:
        return jsonify(error='You cannot modify your own Super Admin account here.'), 400
    conn = get_db()
    target = conn.execute('SELECT * FROM admins WHERE id = ?', (user_id,)).fetchone()
    if not target:
        conn.close()
        return jsonify(error='User not found.'), 404
    if target['role'] == 'SUPER_ADMIN':
        conn.close()
        return jsonify(error='The Super Admin account cannot be modified here.'), 403

    if request.method == 'DELETE':
        conn.execute('DELETE FROM admins WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        record_activity('user_deleted', target=f'admin:{user_id}', details=f'Deleted user account {target["email"]}.', admin_id=admin['id'])
        return jsonify(message='User deleted successfully.')

    payload = request.get_json(silent=True) or {}
    role = (payload.get('role') or '').strip().upper()
    if role not in ALLOWED_USER_ROLES:
        conn.close()
        return jsonify(error='A valid role is required.'), 400
    conn.execute('UPDATE admins SET role = ? WHERE id = ?', (role, user_id))
    conn.commit()
    conn.close()
    record_activity('role_changed', target=f'admin:{user_id}', details=f'Changed {target["email"]} role to {role}.', admin_id=admin['id'])
    return jsonify(message='User role updated successfully.')


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


application = app

