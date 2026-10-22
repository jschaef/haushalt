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
- **Household:** several members, shared data, German and English UI.
- **Modern UI:** bento dashboard, glass design, dark mode, animations, view
  transitions, command palette (Ctrl/⌘ K), swipe gestures on the phone.
- **Accessible:** light, dark and a high-contrast mode for low vision (larger
  text, no transparency or motion); every page is checked automatically
  against WCAG 2.2 AA (EN 301 549) in all three modes.

## Run with containers

```bash
cp deployment/.env.example deployment/.env    # set ANTHROPIC_API_KEY
docker compose -f deployment/compose.yaml up -d --build   # or: podman compose
```

The app listens on port 3200. Login cookies are `Secure` by default, so put
HTTPS in front (reverse proxy or a VPN that provides certificates). For a quick
plain-HTTP test: `HAUSHALT_COOKIE_SECURE=false docker compose … up`.
The first visitor creates the household account; more members are added in
the settings. Data (SQLite database, receipt files) lives in the
`haushalt-data` volume.

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
| `HAUSHALT_DATABASE_URL` | SQLite in data dir | Any SQLAlchemy URL |
| `HAUSHALT_SECRET` | random, kept in data dir | Signs login tokens |
| `HAUSHALT_ALLOW_SIGNUP` | `false` | Self-registration after the first user |
| `HAUSHALT_MAX_UPLOAD_MB` | `20` | Per file |
| `HAUSHALT_API_DOCS` | `false` | OpenAPI pages under `/api/v1/docs` |

Frontend: `HAUSHALT_API_URL` (default `http://127.0.0.1:8300`),
`HAUSHALT_COOKIE_SECURE` (default `true` in production).

## Roadmap

1. ✅ Receipts → review → dashboard, fixed costs, household, DE/EN
2. ✅ Utilities in depth: meter readings by photo, tariffs, settlement forecast, annual bills
3. ✅ Bank statement import (CSV/CAMT) and automatic matching with receipts
4. Smart meter import
