# Building Builders — hosted careers demo

This checkout deploys the existing careers homepage, six-role preview, full `/jobs` directory, and `/admin` CMS on Sites as a Cloudflare Worker. The source Python app is maintained at https://github.com/ishaankothiyal-designer/careers-page (branch `feature/careers-cms`).

The homepage navigation and hero follow the supplied Figma reference, using the four original PNG exports, an anchored background that gently zooms in, text/button moving 15% faster than page scroll, an iceberg following normal page scroll, and clouds that move outward on scroll. The supplied PNGs are 1× exports and are preserved without resampling. Reduced-motion visitors receive a static scene. Following sections keep the shared Dropbox-inspired design system and all candidate interactions. The hosted API uses Cloudflare D1 for jobs, applications, review status, and internal notes. The 120 seeded roles are demonstration content: 72 in India, 24 in Australia, and 24 in the UAE. No email delivery or ATS integration is configured.

The Site is owner-private for testing. ChatGPT sign-in establishes the visitor identity; only the configured owner may use the hiring CMS. Admin mutations also require a server-generated CSRF token and the matching request Origin. Passwords and the local Python database are not uploaded.

Runtime configuration is stored in Sites: `ADMIN_USER_ID`, `ADMIN_EMAIL`, and secret `CSRF_SECRET`. D1 is bound as `DB`. Schema migrations are separate from the deterministic seed dataset, and seeding preserves existing records and edits.

`python3 scripts/build.py` generates one Worker with the frontend and fonts embedded. `node tests/worker.test.mjs` checks the API using Node's SQLite engine and a D1-compatible adapter. Build output and runtime state are ignored by Git. Publish the exact pushed source commit and its matching archive through Sites.
