/** Hosted API integration checks using real SQLite behind a minimal D1 adapter.
 * Run: node tests/worker.test.mjs (Node 24+).
 * Fixtures and generated credentials never touch the deployed database.
 */
import assert from 'node:assert/strict';
import { test, beforeEach, afterEach } from 'node:test';
import { DatabaseSync } from 'node:sqlite';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomBytes } from 'node:crypto';
import { handleApi } from '../worker/api.mjs';

class D1Adapter {
  constructor(path) { this.sqlite = new DatabaseSync(path); this.sqlite.exec('PRAGMA foreign_keys = ON'); }
  prepare(sql) { return new D1Statement(this, sql); }
  async exec(sql) { this.sqlite.exec(sql); return { count: 1, duration: 0 }; }
  async batch(statements) {
    this.sqlite.exec('BEGIN IMMEDIATE');
    try {
      const results = [];
      for (const statement of statements) results.push(await statement.execute());
      this.sqlite.exec('COMMIT');
      return results;
    } catch (error) { this.sqlite.exec('ROLLBACK'); throw error; }
  }
  close() { this.sqlite.close(); }
}
class D1Statement {
  constructor(database, sql, values = []) { this.database = database; this.sql = sql; this.values = values; }
  bind(...values) { return new D1Statement(this.database, this.sql, values); }
  statement() { return this.database.sqlite.prepare(this.sql); }
  async first(column) {
    const row = this.statement().get(...this.values);
    return row ? (column ? row[column] : { ...row }) : null;
  }
  async all() {
    return { success: true, results: this.statement().all(...this.values).map(row => ({ ...row })), meta: { duration: 0 } };
  }
  async run() {
    const result = this.statement().run(...this.values);
    return { success: true, results: [], meta: { changes: Number(result.changes), last_row_id: Number(result.lastInsertRowid), duration: 0 } };
  }
  async execute() { return /^\s*(SELECT|WITH|PRAGMA)\b/i.test(this.sql) ? this.all() : this.run(); }
}

let directory, databasePath, env, csrf;
beforeEach(() => {
  directory = mkdtempSync(join(tmpdir(), 'careers-worker-'));
  databasePath = join(directory, 'test.sqlite3');
  env = { DB: new D1Adapter(databasePath), ADMIN_USER_ID: 'test-owner-identity', CSRF_SECRET: randomBytes(32).toString('hex') };
  env.DB.sqlite.exec(readFileSync(new URL('../drizzle/0000_careers.sql', import.meta.url), 'utf8'));
  csrf = undefined;
});
afterEach(() => { env.DB.close(); rmSync(directory, { recursive: true, force: true }); });

async function request(method, path, data, { owner = false, identity, token = csrf, origin = 'https://careers.example.test' } = {}) {
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (origin !== null) headers.set('Origin', origin);
  if (owner || identity) headers.set('oai-authenticated-user-id', identity || env.ADMIN_USER_ID);
  if (owner) headers.set('oai-authenticated-user-email', 'owner@example.test');
  if (token) headers.set('X-CSRF-Token', token);
  const req = new Request('https://careers.example.test' + path, { method, headers, ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
  const response = await handleApi(req, env);
  assert.ok(response instanceof Response, 'API route must produce a Response');
  return { status: response.status, body: await response.json() };
}
async function ownerSession() {
  const result = await request('GET', '/api/auth/session', undefined, { owner: true });
  assert.equal(result.status, 200);
  assert.equal(result.body.authenticated, true);
  assert.ok(result.body.csrf_token);
  csrf = result.body.csrf_token;
}
function job(changes = {}) {
  return { title: 'Builder – Deliver a useful tool', team: 'Engineering', location: 'Pune', country: 'India', state: 'Maharashtra', work_mode: 'Hybrid', employment_type: 'Full-time', description: 'Build something useful with a collaborative team.', responsibilities: 'Own and improve a focused product.', requirements: 'Experience building thoughtful software.', first_90_days: 'Ship a useful improvement and learn from users.', status: 'draft', ...changes };
}
async function createJob(changes = {}) {
  const result = await request('POST', '/api/admin/jobs', job(changes), { owner: true });
  assert.equal(result.status, 201, JSON.stringify(result.body));
  return result.body.job || result.body;
}
const applicant = { name: 'Test Applicant', email: 'applicant@example.test', portfolio_url: 'https://example.test/work', statement: 'I built a scheduling tool my team used.' };

test('fresh database seeds 120 public roles with required geographic coverage', async () => {
  const result = await request('GET', '/api/jobs');
  assert.equal(result.status, 200);
  const rows = result.body.jobs;
  assert.equal(rows.length, 120);
  assert.equal(new Set(rows.map(row => row.id)).size, 120);
  for (const [country, count, regions] of [['India',72,36],['Australia',24,8],['UAE',24,7]]) {
    const subset = rows.filter(row => row.country === country);
    assert.equal(subset.length, count);
    assert.equal(new Set(subset.map(row => row.state)).size, regions);
  }
  assert.ok(rows.every(row => row.status === 'published' && row.location && row.first_90_days));
  assert.equal((await request('GET', '/api/jobs')).body.jobs.length, 120, 'Repeated access must not seed duplicates');
});

test('admin endpoints reject missing identity and a non-owner identity', async () => {
  const routes = [['GET','/api/admin/jobs'],['GET','/api/admin/applications'],['POST','/api/admin/jobs',job()],['PATCH','/api/admin/jobs/missing',{status:'published'}],['PUT','/api/admin/jobs/missing',job()],['PATCH','/api/admin/applications/missing',{status:'reviewing'}]];
  for (const [method,path,data] of routes) {
    for (const options of [{},{identity:'another-test-user'}]) {
      const result = await request(method,path,data,options);
      assert.ok([401,403].includes(result.status), `${method} ${path} unexpectedly permitted a non-owner`);
    }
  }
  for (const options of [{},{identity:'another-test-user'}]) {
    const result = await request('GET','/api/auth/session',undefined,options);
    assert.equal(result.status,200); assert.equal(result.body.authenticated,false);
    assert.ok(!result.body.csrf_token,'A non-owner must not receive a CSRF token');
  }
});

test('owner mutations require CSRF and invalid attempts leave state unchanged', async () => {
  await ownerSession();
  const posting = await createJob({ status:'published' });
  const receipt = await request('POST',`/api/jobs/${posting.id}/applications`,applicant);
  assert.equal(receipt.status,201);
  for (const token of ['', 'incorrect-test-token']) {
    for (const [method,path,data] of [['POST','/api/admin/jobs',job()],['PATCH',`/api/admin/jobs/${posting.id}`,{status:'closed'}],['PATCH',`/api/admin/applications/${receipt.body.id}`,{status:'hired',note:'Must not save'}]]) {
      assert.equal((await request(method,path,data,{owner:true,token})).status,403);
    }
  }
  const postings = (await request('GET','/api/admin/jobs',undefined,{owner:true})).body.jobs;
  assert.equal(postings.length,121);
  assert.equal(postings.find(row => row.id===posting.id).status,'published');
  const applications = (await request('GET','/api/admin/applications',undefined,{owner:true})).body.applications;
  assert.equal(applications[0].status,'new');
});

test('job and applicant validation reject invalid inputs', async () => {
  await ownerSession();
  for (const changes of [{title:''},{status:'imaginary'},{work_mode:'Anywhere'},{employment_type:'Temporary'},{description:''}]) {
    assert.equal((await request('POST','/api/admin/jobs',job(changes),{owner:true})).status,400);
  }
  const posting = await createJob({status:'published'});
  for (const changes of [{name:''},{email:'invalid'},{portfolio_url:'javascript:alert(1)'},{statement:''}]) {
    assert.equal((await request('POST',`/api/jobs/${posting.id}/applications`,{...applicant,...changes})).status,400);
  }
});

test('draft role remains private and cannot accept an application', async () => {
  await ownerSession(); const posting = await createJob();
  assert.ok(!(await request('GET','/api/jobs')).body.jobs.some(row => row.id===posting.id));
  assert.equal((await request('GET',`/api/jobs/${posting.id}`)).status,404);
  assert.equal((await request('POST',`/api/jobs/${posting.id}/applications`,applicant)).status,404);
});

test('publish, apply, review, database reopen, and close preserve the whole lifecycle', async () => {
  await ownerSession(); const posting = await createJob();
  assert.equal((await request('PATCH',`/api/admin/jobs/${posting.id}`,{status:'published'},{owner:true})).status,200);
  assert.equal((await request('GET',`/api/jobs/${posting.id}`)).status,200);
  const receipt = await request('POST',`/api/jobs/${posting.id}/applications`,applicant);
  assert.equal(receipt.status,201); assert.ok(receipt.body.reference);
  assert.equal((await request('POST',`/api/jobs/${posting.id}/applications`,applicant)).status,409);
  const review = await request('PATCH',`/api/admin/applications/${receipt.body.id}`,{status:'reviewing',note:'Read portfolio and project evidence.'},{owner:true});
  assert.equal(review.status,200);
  env.DB.close(); env.DB = new D1Adapter(databasePath);
  const applications = (await request('GET','/api/admin/applications',undefined,{owner:true})).body.applications;
  const preserved = applications.find(row => row.id===receipt.body.id);
  assert.equal(preserved.status,'reviewing'); assert.equal(preserved.note,'Read portfolio and project evidence.');
  assert.equal((await request('GET','/api/jobs')).body.jobs.length,121,'Reopening must preserve the user role without duplicate seeds');
  assert.equal((await request('PATCH',`/api/admin/jobs/${posting.id}`,{status:'closed'},{owner:true})).status,200);
  assert.ok(!(await request('GET','/api/jobs')).body.jobs.some(row => row.id===posting.id));
  assert.equal((await request('GET',`/api/jobs/${posting.id}`)).status,404);
  assert.equal((await request('POST',`/api/jobs/${posting.id}/applications`,{...applicant,email:'late@example.test'})).status,404);
});

test('country, state, city, and state search constrain public results', async () => {
  const query = new URLSearchParams({country:'India',state:'Maharashtra'});
  const rows = (await request('GET','/api/jobs?'+query)).body.jobs;
  assert.ok(rows.length>0); assert.ok(rows.every(row => row.country==='India' && row.state==='Maharashtra'));
  query.set('location',rows[0].location);
  const cityRows = (await request('GET','/api/jobs?'+query)).body.jobs;
  assert.ok(cityRows.length>0); assert.ok(cityRows.every(row => row.location===rows[0].location));
  assert.equal((await request('GET','/api/jobs?country=Australia&state=Maharashtra')).body.jobs.length,0);
  const search = (await request('GET','/api/jobs?search=Maharashtra')).body.jobs;
  assert.ok(search.length>0); assert.ok(search.every(row => row.state==='Maharashtra'));
});


test('missing or cross-site origins cannot create jobs or submit applications', async () => {
  await ownerSession(); const posting = await createJob({status:'published'});
  for (const origin of [null,'https://unrelated.example.test']) {
    assert.equal((await request('POST','/api/admin/jobs',job(),{owner:true,origin})).status,403);
    assert.equal((await request('POST',`/api/jobs/${posting.id}/applications`,applicant,{origin})).status,403);
  }
  assert.equal((await request('GET','/api/admin/applications',undefined,{owner:true})).body.applications.length,0);
});
