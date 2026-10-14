"""Integration checks against a real server and isolated temporary SQLite database.
Run: python -m unittest discover -s tests -p 'test_api.py' -v
"""
from __future__ import annotations
from collections import Counter
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import re
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]

class Server:
    def __init__(self, seed=False):
        self.seed = seed
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
    def start(self, seed=None):
        if seed is not None: self.seed = seed
        env = dict(os.environ, CAREERS_ADMIN_EMAIL=self.email, CAREERS_ADMIN_PASSWORD=self.password)
        self.log = tempfile.TemporaryFile(mode='w+')
        command = [sys.executable, str(ROOT / 'server.py'), '--host', '127.0.0.1', '--port', str(self.port), '--db', str(self.db)]
        if not self.seed: command.append('--no-seed')
        self.proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=self.log, stderr=self.log)
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

    def test_seed_geography_and_deterministic_restart(self):
        self.server.stop(); self.server.start(seed=True)
        jobs=self.client.request('GET','/api/jobs')[1]['jobs']
        self.assertEqual(len(jobs),120)
        self.assertEqual(Counter(job['country'] for job in jobs),{'India':72,'Australia':24,'UAE':24})
        expected_states={'Andhra Pradesh','Arunachal Pradesh','Assam','Bihar','Chhattisgarh','Goa','Gujarat','Haryana','Himachal Pradesh','Jharkhand','Karnataka','Kerala','Madhya Pradesh','Maharashtra','Manipur','Meghalaya','Mizoram','Nagaland','Odisha','Punjab','Rajasthan','Sikkim','Tamil Nadu','Telangana','Tripura','Uttar Pradesh','Uttarakhand','West Bengal','Andaman and Nicobar Islands','Chandigarh','Dadra and Nagar Haveli and Daman and Diu','Delhi','Jammu and Kashmir','Ladakh','Lakshadweep','Puducherry'}
        def normalize(value):
            return ''.join(char for char in value.lower().replace('&','and') if char.isalnum())
        india={normalize(job['state']) for job in jobs if job['country']=='India'}
        self.assertEqual(india,{normalize(value) for value in expected_states})
        self.assertTrue(all(job['state'] and job['location'] and job['first_90_days'] for job in jobs))
        ids={job['id'] for job in jobs}
        self.assertEqual(len(ids),120)
        self.server.stop(); self.server.start()
        restarted=self.client.request('GET','/api/jobs')[1]['jobs']
        self.assertEqual({job['id'] for job in restarted},ids)
        self.assertEqual(len(restarted),120)

    def test_legacy_state_migration_and_seed_upgrade_preserve_user_data(self):
        self.login(); job=self.create(status='published')
        self.assertEqual(job['state'],'')
        code,receipt=self.client.request('POST',f"/api/jobs/{job['id']}/applications",{'name':'Existing Applicant','email':'existing@example.test','portfolio_url':'','statement':'Already submitted before a seed upgrade.'})
        self.assertEqual(code,201,receipt)
        self.server.stop()
        # Recreate the previous database shape without the optional state field.
        with sqlite3.connect(self.server.db) as connection:
            connection.execute('ALTER TABLE jobs DROP COLUMN state')
        self.server.start(seed=True)
        self.client=Client(self.server); self.login()
        jobs=self.client.request('GET','/api/admin/jobs')[1]['jobs']
        self.assertEqual(len(jobs),121)
        preserved=next(row for row in jobs if row['id']==job['id'])
        self.assertEqual(preserved['title'],job['title']); self.assertEqual(preserved['state'],'')
        applications=self.client.request('GET','/api/admin/applications')[1]['applications']
        self.assertEqual(len(applications),1)
        self.assertEqual(applications[0]['id'],receipt['id'])
        self.assertEqual(applications[0]['email'],'existing@example.test')
        self.server.stop(); self.server.start()
        self.assertEqual(len(self.client.request('GET','/api/jobs')[1]['jobs']),121)

    def test_combined_geography_filters_and_state_search(self):
        self.server.stop(); self.server.start(seed=True)
        params=urllib.parse.urlencode({'country':'India','state':'Maharashtra'})
        code,body=self.client.request('GET','/api/jobs?'+params)
        self.assertEqual(code,200); self.assertTrue(body['jobs'])
        self.assertTrue(all(row['country']=='India' and row['state']=='Maharashtra' for row in body['jobs']))
        city=body['jobs'][0]['location']
        params=urllib.parse.urlencode({'country':'India','state':'Maharashtra','location':city})
        subset=self.client.request('GET','/api/jobs?'+params)[1]['jobs']
        self.assertTrue(subset); self.assertTrue(all(row['location']==city for row in subset))
        params=urllib.parse.urlencode({'country':'Australia','state':'Maharashtra'})
        self.assertEqual(self.client.request('GET','/api/jobs?'+params)[1]['jobs'],[])
        search=self.client.request('GET','/api/jobs?'+urllib.parse.urlencode({'search':'Maharashtra'}))[1]['jobs']
        self.assertTrue(search); self.assertTrue(all(row['state']=='Maharashtra' for row in search))

    def test_seeded_copy_migration_preserves_editor_changes_and_applications(self):
        from demo_jobs import demo_jobs
        self.server.stop(); self.server.start(seed=True); self.login()
        before=self.client.request('GET','/api/admin/jobs')[1]['jobs']
        ids={row['id'] for row in before}
        historical=demo_jobs(legacy_copy=True)[:2]
        edited_id=historical[0]['id']
        code,receipt=self.client.request('POST',f'/api/jobs/{edited_id}/applications',{'name':'Migration Applicant','email':'migration@example.test','portfolio_url':'','statement':'Built something before the content changed.'})
        self.assertEqual(code,201,receipt)
        code,body=self.client.request('PATCH',f"/api/admin/applications/{receipt['id']}",{'status':'reviewing','note':'Preserve this private reviewer note.'})
        self.assertEqual(code,200,body)
        self.server.stop()
        with sqlite3.connect(self.server.db) as connection:
            for fixture in historical:
                connection.execute('UPDATE jobs SET description=?,responsibilities=?,requirements=?,first_90_days=? WHERE id=?',(fixture['description'],fixture['responsibilities'],fixture['requirements'],fixture['first_90_days'],fixture['id']))
            connection.execute('UPDATE jobs SET description=?,status=? WHERE id=?',('An editor has written a specific hiring opportunity.','closed',edited_id))
            connection.execute("DELETE FROM metadata WHERE key='demo_copy_version'")
        self.server.start(); self.client=Client(self.server); self.login()
        after=self.client.request('GET','/api/admin/jobs')[1]['jobs']
        self.assertEqual(len(after),120); self.assertEqual({row['id'] for row in after},ids)
        edited=next(row for row in after if row['id']==edited_id)
        self.assertEqual(edited['description'],'An editor has written a specific hiring opportunity.')
        self.assertEqual(edited['status'],'closed')
        for fixture in historical:
            migrated=next(row for row in after if row['id']==fixture['id'])
            for field in ('description','responsibilities','requirements','first_90_days'):
                self.assertIsNone(re.search(r'\b(?:demo|sample|fictional|illustrative|simulated)\b',migrated[field],re.I),(field,migrated[field]))
        applications=self.client.request('GET','/api/admin/applications')[1]['applications']
        application=next(row for row in applications if row['id']==receipt['id'])
        self.assertEqual(application['status'],'reviewing')
        self.assertEqual(application['note'],'Preserve this private reviewer note.')

    def test_private_files_and_traversal_not_served(self):
        for path in ('/server.py','/var/test.sqlite3','/.git/config','/../server.py','/%2e%2e/server.py','/app/../../server.py','/tests/test_api.py'):
            code, body=self.client.request('GET',path)
            self.assertIn(code,(400,403,404),path)

if __name__ == '__main__': unittest.main()
