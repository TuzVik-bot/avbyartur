# Dealer analytics and indexing deployment

Verified 2026-10-14 on https://suite-s1.denjik.by.

- Feature commit: `4400788`, branch `codex/dealer-analytics-indexing-20261014`.
- Active release: `/home/suite/apps/releases/dealer-analytics-indexing-20261014-4400788-r2`.
- Release copied from `site-assistant-20261014-f4d9d9a`, then overlaid only committed feature files. Its SiteAssistant root-layout additions were preserved.
- API/worker image: `avtorinok-api:dealer-analytics-20261014-4400788`.
- Web image: `avtorinok-web:dealer-analytics-20261014-4400788-r2`.
- Alembic: `0026_dealer_click_events (head)`.
- Backup: `/home/suite/avtorinok-backups/avtorinok-20261014T064929Z`. All SHA256 checks passed; PostgreSQL dump TOC readable. Licensed source directory was absent; backup used the script's explicit empty-licensed recovery mode.
- Nginx backup: `/etc/nginx/sites-available/suite-s1.denjik.by.pre-indexing-20261014-4400788`. Only global X-Robots-Tag removed. Configuration test and reload passed via authorized Docker host namespace access.

## Verification

- Frontend: 42 focused tests, typecheck, VPS production build passed.
- Backend: 8 integration/route-contract tests passed on a dedicated disposable PostgreSQL database.
- Migration: clean chain through 0025, upgrade 0026 and repeat upgrade passed on disposable PostgreSQL.
- Public HTTPS homepage: HTTP 200, robots and googlebot `index, follow`, no noindex response header.
- Account/login retain noindex response headers. Anonymous dealer analytics returns 401. Invalid click payload returns 422.
- robots.txt and sitemap.xml return 200.
- Browser `/login?next=%2Fsell`: Create Account opens name, email, password, repeat password, both consent checkboxes and Register button. No account created.
- All five Compose services healthy; .env remains 600; original named DB/media volumes retained.
- Data before/after: 27 users, 0 companies, 204 listings. No synthetic production data inserted.

## Scope and limits

Counts clicks from a public listing to its company profile on this portal, grouped by listing and selected date range. These are clicks, not unique visitors, external-site purchases or confirmed sales. Historical clicks cannot be recovered. With no production companies, real company-account statistics could not be browser-verified; the integration tests cover recording and company-scoped reporting.

## Rollback

Switch application symlink to `site-assistant-20261014-f4d9d9a` and recreate API, worker and web using that release's saved image override, without deleting volumes. The additive click table can remain. To restore the previous indexing restriction, restore the Nginx backup, test and reload. Database/media restore is unnecessary for an application-only rollback.
