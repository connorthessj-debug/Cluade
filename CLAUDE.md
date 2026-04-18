# CLAUDE.md

Guidance for AI assistants (and developers) working in this repository.
**This file is the project's persistent memory** — it is read automatically at
the start of every Claude Code session, and because it lives in git it syncs
across every device that clones the repo. Update it whenever the ground truth
changes (new tooling, new conventions, finished/abandoned work, known issues).

## Project Overview

**Cluade** is the website and admin tooling for *Le Besian Balls* — a
handcrafted cake-ball shop in Kiefer, Oklahoma. Stack:

- **Frontend**: static HTML + vanilla JS (`js/app.js`, `js/square-payments.js`),
  `css/style.css`. Content driven by `data/content.json`.
- **Admin dashboard**: `admin/` — vanilla JS editing UI backed by `api/admin-api.php`.
- **Payments**: Square Web Payments SDK on the client, `api/process-payment.php`
  server-side (currently placeholder credentials, cURL implementation).
- **Scheduler utility**: `generate_schedule.py` — unrelated SSD police-schedule
  generator; produces `schedule_options.xlsx` with 3 shift-option sheets.

## Repository Structure

```
Cluade/
├── CLAUDE.md              # AI guidance + persistent memory (this file)
├── README.md
├── index.html             # Public storefront
├── admin/                 # Admin dashboard (JS + HTML + CSS)
├── api/                   # PHP endpoints (admin CRUD, Square payment)
├── css/                   # Site styles
├── data/content.json      # Canonical site content (edited via admin)
├── js/                    # Frontend JS (app, square payments)
├── generate_schedule.py   # Excel schedule generator
├── schemas/               # JSON Schema definitions
├── tests/
│   ├── python/            # pytest — schedule generator
│   ├── php/               # PHPUnit — API endpoints
│   └── js/                # vitest + jsdom — frontend + schema
└── .github/workflows/     # CI (pytest, phpunit, vitest)
```

## Running Tests

```bash
# Python
pip install -r requirements-dev.txt
pytest

# PHP
composer install
vendor/bin/phpunit

# JS
npm install
npm test
```

All three suites run in CI on every push / PR via `.github/workflows/tests.yml`.

## Development Workflow

### Branching
- Default branch: `main`
- Feature branches use the `claude/` prefix (e.g., `claude/feature-name-<id>`)
- Always push with `git push -u origin <branch-name>`

### Commits
- Imperative mood in subjects ("Add feature", not "Added feature")
- One logical change per commit

### Code Style
- Follow existing patterns
- Prefer editing existing files over creating new ones
- No over-engineering — add only what the task requires

## Persistent Memory Protocol

The repo itself is the memory. To keep state across context clears and across
devices:

1. **Record decisions and state here.** When a session ends mid-work, append a
   bullet to "Current State" describing where things stand and what's next.
2. **Commit and push.** Memory only syncs once it's pushed to the remote. A
   new session on any device starts by reading this file.
3. **Don't drop stale entries silently** — move finished items to "History"
   so we can see progression. When an assumption in this file is disproven,
   edit it.
4. For session-specific notes that shouldn't be committed (e.g., one-off
   exploration), use a local `.claude-notes.md` that is gitignored.

## Current State

_Last updated: 2026-04-18 on branch `claude/analyze-test-coverage-eHeNI`._

- **Test coverage audit complete.** Baseline was 0% (no tests, no framework).
  Scaffolded three suites totaling 55 tests, all passing locally:
  - `tests/python/` — 19 tests. Pins option A/B/C branching for Lester/Blaine,
    8-hour-shift invariant, xlsx round-trip.
  - `tests/php/` — 12 tests. Spins up PHP built-in server in-process; covers
    admin-api load/save/backup/invalid-JSON/OPTIONS/CORS and payment input
    validation. Includes a regression marker for the missing auth.
  - `tests/js/` — 24 tests. Loads `js/app.js` + `js/square-payments.js` into
    a jsdom window via a bridge helper (`tests/js/helpers/loadApp.js`);
    covers cart mutations, checkout math (delivery fee threshold), renderers,
    `content.json` schema validation, and an XSS regression marker.
- **JSON Schema** for `data/content.json` lives at `schemas/content.schema.json`
  and is validated in the JS suite.
- **CI** runs all three suites: `.github/workflows/tests.yml`.

### Known Issues / Risk Areas (discovered during audit)

These are documented as regression markers in the tests where possible. Fix
in priority order:

1. **`api/admin-api.php` has no auth.** The TODO block at lines 23–32 is
   unimplemented; `action=save` is reachable by anyone.
   `AdminApiTest::test_unauthenticated_save_currently_allowed_regression_marker`
   will flip when this is fixed.
2. **Payment credentials are placeholders** in both
   `api/process-payment.php` and `js/square-payments.js`. Make the Square
   base URL and access token injectable so happy-path payment flow can be
   tested against a fake Square server.
3. **XSS in `menuCard()` and admin slide renderers.** `item.name` /
   `item.description` are interpolated into `innerHTML` without escaping.
   See `tests/js/renderers.test.js` "XSS exposure" block.
4. **`getCartTotal()` silently skips unknown ids.** Documented in
   `tests/js/cart.test.js`; consider logging or surfacing these instead.
5. **`data/content.json` lacks runtime validation** server-side. Admin-api
   `save` writes whatever JSON it gets; validate against
   `schemas/content.schema.json` before persisting.

### Next Up (proposed)

- Add Square HTTP injection point so `process-payment.php` can be tested
  against a fake upstream; currently only input validation is covered.
- Wire `schemas/content.schema.json` into `api/admin-api.php` save path.
- Add lint/format config (ruff for Python, phpcs for PHP, prettier/eslint
  for JS) and include them in CI.
- Implement admin auth per issue #1 above; update the regression marker.

## History

- 2026-04-18 — Initial test-coverage audit + scaffolding on branch
  `claude/analyze-test-coverage-eHeNI`. 55 passing tests across Python, PHP,
  and JS. Added JSON Schema for content and GitHub Actions workflow.

## For AI Assistants

- **Read this file first** each session — it's the project memory.
- Read existing files before proposing changes.
- Do not create files unless necessary.
- Match the style and conventions already present in the codebase.
- When you finish meaningful work, update "Current State" and "History",
  then commit and push so future sessions (and other devices) pick it up.
- When in doubt, ask the user for clarification.
