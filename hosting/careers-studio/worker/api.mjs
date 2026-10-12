import seedJobs from './seed.mjs';

const JOB_FIELDS = ['title', 'team', 'location', 'country', 'state', 'work_mode', 'employment_type', 'description', 'responsibilities', 'requirements', 'first_90_days', 'status'];
const JOB_STATUSES = ['draft', 'published', 'closed'];
const APPLICATION_STATUSES = ['new', 'reviewing', 'interview', 'hired', 'rejected'];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const APPLICATION_SELECT = 'SELECT applications.*, jobs.title AS job_title FROM applications JOIN jobs ON jobs.id=applications.job_id';
const SEED_VERSION = 'regional-demo-v2';

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
function json(data, status = 200) {
  return new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}});
}
function text(data, key, max = 200, required = true) {
  const value = data[key] === undefined ? '' : data[key];
  if (typeof value !== 'string') throw new ApiError(400, `${key} must be text.`);
  const clean = value.trim();
  if (required && !clean) throw new ApiError(400, `${key} is required.`);
  if (clean.length > max) throw new ApiError(400, `${key} must be ${max} characters or fewer.`);
  return clean;
}
async function body(request) {
  if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') throw new ApiError(415, 'Use application/json.');
  const claimed = Number(request.headers.get('content-length') || 0);
  if (claimed > 65536) throw new ApiError(413, 'Request body must be at most 64 KB.');
  // Bound actual bytes too; a missing or inaccurate Content-Length is not trusted.
  const reader = request.body?.getReader();
  if (!reader) throw new ApiError(400, 'Request body must be JSON.');
  const chunks = []; let length = 0;
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > 65536) { await reader.cancel(); throw new ApiError(413, 'Request body must be at most 64 KB.'); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  let data;
  try { data = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes)); }
  catch { throw new ApiError(400, 'Invalid JSON.'); }
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new ApiError(400, 'JSON body must be an object.');
  return data;
}
function validateJob(data, defaultStatus = 'draft') {
  const clean = {};
  for (const field of JOB_FIELDS.filter(field => field !== 'status')) clean[field] = text(data, field, ['description', 'responsibilities', 'requirements', 'first_90_days'].includes(field) ? 12000 : 200, field !== 'state');
  clean.status = data.status === undefined ? defaultStatus : data.status;
  for (const [field, choices] of [['status', JOB_STATUSES], ['work_mode', ['On-site', 'Hybrid', 'Remote']], ['employment_type', ['Full-time', 'Part-time', 'Contract', 'Internship']]]) {
    if (!choices.includes(clean[field])) throw new ApiError(400, `Invalid ${field}.`);
  }
  return clean;
}
function owner(request, env) {
  const identity = request.headers.get('oai-authenticated-user-id');
  return Boolean(env.ADMIN_USER_ID && identity && identity === env.ADMIN_USER_ID);
}
async function csrf(env) {
  if (!env.CSRF_SECRET || !env.ADMIN_USER_ID) throw new ApiError(503, 'Admin configuration is unavailable.');
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', encoder.encode(env.CSRF_SECRET), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(`careers-admin:${env.ADMIN_USER_ID}`));
  return Array.from(new Uint8Array(signature), byte => byte.toString(16).padStart(2, '0')).join('');
}
function sameOrigin(request) {
  const origin = request.headers.get('origin');
  if (!origin || origin !== new URL(request.url).origin || request.headers.get('sec-fetch-site') === 'cross-site') throw new ApiError(403, 'Request origin is not allowed.');
}
async function requireAdmin(request, env, mutate = false) {
  if (!owner(request, env)) throw new ApiError(401, 'Sign in to continue.');
  if (mutate) {
    const expected = await csrf(env), actual = request.headers.get('x-csrf-token') || '';
    let mismatch = actual.length ^ expected.length;
    for (let i = 0; i < expected.length; i++) mismatch |= expected.charCodeAt(i) ^ (actual.charCodeAt(i) || 0);
    if (mismatch) throw new ApiError(403, 'Invalid CSRF token. Refresh and try again.');
  }
}
function identity() { return crypto.randomUUID().replaceAll('-', ''); }
function timestamp() { return new Date().toISOString(); }
async function rows(statement) { return (await statement.all()).results || []; }

export async function ensureSeed(db) {
  const marker = await db.prepare("SELECT value FROM metadata WHERE key='demo_seed_version'").first();
  if (marker?.value === SEED_VERSION) return;
  const columns = ['id', ...JOB_FIELDS, 'created_at', 'updated_at'];
  const stamp = timestamp();
  const statements = seedJobs.map(job => db.prepare(`INSERT INTO jobs (${columns.join(',')}) VALUES (${columns.map(() => '?').join(',')}) ON CONFLICT(id) DO NOTHING`).bind(job.id, ...JOB_FIELDS.map(field => job[field] ?? ''), job.created_at || stamp, job.updated_at || stamp));
  statements.push(db.prepare("INSERT INTO metadata(key,value) VALUES ('demo_seed_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(SEED_VERSION));
  // D1 batch is transactional. Stable IDs protect concurrent initialization and admin edits.
  await db.batch(statements);
}

export async function handleApi(request, env) {
  try {
    const url = new URL(request.url), path = url.pathname.replace(/\/$/, ''), method = request.method;
    if (method !== 'GET') sameOrigin(request);
    if (path === '/api/auth/session' && method === 'GET') {
      return json(owner(request, env) ? {authenticated: true, email: env.ADMIN_EMAIL || 'Site owner', csrf_token: await csrf(env)} : {authenticated: false});
    }
    if (path === '/api/auth/login' && method === 'POST') throw new ApiError(401, 'Use ChatGPT sign-in to access the admin.');
    if (path === '/api/auth/logout' && method === 'POST') {
      await requireAdmin(request, env, true);
      return json({ok: true, logout_url: '/signout-with-chatgpt?return_to=/admin'});
    }
    const admin = path.startsWith('/api/admin/');
    if (admin) await requireAdmin(request, env, method !== 'GET');
    await ensureSeed(env.DB);
    if (path === '/api/jobs' && method === 'GET') {
      let sql = "SELECT * FROM jobs WHERE status='published'"; const params = [];
      for (const field of ['team', 'location', 'country', 'state', 'work_mode']) {
        if (url.searchParams.get(field)) { sql += ` AND ${field}=?`; params.push(url.searchParams.get(field)); }
      }
      const search = url.searchParams.get('search');
      if (search) {
        sql += ' AND (' + ['title', 'team', 'description', 'location', 'country', 'state'].map(field => `instr(lower(${field}),?)>0`).join(' OR ') + ')';
        params.push(...Array(6).fill(search.toLowerCase()));
      }
      return json({jobs: await rows(env.DB.prepare(sql + ' ORDER BY created_at DESC,id').bind(...params))});
    }
    const publicMatch = path.match(/^\/api\/jobs\/([a-zA-Z0-9_-]+)(\/applications)?$/);
    if (publicMatch) {
      const [, jobId, applications] = publicMatch;
      const job = await env.DB.prepare("SELECT * FROM jobs WHERE id=? AND status='published'").bind(jobId).first();
      if (!job) throw new ApiError(404, 'This role is no longer available.');
      if (!applications && method === 'GET') return json({job});
      if (applications && method === 'POST') {
        const data = await body(request), name = text(data, 'name', 150), email = text(data, 'email', 254).toLowerCase();
        const statement = text(data, 'statement', 6000), portfolio = text(data, 'portfolio_url', 2048, false);
        if (!EMAIL.test(email)) throw new ApiError(400, 'Enter a valid email address.');
        if (portfolio) {
          let parsed; try { parsed = new URL(portfolio); } catch { throw new ApiError(400, 'Portfolio URL must be an http or https link.'); }
          if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password) throw new ApiError(400, 'Portfolio URL must be an http or https link.');
        }
        if (await env.DB.prepare('SELECT 1 FROM applications WHERE job_id=? AND email=?').bind(jobId, email).first()) throw new ApiError(409, 'You have already applied for this role with this email address.');
        const id = identity(), reference = 'BLD-' + identity().slice(0, 8).toUpperCase(), stamp = timestamp();
        // Recheck published status in the INSERT itself so a concurrent closure wins safely.
        const inserted = await env.DB.prepare("INSERT INTO applications(id,reference,job_id,name,email,portfolio_url,statement,status,note,created_at,updated_at) SELECT ?,?,?,?,?,?,?,'new','',?,? FROM jobs WHERE id=? AND status='published'").bind(id, reference, jobId, name, email, portfolio, statement, stamp, stamp, jobId).run();
        if (!inserted.meta?.changes) throw new ApiError(404, 'This role is no longer available.');
        return json({id, reference, job_title: job.title, created_at: stamp, message: 'Application received. Save your reference for your records.'}, 201);
      }
    }
    if (path === '/api/admin/jobs') {
      if (method === 'GET') return json({jobs: await rows(env.DB.prepare('SELECT jobs.*, (SELECT count(*) FROM applications WHERE job_id=jobs.id) AS application_count FROM jobs ORDER BY created_at DESC,id'))});
      if (method === 'POST') {
        const clean = validateJob(await body(request)), id = identity(), stamp = timestamp();
        const columns = ['id', ...JOB_FIELDS, 'created_at', 'updated_at'];
        await env.DB.prepare(`INSERT INTO jobs (${columns.join(',')}) VALUES (${columns.map(() => '?').join(',')})`).bind(id, ...JOB_FIELDS.map(field => clean[field]), stamp, stamp).run();
        return json({job: await env.DB.prepare('SELECT * FROM jobs WHERE id=?').bind(id).first()}, 201);
      }
    }
    const jobMatch = path.match(/^\/api\/admin\/jobs\/([a-zA-Z0-9_-]+)$/);
    if (jobMatch && ['PUT', 'PATCH'].includes(method)) {
      const id = jobMatch[1], existing = await env.DB.prepare('SELECT * FROM jobs WHERE id=?').bind(id).first();
      if (!existing) throw new ApiError(404, 'Role not found.');
      const data = await body(request); let clean;
      if (method === 'PUT') clean = validateJob(data, existing.status);
      else {
        if (!JOB_STATUSES.includes(data.status)) throw new ApiError(400, 'Invalid status.');
        clean = {status: data.status};
      }
      await env.DB.prepare(`UPDATE jobs SET ${Object.keys(clean).map(field => `${field}=?`).join(',')},updated_at=? WHERE id=?`).bind(...Object.values(clean), timestamp(), id).run();
      return json({job: await env.DB.prepare('SELECT * FROM jobs WHERE id=?').bind(id).first()});
    }
    if (path === '/api/admin/applications' && method === 'GET') {
      const conditions = [], params = [];
      for (const field of ['job_id', 'status']) if (url.searchParams.get(field)) { conditions.push(`applications.${field}=?`); params.push(url.searchParams.get(field)); }
      const search = url.searchParams.get('search');
      if (search) { conditions.push('(instr(lower(applications.name),?)>0 OR instr(lower(applications.email),?)>0 OR instr(lower(jobs.title),?)>0)'); params.push(...Array(3).fill(search.toLowerCase())); }
      return json({applications: await rows(env.DB.prepare(APPLICATION_SELECT + (conditions.length ? ' WHERE ' + conditions.join(' AND ') : '') + ' ORDER BY applications.created_at DESC,applications.id').bind(...params))});
    }
    const applicationMatch = path.match(/^\/api\/admin\/applications\/([a-zA-Z0-9_-]+)$/);
    if (applicationMatch && method === 'PATCH') {
      const id = applicationMatch[1];
      if (!await env.DB.prepare('SELECT 1 FROM applications WHERE id=?').bind(id).first()) throw new ApiError(404, 'Application not found.');
      const data = await body(request), clean = {};
      if ('status' in data) {
        if (!APPLICATION_STATUSES.includes(data.status)) throw new ApiError(400, 'Invalid application status.');
        clean.status = data.status;
      }
      if ('note' in data) clean.note = text(data, 'note', 6000, false);
      if (!Object.keys(clean).length) throw new ApiError(400, 'Provide a status or note.');
      await env.DB.prepare(`UPDATE applications SET ${Object.keys(clean).map(field => `${field}=?`).join(',')},updated_at=? WHERE id=?`).bind(...Object.values(clean), timestamp(), id).run();
      return json({application: await env.DB.prepare(APPLICATION_SELECT + ' WHERE applications.id=?').bind(id).first()});
    }
    throw new ApiError(404, 'Endpoint not found.');
  } catch (error) {
    if (error instanceof ApiError) return json({error: error.message}, error.status);
    if (/UNIQUE constraint failed/i.test(String(error?.message))) return json({error: 'This record already exists.'}, 409);
    return json({error: 'Something went wrong. Please try again.'}, 500);
  }
}
