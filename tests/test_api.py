"""Integration checks against a real server and isolated temporary SQLite database.
Run: python -m unittest discover -s tests -p 'test_api.py' -v
"""
from __future__ import annotations
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

class Server:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='careers-test-')
        self.db = Path(self.tmp.name) / 'test.sqlite3'
        self.email = 'admin@example.test'
        self.password = secrets.token_urlsafe(24)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.base = f'http://127.0.0.1:{self.port}'
        self.proc = None
        self.start()
    def start(self):
        env = dict(os.environ, CAREERS_ADMIN_EMAIL=self.email, CAREERS_ADMIN_PASSWORD=self.password)
        self.log = tempfile.TemporaryFile(mode='w+')
        self.proc = subprocess.Popen([sys.executable, str(ROOT / 'server.py'), '--host', '127.0.0.1', '--port', str(self.port), '--db', str(self.db), '--no-seed'], cwd=ROOT, env=env, stdout=self.log, stderr=self.log)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(self.base + '/api/jobs', timeout=.3).close()
                return
            except (OSError, urllib.error.URLError):
                if self.proc.poll() is not None:
                    self.log.seek(0)
                    raise RuntimeError('Test server exited: ' + self.log.read())
                time.sleep(.05)
        raise RuntimeError('Test server did not become ready')
    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=5)
        self.log.close()
    def close(self):
        self.stop(); self.tmp.cleanup()

class Client:
    def __init__(self, server):
        self.base = server.base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None
    def request(self, method, path, data=None, csrf=True):
        headers = {'Content-Type': 'application/json'}
        if csrf and self.csrf: headers['X-CSRF-Token'] = self.csrf
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
        try:
            response = self.opener.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        try: body = json.loads(raw)
        except json.JSONDecodeError: body = raw.decode(errors='replace')
        return response.status, body
    def login(self, server):
        status, body = self.request('POST', '/api/auth/login', {'email':server.email, 'password':server.password})
        if status != 200: raise AssertionError((status, body))
        status, session = self.request('GET', '/api/auth/session')
        self.csrf = session['csrf_token']
        return session

def job_payload(**changes):
    value = dict(title='Integration Builder', team='Engineering', location='Gurugram', country='India', work_mode='Hybrid', employment_type='Full-time', description='Build useful tools with a collaborative team.', responsibilities='Own a small product and measure its impact.', requirements='Experience delivering thoughtful software.', first_90_days='Ship a useful tool and learn from real users.', status='draft')
    value.update(changes)
    return value

class APITests(unittest.TestCase):
    def setUp(self):
        self.server = Server(); self.client = Client(self.server)
        self.addCleanup(self.server.close)
    def login(self): return self.client.login(self.server)
    def create(self, **changes):
        code, body = self.client.request('POST', '/api/admin/jobs', job_payload(**changes))
        self.assertEqual(code, 201, body)
        return body.get('job', body)
    def test_admin_requires_authentication(self):
        for method, path, data in [('GET','/api/admin/jobs',None), ('GET','/api/admin/applications',None), ('POST','/api/admin/jobs',job_payload()), ('PATCH','/api/admin/jobs/missing',{'status':'published'}), ('PUT','/api/admin/jobs/missing',job_payload()), ('PATCH','/api/admin/applications/missing',{'status':'reviewing'})]:
            code, body = self.client.request(method,path,data)
            self.assertEqual(code,401,body)
        code, session = self.client.request('GET','/api/auth/session')
        self.assertEqual(code,200); self.assertFalse(session.get('authenticated',session.get('auth')))
    def test_login_logout_and_bad_credentials(self):
        code, _ = self.client.request('POST','/api/auth/login',{'email':self.server.email,'password':'wrong-password'})
        self.assertEqual(code,401)
        session = self.login()
        self.assertTrue(session.get('authenticated',session.get('auth')))
        self.assertEqual(session['email'],self.server.email)
        self.assertTrue(self.client.csrf)
        self.assertEqual(self.client.request('POST','/api/auth/logout',{})[0],200)
        self.assertEqual(self.client.request('GET','/api/admin/jobs')[0],401)
    def test_csrf_required_for_mutations(self):
        self.login()
        job=self.create(status='published')
        _,receipt=self.client.request('POST',f"/api/jobs/{job['id']}/applications",{'name':'CSRF Applicant','email':'csrf@example.test','portfolio_url':'','statement':'Built a useful tool.'})
        for csrf_value in (None,'invalid-token'):
            self.client.csrf=csrf_value
            for method,path,data in [('POST','/api/admin/jobs',job_payload()),('PATCH',f"/api/admin/jobs/{job['id']}",{'status':'closed'}),('PATCH',f"/api/admin/applications/{receipt['id']}",{'status':'hired','note':'Should not save'}),('POST','/api/auth/logout',{})]:
                code,body=self.client.request(method,path,data)
                self.assertEqual(code,403,body)
        jobs=self.client.request('GET','/api/admin/jobs')[1]['jobs']
        self.assertEqual(len(jobs),1); self.assertEqual(jobs[0]['status'],'published')
        applications=self.client.request('GET','/api/admin/applications')[1]['applications']
        self.assertEqual(applications[0]['status'],'new')
    def test_job_validation(self):
        self.login()
        for changes in ({'title':''},{'status':'imaginary'},{'work_mode':'Anywhere'},{'employment_type':'Temporary'},{'description':''}):
            code, body = self.client.request('POST','/api/admin/jobs',job_payload(**changes))
            self.assertEqual(code,400,body)
            self.assertIsInstance(body.get('error'),str)
    def test_drafts_private_and_only_published_apply(self):
        self.login(); job = self.create()
        self.assertEqual(self.client.request('GET','/api/jobs')[1]['jobs'],[])
        self.assertEqual(self.client.request('GET',f"/api/jobs/{job['id']}")[0],404)
        code, _ = self.client.request('POST',f"/api/jobs/{job['id']}/applications",{'name':'Test Applicant','email':'test@example.test','portfolio_url':'','statement':'I want to build.'})
        self.assertEqual(code,404)
    def test_application_validation_and_duplicate(self):
        self.login(); job=self.create(status='published'); path=f"/api/jobs/{job['id']}/applications"
        applicant={'name':'Test Applicant','email':'test@example.test','portfolio_url':'https://example.test/work','statement':'I built a small useful tool.'}
        for change in ({'name':''},{'email':'bad'},{'portfolio_url':'javascript:alert(1)'},{'statement':''}):
            code, body=self.client.request('POST',path,dict(applicant,**change))
            self.assertEqual(code,400,body)
        code, body=self.client.request('POST',path,applicant)
        self.assertEqual(code,201,body); self.assertTrue(body['reference'])
        self.assertEqual(self.client.request('POST',path,applicant)[0],409)
    def test_complete_lifecycle_and_restart_persistence(self):
        self.login(); job=self.create(); job_id=job['id']
        code, body=self.client.request('PATCH',f'/api/admin/jobs/{job_id}',{'status':'published'})
        self.assertEqual(code,200,body)
        self.assertIn(job_id,[row['id'] for row in self.client.request('GET','/api/jobs')[1]['jobs']])
        self.assertEqual(self.client.request('GET',f'/api/jobs/{job_id}')[0],200)
        code, receipt=self.client.request('POST',f'/api/jobs/{job_id}/applications',{'name':'Lifecycle Applicant','email':'lifecycle@example.test','portfolio_url':'','statement':'Built an internal tool used by my team.'})
        self.assertEqual(code,201,receipt)
        applications=self.client.request('GET','/api/admin/applications')[1]['applications']
        application=next(row for row in applications if row['id']==receipt['id'])
        self.assertEqual(application['email'],'lifecycle@example.test')
        code, body=self.client.request('PATCH',f"/api/admin/applications/{receipt['id']}",{'status':'reviewing','note':'Reviewed the project.'})
        self.assertEqual(code,200,body)
        self.server.stop(); self.server.start(); self.client=Client(self.server); self.login()
        applications=self.client.request('GET','/api/admin/applications')[1]['applications']
        self.assertEqual(next(row for row in applications if row['id']==receipt['id'])['status'],'reviewing')
        code, body=self.client.request('PATCH',f'/api/admin/jobs/{job_id}',{'status':'closed'})
        self.assertEqual(code,200,body)
        self.assertNotIn(job_id,[row['id'] for row in self.client.request('GET','/api/jobs')[1]['jobs']])
        self.assertEqual(self.client.request('POST',f'/api/jobs/{job_id}/applications',{'name':'Late Applicant','email':'late@example.test','portfolio_url':'','statement':'Too late.'})[0],404)
    def test_private_files_and_traversal_not_served(self):
        for path in ('/server.py','/var/test.sqlite3','/.git/config','/../server.py','/%2e%2e/server.py','/app/../../server.py','/tests/test_api.py'):
            code, body=self.client.request('GET',path)
            self.assertIn(code,(400,403,404),path)

if __name__ == '__main__': unittest.main()
