CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  team TEXT NOT NULL,
  location TEXT NOT NULL,
  country TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT '',
  work_mode TEXT NOT NULL,
  employment_type TEXT NOT NULL,
  description TEXT NOT NULL,
  responsibilities TEXT NOT NULL,
  requirements TEXT NOT NULL,
  first_90_days TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('draft','published','closed')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
--> statement-breakpoint
CREATE TABLE IF NOT EXISTS applications (
  id TEXT PRIMARY KEY,
  reference TEXT NOT NULL UNIQUE,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  portfolio_url TEXT NOT NULL,
  statement TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('new','reviewing','interview','hired','rejected')),
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(job_id,email)
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS applications_job_id ON applications(job_id);
