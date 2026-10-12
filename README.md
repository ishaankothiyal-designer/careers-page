# Careers studio

A locally runnable end-to-end careers prototype: an admin publishes jobs, candidates apply, and the admin reviews applications. Cars24 careers content follows the supplied *Building Builders* brief. The homepage navigation and hero follow the supplied Figma design, with a fixed background and clouds that move outward on scroll. Following sections draw from Dropbox's official brand guidance, with supporting content patterns from Tines, Apollo, Webflow, Squarespace, and TinyWins.

## Hosted test link

The deployed demo is available at <https://building-builders-careers.cars24.chatgpt.site>. Open `/jobs` for the directory and `/admin` for hiring. The Site follows its existing workspace sharing policy. Sign in with ChatGPT to view it; hosted admin access is restricted to the configured owner and uses that identity rather than the local generated password.

The hosted Worker source is in `hosting/careers-studio/`. Cloudflare D1 stores jobs, applications, statuses, and reviewer notes; runtime secrets remain in Sites. Its eight SQLite-backed API integration checks cover the hiring lifecycle, persistence, geographic filtering, identity, CSRF, and validation. The platform confirmed deployment and the database schema. Direct live HTTP/browser verification from this workspace was blocked by its network proxy.

## Run

Requires Python 3.10 or later. The application uses only Python's standard library; no npm install or build step is needed.

```sh
python3 server.py
```

Open <http://127.0.0.1:8000/> for the candidate experience and <http://127.0.0.1:8000/admin> for the CMS.

The homepage introduces the builder culture and brings a short job preview near the top. **Show more listings** opens `/jobs`, the dedicated roles directory with search, geography filters, job details, and applications.

On first startup, the server creates a local admin account and writes its generated credentials to `var/admin-access.txt`. This file, the database, and runtime data are ignored by Git and cannot be fetched through the application server. Sign in using those credentials.

For a different port or database:

```sh
python3 server.py --port 8080 --db /absolute/path/careers.db
```

To start without sample jobs, use `--no-seed` with a new database. Seeding runs once per database. Fresh databases contain 120 illustrative test vacancies: 72 across all 28 Indian states and 8 union territories, 24 across Australia’s six states and two territories, and 24 across the UAE’s seven emirates. Existing databases receive the regional catalogue once; existing postings and applications remain intact.

For a controlled admin account, set `CAREERS_ADMIN_EMAIL` and `CAREERS_ADMIN_PASSWORD` before starting the server. The password must contain at least 12 characters. Supplying a password resets the admin account at startup; keep credentials out of source files and version control.

## Test both sides

1. Sign in at `/admin`. Create a job with its problem, team, location, working model, job description, and first-90-day outcome. Save the draft.
2. Publish the job. Open the public careers page in a separate browser or private window. Drafts and closed jobs are hidden.
3. Use country, state/region, city, team, and working-model filters to find the published job, read its details, and apply with a name, email, a short account of something built, and an optional portfolio link.
4. Keep the application reference shown on the confirmation screen. Submission saves the application; no email is sent.
5. Return to the admin's applications view. Read the submission, add a note, and move it through review, interview, hired, or rejected.
6. Close the job. It disappears from the public page and no longer accepts applications. Existing applications remain available to the admin.
7. Restart the server. Jobs, applications, notes, and statuses persist in SQLite; admin sessions require signing in again.

This is a local prototype with finished presentation copy. The 120 seeded vacancies and culture stories are demonstration content, not verified active openings or approved recruitment policy. Editorial annotations and reference labels are kept out of the website. No live Darwinbox or Assembly connection is configured.

## Verification

Backend integration checks require no extra packages:

```sh
python3 -m unittest discover -s tests -p 'test_api.py' -v
```

Browser checks use Playwright and Chromium and run with an isolated database:

```sh
python3 -m pip install playwright
python3 -m playwright install chromium
python3 tests/browser_check.py
python3 tests/hero_motion_check.py
```

`CHROMIUM_EXECUTABLE_PATH` can select an existing Chromium installation. These packages are only for automated browser verification; application runtime still has no third-party dependencies.

## Project map

- `server.py`: HTTP API, validation, authentication, safe static serving, and SQLite persistence.
- `demo_jobs.py`: versioned, deterministic regional demo catalogue.
- `app/index.html`, `app/jobs.html`, `app/careers.js`, `app/public.css`: candidate journey, roles directory, published jobs, and applications.
- `app/admin.html`, `app/admin.js`, `app/admin.css`: job CMS and application review.
- `app/tokens.css`, `app/base.css`: the shared visual and control system.
- `app/fonts/`: self-hosted Geist and Space Grotesk fonts, with their Open Font Licenses.
- `tests/`: isolated integration and real-browser checks.

## Design sources and limits

The hero uses the four original PNG files supplied in `hero-assets.zip`, without resampling. They are 1× exports: background 1728×781, iceberg 876×361, and clouds 488×315 each. Dedicated checks cover image loading and proportions, fixed-background geometry, cloud exit and reverse motion, reduced motion, seven viewport widths, and navigation through an application.

Dropbox's [colour](https://brand.dropbox.com/color), [typography](https://brand.dropbox.com/typography), [motion](https://brand.dropbox.com/motion), and [imagery](https://brand.dropbox.com/imagery) guidance informed the system. Its [careers](https://www.dropbox.jobs/en/) and [Emerging Talent](https://www.dropbox.jobs/en/emerging-talent/) pages informed ownership and project storytelling. References checked 12 October 2026.

DB Sharp Grotesk is not bundled; the prototype uses Space Grotesk for display type and Geist for body text. Exact live-site animation and geometry were not visually verified because reference-site browser access was blocked. This is a Dropbox-inspired interpretation with one consistent design system, rather than a pixel-matched clone.
