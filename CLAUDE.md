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
- Households (Jochen, 2026-10-27; `tenancy.py`, migration `0002`): several
  households in one installation, one login = one household (usernames
  unique across all). Every data table is `HouseholdOwned`; a session
  bound to a household (`session_user` binds it) gets `household_id =`
  on every ORM select/update/delete and on every new row, an unbound one
  sees nothing. Reading across households needs `tenancy.everywhere()`
  or `tenancy.unscoped()` (login, CLI, receipt file expiry, meter
  polling, device ingest). Background work gets the household id
  (`banking.rematch_later(household_id)`). Unique keys (category key,
  store, rules, merchant keyword, tag name, booking fingerprint) and
  settings (`HouseholdSetting`) are per household. The first signup sets
  up "Mein Haushalt"; an existing database became household 1.
  `tests/test_households.py` calls every route with an id from another
  household (404) - a new route with an id must join its ROUTES list.
- All members of a household share its data; receipts remember the uploader.
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
  counting).
- Schema changes (Jochen, 2026-10-27: Alembic): every change is a migration
  in `backend/haushalt_api/migrations/versions` (`backend/alembic.ini`,
  `alembic revision --autogenerate`, check the result); `db.migrate()`
  runs them at start. The baseline `0001` only creates missing tables and
  adds the frozen `LATER_COLUMNS`, so it also completes a database from
  before Alembic.
  `tests/test_migrations.py` fails when models and migrations differ.
- Automatic meter readings (`smartmeter.py`, `smartmeter_api.py`): device
  token push to `/api/v1/ingest/reading` (the gateway's only path without
  session/Origin, it forwards the device's Authorization header) and polling
  of local devices (SSRF-limited, http pinned to the checked IP).
- Bank (`banking.py`, `banking_api.py`): CAMT via defusedxml, CSV header
  detection by whole words. Booking status decides counting: only `counted`
  enters the statistics (`receipt`/`fixed` are counted through the receipt or
  recurring cost). Deleting those reopens linked bookings.
- Fixed costs (Jochen, 2026-10-26): linking a booking to a recurring cost
  is learned per counterparty (`RecurringRule`, several costs per payer);
  later bookings within ±20 % go to the closest learned cost, bookings
  outside its period count by themselves in its category. A new instalment
  from a bill takes over the learned payers. `db._learn_recurring` learned
  the links made before, once. Bookings remember `decided_by` (auto or
  person; older decisions count as the person's): creating, changing or
  deleting a fixed cost (or applying a bill's instalment) matches the
  app's own decisions and the open ones again (`banking.rematch`), a
  person's decisions stay.
- Own accounts (Jochen, 2026-10-23; `BankAccount`): the statement's IBAN
  (CAMT `Acct`, CSV preamble, checked with mod 97) picks or creates the
  account, a chosen account must match it (409). A booking whose
  counterparty IBAN is an own account is a transfer -> `ignored` (also on
  rematch, run when an account is saved). Fingerprints stay without the
  account so old imports still dedupe. Income is `ignored` too; the bank
  page has an "Eingänge" view for it.
- Credit cards (Jochen, 2026-10-23/26: single transactions, CSV export):
  a card statement (masked card number above the table) is an account
  with `card_number`, no IBAN; the euro "Betrag" after "Kurs" counts, the
  merchant comes from the purpose without "PAYPAL *". Card bookings keep
  their `statement_on`; a debit on another account equal to the sum of one
  card statement, booked -14..+3 days around its date, is `ignored` with
  `settles_account_id` (badge "Kartenabrechnung"), also when the card
  statement is imported after it (`settle_cards`).
- Income (Jochen, 2026-10-26): categories of kind `income` (seeded:
  salary, benefits, rent_income, interest, other_income) only for incoming
  bookings; an incoming booking counted in a spending category is a refund
  and lowers that category. Incoming money waits in `review` (learned per
  payer like spending; an income rule never counts a payment, 422 on
  PATCH). `stats.summary` adds income, balance, savings rate, open review
  sums and `monthly`; dashboard tile "Einnahmen und Ausgaben" + monthly
  chart. Spending selects use `spendingCategories()`. One-time migration
  `db._reopen_income` (marker in `app_state`) moved old ignored incoming
  bookings back to review.
- Savings accounts (Jochen, 2026-10-26): `BankAccount.kind` giro|savings
  (API reports card for card accounts). `saved_cents` in the summary = net
  transfers to savings accounts, counted on the giro side; a savings-side
  booking counts only without a mirror booking (same amount, within 3
  days). Shown as "davon aufs Sparkonto" under the balance.
- One-offs (Jochen, 2026-10-26): a person marks a booking `one_off`
  (gift, car; the matching never sets or clears it). Counted and review
  one-offs enter no category, average, chart, balance, savings rate, open
  sums or `saved_cents`; `summary.one_off` reports their sums in and out
  (tile line "Einmalig"). The bank page suggests amounts from the
  threshold in the household settings (`/bank/settings`, default 1,000 €, 0 = off).
- Merchants (Jochen, 2026-10-27; `MerchantRule`, `/bank/merchants`,
  settings tile): a keyword found as whole words in the normalized
  counterparty (purpose if it is empty) counts a payment in its category,
  last in the match order: receipt, fixed cost, learned counterparty rule
  first. Seeded once with grocery chains (`db.DEFAULT_MERCHANTS`, marker
  `merchant_rules_v1`, so removed ones stay removed). Changing the list
  and confirming a receipt re-match the app's own decisions in the
  background, so a supermarket booking counted before its receipt moves
  to the receipt instead of counting twice.
- Reset date (Jochen, 2026-10-27; `stats.reset_date`, `/stats/since`, PUT
  admins only, not in the future, null lifts it): the whole dashboard
  starts there - every period of the summary is cut to it, a previous
  period before it is not compared (`previous_total_cents` 0). Data stays.
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

- `sr-only` on a `<table>` does not hide its width (tables ignore the 1 px
  width) and makes the page scroll sideways at 320 px: put it on a wrapper.
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
