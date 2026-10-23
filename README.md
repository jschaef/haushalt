# haushalt

A household expense tracking app. Photograph a receipt – Claude reads store,
date and every line item, suggests a category and learns from your
corrections. The dashboard shows what the household spends on average per
day, week, month and year, split into variable spending (supermarkets,
lifestyle) and fixed costs (electricity, gas, water, rent, subscriptions).

- **Capture without typing:** phone camera (installable PWA), photos and PDFs,
  several at once. Long receipts are split into tiles so nothing gets lost.
- **Review:** every receipt starts as a draft; check, correct and confirm.
  Probable duplicates are flagged.
- **Fixed costs:** monthly instalments and yearly bills are spread evenly over
  their period, so averages stay honest.
- **Utilities:** meters for electricity, gas and water; photograph the meter and
  Claude reads the value. With the tariff the app forecasts the annual
  settlement (credit or additional payment) and suggests an instalment. Annual
  bills (PDF) are read and their prices and new instalment can be taken over.
- **Bank statements:** import CAMT (XML) or CSV exports; bookings are matched
  with receipts and fixed costs automatically, the rest waits for a decision,
  so nothing is counted twice.
- **Tags:** fixed costs and bank bookings can carry tags next to their
  category (for whom or what for, e.g. a person or a holiday), with their own
  sums on the dashboard and filters; tags of a counterparty are learned.
- **Household:** several members, shared data, German and English UI. Admins
  add members and reset passwords with one-time passwords; passwords follow
  NIST SP 800-63B (at least 12 characters, no common or leaked passwords).
- **Modern UI:** bento dashboard, glass design, dark mode, animations, view
  transitions, command palette (Ctrl/⌘ K), swipe gestures on the phone.
- **Accessible:** light, dark and two high-contrast modes for low vision, on
  black or on white (larger text, no transparency or motion); every page is
  checked automatically against WCAG 2.2 AA (EN 301 549) in all four modes.

## Run with containers

```bash
cp deployment/.env.example deployment/.env    # set ANTHROPIC_API_KEY, HAUSHALT_DB_PASSWORD
docker compose -f deployment/compose.yaml up -d --build   # or: podman compose
```

Three containers: PostgreSQL (`db`), the API and the web app. Only the web app
is published, and only on `127.0.0.1:3200` of the host. The first visitor
creates the household account; more members are added in the settings.

With Podman (also on macOS): give the Podman machine at least 4 GB of memory
for the web build (`podman machine set --memory 4096` while it is stopped).
The health checks are part of `compose.yaml`, because Podman drops
`HEALTHCHECK` from images it builds in its default OCI format.

### Access from the tailnet

Login cookies are `Secure`, so the app needs HTTPS. Tailscale provides it:

```bash
sudo tailscale serve --bg 3200     # on the host running the containers
```

The app is then at `https://<machine>.<tailnet>.ts.net` for devices in the
tailnet only. Put exactly that address into `HAUSHALT_PUBLIC_ORIGIN` in
`deployment/.env` (the login checks where requests come from) and restart the
web container. (Command from the Tailscale documentation as known to the
author; not tested in this repository's CI.)

### Members and passwords

The first account is the household admin. Admins add members in the settings:
the app shows a one-time password once, which the member replaces at the first
login. A reset works the same way and ends all sessions of that account;
admins can also appoint further admins and disable accounts. Passwords need at
least 12 characters and must not be common, leaked or contain the name; there
are no special-character rules and no forced changes (NIST SP 800-63B).

If no admin can log in any more, run in the API container:

```bash
docker compose -f deployment/compose.yaml exec api python -m haushalt_api.admin list
docker compose -f deployment/compose.yaml exec api python -m haushalt_api.admin reset-password <username>
docker compose -f deployment/compose.yaml exec api python -m haushalt_api.admin make-admin <username>
```

### Data and backups

- Database: volume `haushalt-pg`. Backup: `docker compose -f deployment/compose.yaml exec db pg_dump -U haushalt haushalt > haushalt.sql`
- Receipt files and the token secret: volume `haushalt-data`.
- Receipt photos are deleted one year after the purchase date
  (`HAUSHALT_RECEIPT_PHOTO_DAYS`); positions and amounts stay.

## Develop

```bash
cd backend && uv venv .venv && uv pip install -p .venv -r requirements-dev.txt
.venv/bin/uvicorn haushalt_api.main:app --port 8300 --reload   # HAUSHALT_EXTRACTOR=fake for no API calls
npm install && npm run dev        # http://localhost:3200
```

Tests: `backend/.venv/bin/python -m pytest` (in `backend/`), `npm test`,
`npm run lint`, `npm run typecheck`, `npx playwright test` (after `npm run build`).

## Configuration (haushalt-api)

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | – | Key for reading receipts |
| `HAUSHALT_RECEIPT_MODEL` | `claude-opus-5-5` | Model for receipts (`claude-haiku-5-5` is cheaper) |
| `HAUSHALT_RECEIPT_EFFORT` | `low` | Effort level for the model |
| `HAUSHALT_EXTRACTOR` | `claude` | `fake` returns a fixed receipt (tests) |
| `HAUSHALT_DATA_DIR` | `backend/data` | Database, secret, receipt files |
| `HAUSHALT_DATABASE_URL` | SQLite in data dir | e.g. `postgresql+psycopg://user:pw@db:5432/haushalt` (compose sets it) |
| `HAUSHALT_SECRET` | random, kept in data dir | Signs login tokens |
| `HAUSHALT_ALLOW_SIGNUP` | `false` | Self-registration after the first user |
| `HAUSHALT_MAX_UPLOAD_MB` | `20` | Per file |
| `HAUSHALT_API_DOCS` | `false` | OpenAPI pages under `/api/v1/docs` |
| `HAUSHALT_RECEIPT_PHOTO_DAYS` | `365` | Days after purchase until receipt files are deleted, `0` = never |
| `HAUSHALT_POLL_MINUTES` | `15` | Polling interval for meter devices, `0` = off |
| `HAUSHALT_POLL_ALLOW_PUBLIC` | `false` | Allow polling addresses outside the local network |

Frontend: `HAUSHALT_API_URL` (default `http://127.0.0.1:8300`),
`HAUSHALT_COOKIE_SECURE` (default `true` in production),
`HAUSHALT_PUBLIC_ORIGIN` (HTTPS address the app is opened at, comma-separated).

## Roadmap

1. ✅ Receipts → review → dashboard, fixed costs, household, DE/EN
2. ✅ Utilities in depth: meter readings by photo, tariffs, settlement forecast, annual bills
3. ✅ Bank statement import (CSV/CAMT) and automatic matching with receipts
4. ✅ Automatic meter readings: device push with a token, polling of local devices
   (presets for Tasmota IR reading heads and AI-on-the-edge cameras)
