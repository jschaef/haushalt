@AGENTS.md

# haushalt

Household expense tracker: receipts are photographed or uploaded, read by
Claude (vision + structured outputs) and shown as averages per day, week,
month and year. Next.js 16 frontend (`app/`, `components/`, `lib/`) plus
haushalt-api (`backend/`, FastAPI, prefix `/api/v1`). Layout and tooling
follow jschaef/sarfile_analyzer_web, which is only a template.

## Project memory: cloud-memory and cloud-inbox

- **Read before assuming.** Decisions, architecture, findings and bugs of this
  project are in cloud-memory (`search_cloud_memory`, German) and, not yet
  reviewed, in cloud-inbox (`search_cloud_inbox`, haushalt notes in English:
  search German AND English). Search both before changing how something
  works. Start with "haushalt app decisions". Never delete inbox entries.
- **Recurring errors** (Jochen, 2026-10-22): when an error happens a second
  time, record it in cloud-inbox as a recurring error, and search the inbox
  for "recurring error haushalt" now and then, at the latest before larger
  changes.
- **Write as you go.** New decisions by Jochen, root causes of bugs, pitfalls
  and measured results go to cloud-inbox (`store_cloud_inbox`), one topic per
  point, in English, never into files of this public repository.

## Working rules (Jochen)

- Talk to Jochen in German. Code, comments, commit messages, notes in English.
- Small topic commits, only after the checks below pass. No `Co-Authored-By`.
- Never push to `main`, never merge; PRs only when asked.
- Security is part of every change (see "Security" below).
- Use cheaper models (subagents) for routine work where quality allows.

## Checks before a commit

```bash
(cd backend && .venv/bin/python -m pytest -q)   # API, incl. security tests
npm run lint && npm run typecheck && npm test   # vitest: lib/**/*.test.ts
npm run build
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium npx playwright test
```

Backend venv: `cd backend && uv venv .venv && uv pip install -p .venv -r requirements-dev.txt`.
`npm install` needs `legacy-peer-deps` (set in `.npmrc`). CI runs all of
this on every push and nightly (`.github/workflows/ci.yml`).

## Architecture in short

- Browser → Next.js only. `app/api/v1/[...path]/route.ts` forwards to the API
  (address `HAUSHALT_API_URL`, read at runtime) and adds the bearer token from
  the httpOnly cookie `haushalt_session`. Login/signup/logout: `app/api/auth/*`.
- Operation (Jochen, 2026-10-22): self-hosted with PostgreSQL in compose,
  access via the tailnet (`tailscale serve` -> HTTPS, web bound to
  127.0.0.1, `HAUSHALT_PUBLIC_ORIGIN` for the Origin check), receipt files
  deleted after one year (`receipts.expire_files`, daily). Tests run on
  SQLite; set `HAUSHALT_TEST_DATABASE_URL` to run them on PostgreSQL (CI
  job `backend-postgres`). PostgreSQL enforces string lengths - truncate.
- All household members share all data; receipts remember the uploader.
- Members (Jochen, 2026-10-23): the first account is admin; only admins add
  members, reset passwords and disable accounts. Adding and resetting give a
  one-time password (`must_change_password`): until it is replaced every
  route behind `current_user` answers 403 `password_change_required`, only
  `session_user` routes (`/me`, `/me/password`) work. Raising
  `users.token_version` ends all sessions of an account (password change,
  reset, disabling). Emergency CLI: `python -m haushalt_api.admin`.
- Money is integer cents everywhere. Statistics (`backend/haushalt_api/stats.py`):
  calendar days, only confirmed receipts, recurring costs spread over their
  interval, variable vs. fixed by category kind.
- Receipt reading (`extraction.py`): `HAUSHALT_EXTRACTOR=claude|fake`; tall
  photos are cut into tiles (the API downsizes to ~1568 px). Model
  `HAUSHALT_RECEIPT_MODEL` (default `claude-opus-5-5`, server-side fallback on).
- Categories: learned rule (normalized item text) → model suggestion → store default.
- Tags (Jochen, 2026-10-23; `tags_api.py`): for whom/what for, next to the one
  category, only on bank bookings (status `counted`) and recurring costs.
  Tag sums overlap (no shares). Learned per bank counterparty like the
  category (`TagRule`, the latest decision replaces the set). `tag_ids`
  missing in a recurring update keeps the tags.
- Utilities (`utilities.py`, `utilities_api.py`): meters, readings (must count
  up), tariffs, bills. The dashboard counts the instalments only; consumption
  costs and the settlement forecast live on the utilities page (no double
  counting). New columns on existing tables need an entry in
  `db._LATER_COLUMNS` (create_all never alters tables).
- Automatic meter readings (`smartmeter.py`, `smartmeter_api.py`): device
  token push to `/api/v1/ingest/reading` (the gateway's only path without
  session/Origin, it forwards the device's Authorization header) and polling
  of local devices (SSRF-limited, http pinned to the checked IP).
- Bank (`banking.py`, `banking_api.py`): CAMT via defusedxml, CSV header
  detection by whole words. Booking status decides counting: only `counted`
  enters the statistics (`receipt`/`fixed` are counted through the receipt or
  recurring cost). Deleting those reopens linked bookings.
- Themes (`lib/themes.ts`, next-themes): `light`, `dark` and two low-vision
  modes in `app/globals.css`, `contrast` (black/white/yellow) and
  `contrast-light` (black on white, dark blue), both 118.75 % text, opaque,
  no motion via `components/motion-mode.tsx`. The eye button keeps the
  lightness, the sun/moon button keeps the low-vision mode. Only `contrast`
  uses the Tailwind `dark:` variant.
- Accessibility baseline (Jochen: follow the standards): WCAG 2.2 level AA as
  referenced by EN 301 549 V4.1.1 (BFSG). `e2e/a11y.spec.ts` runs axe
  (wcag2a-22aa, serious/critical) on every page in all four themes, checks
  reflow at 320 px (1.4.10), focus not obscured by the sticky bars (2.4.11)
  and no sideways scrolling in high contrast - add new pages to its PAGES list.
- i18n: `lib/i18n/messages.ts` (de reference, en typed against it), cookie `haushalt_locale`.

## Security

- CSRF: changing requests through the gateway and the auth routes need a
  matching `Origin`; cookie SameSite=Lax, httpOnly, Secure in production.
- Gateway accepts only plain path segments (no `..`).
- Uploads: type from magic bytes, size limit, Pillow pixel limit; files are
  served with `nosniff` and a sandbox CSP.
- Login: scrypt hashes (NFKC-normalized), per-user/address failure limit,
  revocable tokens plus a per-account token version.
- Password policy (`passwords.py`, NIST SP 800-63B, Jochen: 12 characters):
  length, a list of common/leaked passwords (`data/common-passwords.txt.gz`,
  SecLists, MIT), context words, repeated/sequential characters; no
  composition rules, no forced rotation. `lib/password.ts` mirrors the
  length rule for hints only.
- Security headers (CSP, frame-ancestors none) in `next.config.ts`.
- Containers run unprivileged, read-only, all capabilities dropped.

## Pitfalls

- Hand-written `backdrop-filter` pairs lose their unprefixed half in the CSS
  minifier: use Tailwind `backdrop-*` utilities or the `--tw-backdrop-*` vars.
- Next.js 16: `proxy.ts` is the middleware. Read `node_modules/next/dist/docs/`.
- A reverse proxy must pass the Host header with port (Origin check).
- `HAUSHALT_COOKIE_SECURE=true` (default in production) needs HTTPS, else
  login silently fails because the browser drops the cookie.
- Podman builds OCI images and drops `HEALTHCHECK`; compose `depends_on:
  service_healthy` needs the health checks in `compose.yaml` itself. Podman
  runs health checks from systemd timers, so in a container without systemd
  they never run (test with `podman healthcheck run` in a loop).
- In cloud sessions Docker Hub may answer 429: build with
  `--build-arg REGISTRY=mirror.gcr.io/library`; the session proxy's CA must be
  added to test base images (see the cloud-inbox note on container builds).
