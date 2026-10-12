#!/usr/bin/env python3
"""Local careers demo: Python stdlib HTTP server and SQLite persistence."""
import argparse
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from demo_jobs import SEED_VERSION, demo_jobs

ROOT = Path(__file__).resolve().parent
JOB_FIELDS = ('title', 'team', 'location', 'country', 'state', 'work_mode', 'employment_type', 'description', 'responsibilities', 'requirements', 'first_90_days', 'status')
JOB_STATUSES = ('draft', 'published', 'closed')
APPLICATION_STATUSES = ('new', 'reviewing', 'interview', 'hired', 'rejected')
WORK_MODES = ('On-site', 'Hybrid', 'Remote')
EMPLOYMENT_TYPES = ('Full-time', 'Part-time', 'Contract', 'Internship')
EMAIL = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 310000).hex()


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def string(data, key, max_length=200, required=True):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise APIError(400, f'{key} must be text.')
    value = value.strip()
    if required and not value:
        raise APIError(400, f'{key} is required.')
    if len(value) > max_length:
        raise APIError(400, f'{key} must be {max_length} characters or fewer.')
    return value


def validate_job(data, default_status='draft'):
    clean = {field: string(data, field, 12000 if field in ('description', 'responsibilities', 'requirements', 'first_90_days') else 200, required=field != 'state') for field in JOB_FIELDS if field != 'status'}
    clean['status'] = data.get('status', default_status)
    for field, choices in [('status', JOB_STATUSES), ('work_mode', WORK_MODES), ('employment_type', EMPLOYMENT_TYPES)]:
        if clean[field] not in choices:
            raise APIError(400, f'Invalid {field}.')
    return clean


class CareersServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, db_path, seed=True):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sessions = {}
        self.login_attempts = {}
        self.lock = threading.Lock()
        self.initialize(seed)
        os.chmod(self.db_path, 0o600)
        super().__init__(address, Handler)

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def initialize(self, seed):
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS admin (email TEXT PRIMARY KEY, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, team TEXT NOT NULL, location TEXT NOT NULL,
                    country TEXT NOT NULL, state TEXT NOT NULL DEFAULT '', work_mode TEXT NOT NULL, employment_type TEXT NOT NULL,
                    description TEXT NOT NULL, responsibilities TEXT NOT NULL, requirements TEXT NOT NULL,
                    first_90_days TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('draft','published','closed')),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS applications (
                    id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, job_id TEXT NOT NULL REFERENCES jobs(id),
                    name TEXT NOT NULL, email TEXT NOT NULL, portfolio_url TEXT NOT NULL, statement TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('new','reviewing','interview','hired','rejected')),
                    note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(job_id,email));
            ''')
            if 'state' not in {column['name'] for column in db.execute('PRAGMA table_info(jobs)')}:
                db.execute("ALTER TABLE jobs ADD COLUMN state TEXT NOT NULL DEFAULT ''")
            existing = db.execute('SELECT email FROM admin LIMIT 1').fetchone()
            env_password = os.environ.get('CAREERS_ADMIN_PASSWORD')
            if not existing or env_password:
                email = os.environ.get('CAREERS_ADMIN_EMAIL', 'admin@careers.local').strip().lower()
                if not EMAIL.fullmatch(email):
                    raise ValueError('CAREERS_ADMIN_EMAIL must be a valid email address.')
                password = env_password or secrets.token_urlsafe(20)
                if len(password) < 12:
                    raise ValueError('CAREERS_ADMIN_PASSWORD must be at least 12 characters.')
                salt = secrets.token_hex(16)
                db.execute('DELETE FROM admin')
                db.execute('INSERT INTO admin(email,salt,password_hash) VALUES (?,?,?)', (email, salt, password_hash(password, salt)))
                if not env_password:
                    access = self.db_path.parent / 'admin-access.txt'
                    descriptor = os.open(access, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    os.fchmod(descriptor, 0o600)
                    with os.fdopen(descriptor, 'w') as output:
                        output.write(f'Local demo admin\nEmail: {email}\nPassword: {password}\n')
            seeded = db.execute("SELECT value FROM metadata WHERE key='demo_seed_version'").fetchone()
            if seed and (not seeded or seeded['value'] != SEED_VERSION):
                stamp = now()
                columns = ('id', *JOB_FIELDS, 'created_at', 'updated_at')
                for job in demo_jobs():
                    values = (job['id'], *(job[field] for field in JOB_FIELDS), stamp, stamp)
                    # Stable IDs and DO NOTHING preserve edits, statuses, and existing applications.
                    db.execute('INSERT INTO jobs (' + ','.join(columns) + ') VALUES (' + ','.join('?' * len(columns)) + ') ON CONFLICT(id) DO NOTHING', values)
                db.execute("INSERT INTO metadata(key,value) VALUES ('demo_seed_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (SEED_VERSION,))
            if not db.execute("SELECT 1 FROM metadata WHERE key='demo_copy_version' AND value='natural-v2'").fetchone():
                # Change only untouched generated copy; preserve edits, status, IDs, and applications.
                for original, clean in zip(demo_jobs(legacy_copy=True), demo_jobs()):
                    for field in ('description', 'responsibilities', 'requirements', 'first_90_days'):
                        db.execute(f'UPDATE jobs SET {field}=? WHERE id=? AND {field}=?',
                                   (clean[field], original['id'], original[field]))
                # Original three-role starter set used random IDs; identify its exact known copy.
                legacy_titles = ('Product Designer', 'Frontend Engineer', 'Operations Lead',
                                 'Builder – Design the customer journey', 'Builder – Improve digital experiences',
                                 'Builder – Simplify pilot workflows')
                original_description = 'Illustrative demo role. Help turn meaningful problems into useful experiences. This posting is for testing; it is not an active vacancy.'
                db.execute('UPDATE jobs SET description=? WHERE title IN (' + ','.join('?' * len(legacy_titles)) + ') AND description=?',
                           ('Help turn meaningful problems into useful experiences. Own a focused customer problem, collaborate across teams, and share what you learn as you improve the journey.',
                            *legacy_titles, original_description))
                db.execute("INSERT INTO metadata(key,value) VALUES ('demo_copy_version','natural-v2') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            db.execute("INSERT INTO metadata(key,value) VALUES ('initialized','1') ON CONFLICT(key) DO NOTHING")


class Handler(BaseHTTPRequestHandler):
    server_version = 'CareersDemo/1.0'

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def do_PUT(self):
        self.dispatch('PUT')

    def do_PATCH(self):
        self.dispatch('PATCH')

    def dispatch(self, method):
        try:
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            if not path.startswith('/api/'):
                if method != 'GET':
                    raise APIError(405, 'Method not allowed.')
                return self.static(path)
            if method != 'GET':
                self.check_origin()
            result, status, cookie = self.api(method, path.rstrip('/'), parse_qs(parsed.query))
            self.json_response(result, status, cookie)
        except APIError as exc:
            self.json_response({'error': exc.message}, exc.status)
        except sqlite3.IntegrityError:
            self.json_response({'error': 'This record already exists.'}, 409)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            # Never return database errors, credentials, or applicant details to the client.
            self.json_response({'error': 'Something went wrong. Please try again.'}, 500)

    def json_response(self, data, status=200, cookie=None):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def check_origin(self):
        origin = self.headers.get('Origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or parsed.netloc != self.headers.get('Host') or parsed.path or parsed.query or parsed.fragment:
                raise APIError(403, 'Request origin is not allowed.')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise APIError(403, 'Cross-site requests are not allowed.')

    def body(self):
        if self.headers.get('Transfer-Encoding'):
            raise APIError(400, 'Transfer encoding is not supported.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise APIError(400, 'Invalid request length.')
        if not 0 < length <= 65536:
            raise APIError(413 if length > 65536 else 400, 'Request body must be JSON and at most 64 KB.')
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise APIError(415, 'Use application/json.')
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise APIError(400, 'Invalid JSON.')
        if not isinstance(data, dict):
            raise APIError(400, 'JSON body must be an object.')
        return data

    def session(self, required=False, mutate=False):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookies['careers_session'].value if 'careers_session' in cookies else ''
        except Exception:
            token = ''
        with self.server.lock:
            session = self.server.sessions.get(token)
            if session and session['expires'] <= time.time():
                self.server.sessions.pop(token, None)
                session = None
        if required and not session:
            raise APIError(401, 'Sign in to continue.')
        if mutate and session and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf_token']):
            raise APIError(403, 'Invalid CSRF token. Refresh and try again.')
        return token, session

    def api(self, method, path, query):
        if path == '/api/auth/session' and method == 'GET':
            _, session = self.session()
            return ({'authenticated': True, 'email': session['email'], 'csrf_token': session['csrf_token']} if session else {'authenticated': False}), 200, None
        if path == '/api/auth/login' and method == 'POST':
            data = self.body()
            email = string(data, 'email', 254).lower()
            password = string(data, 'password', 1024)
            address = self.client_address[0]
            timestamp = time.time()
            with self.server.lock:
                attempts = [attempt for attempt in self.server.login_attempts.get(address, []) if attempt > timestamp - 300]
                if len(attempts) >= 10:
                    raise APIError(429, 'Too many sign-in attempts. Try again in five minutes.')
                attempts.append(timestamp)
                self.server.login_attempts[address] = attempts
            with self.server.connect() as db:
                admin = db.execute('SELECT * FROM admin WHERE email=?', (email,)).fetchone()
            # Do the same expensive hash for unknown accounts.
            digest = password_hash(password, admin['salt'] if admin else '0' * 32)
            if not admin or not hmac.compare_digest(digest, admin['password_hash']):
                raise APIError(401, 'Email or password is incorrect.')
            token = secrets.token_urlsafe(32)
            session = {'email': email, 'csrf_token': secrets.token_urlsafe(32), 'expires': timestamp + 28800}
            with self.server.lock:
                self.server.sessions = {key: value for key, value in self.server.sessions.items() if value['expires'] > timestamp}
                self.server.sessions[token] = session
                self.server.login_attempts.pop(address, None)
            return {'authenticated': True, 'email': email, 'csrf_token': session['csrf_token']}, 200, f'careers_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'
        if path == '/api/auth/logout' and method == 'POST':
            token, _ = self.session(required=True, mutate=True)
            with self.server.lock:
                self.server.sessions.pop(token, None)
            return {'ok': True}, 200, 'careers_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
        if path.startswith('/api/admin/'):
            self.session(required=True, mutate=method != 'GET')
            return self.admin_api(method, path, query)
        if path == '/api/jobs' and method == 'GET':
            sql, params = "SELECT * FROM jobs WHERE status='published'", []
            for field in ('team', 'location', 'country', 'state', 'work_mode'):
                if query.get(field, [''])[0]:
                    sql += f' AND {field}=?'
                    params.append(query[field][0])
            if query.get('search', [''])[0]:
                sql += " AND (instr(lower(title),?)>0 OR instr(lower(team),?)>0 OR instr(lower(description),?)>0 OR instr(lower(location),?)>0 OR instr(lower(country),?)>0 OR instr(lower(state),?)>0)"
                params.extend([query['search'][0].lower()] * 6)
            with self.server.connect() as db:
                jobs = [dict(row) for row in db.execute(sql + ' ORDER BY created_at DESC,id', params)]
            return {'jobs': jobs}, 200, None
        match = re.fullmatch(r'/api/jobs/([a-zA-Z0-9_-]+)(/applications)?', path)
        if match:
            job_id, applications = match.groups()
            with self.server.connect() as db:
                job = db.execute("SELECT * FROM jobs WHERE id=? AND status='published'", (job_id,)).fetchone()
                if not job:
                    raise APIError(404, 'This role is no longer available.')
                if not applications and method == 'GET':
                    return {'job': dict(job)}, 200, None
                if applications and method == 'POST':
                    data = self.body()
                    name = string(data, 'name', 150)
                    email = string(data, 'email', 254).lower()
                    statement = string(data, 'statement', 6000)
                    portfolio = string(data, 'portfolio_url', 2048, False)
                    if not EMAIL.fullmatch(email):
                        raise APIError(400, 'Enter a valid email address.')
                    if portfolio:
                        parsed = urlsplit(portfolio)
                        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                            raise APIError(400, 'Portfolio URL must be an http or https link.')
                    identity, reference, stamp = secrets.token_hex(12), 'BLD-' + secrets.token_hex(4).upper(), now()
                    # Transaction rechecks availability: closed roles cannot receive applications.
                    db.execute('BEGIN IMMEDIATE')
                    if not db.execute("SELECT 1 FROM jobs WHERE id=? AND status='published'", (job_id,)).fetchone():
                        raise APIError(404, 'This role is no longer available.')
                    if db.execute('SELECT 1 FROM applications WHERE job_id=? AND email=?', (job_id, email)).fetchone():
                        raise APIError(409, 'You have already applied for this role with this email address.')
                    db.execute('INSERT INTO applications(id,reference,job_id,name,email,portfolio_url,statement,status,note,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', (identity, reference, job_id, name, email, portfolio, statement, 'new', '', stamp, stamp))
                    return {'id': identity, 'reference': reference, 'job_title': job['title'], 'created_at': stamp, 'message': 'Application received. Save your reference for your records.'}, 201, None
        raise APIError(404, 'Endpoint not found.')

    def admin_api(self, method, path, query):
        with self.server.connect() as db:
            if path == '/api/admin/jobs':
                if method == 'GET':
                    jobs = [dict(row) for row in db.execute('SELECT jobs.*, (SELECT count(*) FROM applications WHERE job_id=jobs.id) AS application_count FROM jobs ORDER BY created_at DESC,id')]
                    return {'jobs': jobs}, 200, None
                if method == 'POST':
                    clean = validate_job(self.body())
                    identity, stamp = secrets.token_hex(12), now()
                    values = (identity, *(clean[field] for field in JOB_FIELDS), stamp, stamp)
                    columns = ('id', *JOB_FIELDS, 'created_at', 'updated_at')
                    db.execute('INSERT INTO jobs (' + ','.join(columns) + ') VALUES (' + ','.join('?' * len(columns)) + ')', values)
                    return {'job': dict(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())}, 201, None
            match = re.fullmatch(r'/api/admin/jobs/([a-zA-Z0-9_-]+)', path)
            if match and method in ('PUT', 'PATCH'):
                identity = match[1]
                existing = db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone()
                if not existing:
                    raise APIError(404, 'Role not found.')
                data = self.body()
                if method == 'PUT':
                    clean = validate_job(data, existing['status'])
                else:
                    if data.get('status') not in JOB_STATUSES:
                        raise APIError(400, 'Invalid status.')
                    clean = {'status': data['status']}
                columns = ','.join(f'{field}=?' for field in clean)
                db.execute(f'UPDATE jobs SET {columns},updated_at=? WHERE id=?', (*clean.values(), now(), identity))
                return {'job': dict(db.execute('SELECT * FROM jobs WHERE id=?', (identity,)).fetchone())}, 200, None
            application_sql = 'SELECT applications.*, jobs.title AS job_title FROM applications JOIN jobs ON jobs.id=applications.job_id'
            if path == '/api/admin/applications' and method == 'GET':
                conditions, params = [], []
                for field in ('job_id', 'status'):
                    if query.get(field, [''])[0]:
                        conditions.append(f'applications.{field}=?')
                        params.append(query[field][0])
                if query.get('search', [''])[0]:
                    conditions.append('(instr(lower(applications.name),?)>0 OR instr(lower(applications.email),?)>0 OR instr(lower(jobs.title),?)>0)')
                    params.extend([query['search'][0].lower()] * 3)
                where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
                applications = [dict(row) for row in db.execute(application_sql + where + ' ORDER BY applications.created_at DESC,applications.id', params)]
                return {'applications': applications}, 200, None
            match = re.fullmatch(r'/api/admin/applications/([a-zA-Z0-9_-]+)', path)
            if match and method == 'PATCH':
                identity = match[1]
                if not db.execute('SELECT 1 FROM applications WHERE id=?', (identity,)).fetchone():
                    raise APIError(404, 'Application not found.')
                data = self.body()
                clean = {}
                if 'status' in data:
                    if data['status'] not in APPLICATION_STATUSES:
                        raise APIError(400, 'Invalid application status.')
                    clean['status'] = data['status']
                if 'note' in data:
                    clean['note'] = string(data, 'note', 6000, False)
                if not clean:
                    raise APIError(400, 'Provide a status or note.')
                columns = ','.join(f'{field}=?' for field in clean)
                db.execute(f'UPDATE applications SET {columns},updated_at=? WHERE id=?', (*clean.values(), now(), identity))
                application = dict(db.execute(application_sql + ' WHERE applications.id=?', (identity,)).fetchone())
                return {'application': application}, 200, None
        raise APIError(404, 'Endpoint not found.')

    def static(self, path):
        app = (ROOT / 'app').resolve()
        relative = {'/': 'index.html', '/jobs': 'jobs.html', '/jobs/': 'jobs.html', '/admin': 'admin.html', '/admin/': 'admin.html'}.get(path, path.lstrip('/'))
        asset = (app / relative).resolve()
        if not asset.is_relative_to(app) or any(part.startswith('.') for part in Path(relative).parts) or asset.suffix.lower() not in ('.html', '.css', '.js', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.woff', '.woff2', '.ico') or not asset.is_file():
            raise APIError(404, 'Page not found.')
        body = asset.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', (mimetypes.guess_type(asset.name)[0] or 'application/octet-stream') + ('; charset=utf-8' if asset.suffix in ('.html', '.css', '.js', '.svg') else ''))
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--db', default=str(ROOT / 'var' / 'careers.db'))
    parser.add_argument('--no-seed', action='store_true')
    options = parser.parse_args()
    server = CareersServer((options.host, options.port), options.db, not options.no_seed)
    print(f'Careers demo running at http://{options.host}:{options.port}; admin at /admin', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
