# CLAUDE.md

This file provides guidance for AI assistants (and developers) working in this repository.

## Project Overview

This repository contains **Le Besian Balls** — a full-stack e-commerce website for a handcrafted cake balls and truffles business based in Kiefer, Oklahoma. The site includes a customer-facing storefront with online ordering, a Square-powered payment integration, and an admin dashboard for managing content.

A separate Python utility (`generate_schedule.py`) for generating employee shift schedules is also included.

## Repository Structure

```
Cluade/
├── CLAUDE.md                  # AI assistant guidance (this file)
├── README.md                  # Project description
├── index.html                 # Main storefront (single-page app)
├── css/
│   └── style.css              # Storefront styles
├── js/
│   ├── app.js                 # Core storefront logic (cart, menu, UI)
│   └── square-payments.js     # Square Web Payments SDK integration
├── data/
│   └── content.json           # CMS-like data file (menu, hero, about, packs, fulfillment, social)
├── api/
│   ├── admin-api.php          # Admin CRUD API — loads/saves content.json
│   └── process-payment.php    # Square payment processing endpoint
├── admin/
│   ├── index.html             # Admin dashboard UI
│   ├── admin.js               # Admin dashboard logic
│   └── admin.css              # Admin dashboard styles
├── generate_schedule.py       # Python script to generate shift schedule XLSX
└── schedule_options.xlsx      # Generated shift schedule output
```

## Architecture

### Frontend (Storefront)
- **Vanilla HTML/CSS/JS** — no frameworks or build tools
- `index.html` is a single-page app with sections: hero carousel, weekly flavors, classics, packs, about, order/fulfillment, cart sidebar, checkout modal
- All content is loaded dynamically from `data/content.json` at runtime via `fetch()`
- Cart state is persisted in `localStorage` (key: `lb_cart`)
- Square Web Payments SDK handles card tokenization on the client side

### Backend (PHP)
- `api/admin-api.php` — loads and saves `data/content.json` (no auth currently; placeholder for authentication)
- `api/process-payment.php` — receives tokenized card data and calls Square Payments API (supports both Square PHP SDK and raw cURL)
- **Requires a PHP server** to run the API endpoints

### Admin Dashboard
- Standalone page at `admin/index.html`
- Allows editing all content sections (hero, menu, packs, about, fulfillment, announcements)
- Communicates with `api/admin-api.php` to persist changes

### Schedule Generator
- `generate_schedule.py` — standalone Python script using `openpyxl`
- Generates `schedule_options.xlsx` with 3 shift schedule variants (Options A/B/C)
- Covers morning, afternoon, night, and SSD officer shifts

## Development Workflow

### Branching

- The default branch is `main`
- Feature branches should use the `claude/` prefix (e.g., `claude/feature-name-<id>`)
- Always push feature branches with `git push -u origin <branch-name>`

### Commits

- Write clear, descriptive commit messages
- Use imperative mood in commit subjects (e.g., "Add feature" not "Added feature")
- Keep commits focused — one logical change per commit

### Code Style

- **HTML/JS/CSS**: Vanilla, no frameworks. Follow existing patterns (e.g., template literals for HTML generation in JS, BEM-ish class naming in CSS)
- **PHP**: Procedural style, JSON responses, CORS headers set per-file
- **Python**: Standard library + `openpyxl` for XLSX generation
- Keep files focused and avoid unnecessary bloat
- Prefer editing existing files over creating new ones when practical

## Key Conventions

- **No over-engineering**: Only add what is needed for the current task
- **Security first**: Never commit secrets, credentials, or `.env` files. Square API keys in the codebase are placeholders — real credentials should never be committed
- **Simplicity**: Favor straightforward solutions over clever abstractions
- **Content-driven**: Site content lives in `data/content.json` — update that file (or use the admin dashboard) rather than hardcoding values in HTML/JS

## Commands

```bash
# Run the schedule generator (requires Python 3 + openpyxl)
pip install openpyxl
python generate_schedule.py

# Serve the site locally (requires PHP)
php -S localhost:8000
# Then visit http://localhost:8000 (storefront) or http://localhost:8000/admin/ (dashboard)
```

No build system, test framework, or linting tools are configured. Update this section as tooling is added.

## Important Notes

- Square integration is in **sandbox mode**. To go live: update credentials in `js/square-payments.js` and `api/process-payment.php`, and switch the SDK script in `index.html` from `sandbox.web.squarecdn.com` to `web.squarecdn.com`
- The admin API at `api/admin-api.php` has **no authentication** — add auth before deploying to production
- The admin API creates automatic backups in `data/backups/` before each save

## For AI Assistants

- Read existing files before proposing changes
- Do not create files unless necessary
- Match the style and conventions already present in the codebase
- Content changes should go in `data/content.json`, not hardcoded in HTML/JS
- When modifying JS, follow the existing pattern of DOM manipulation with `getElementById` and template literals
- When in doubt, ask the user for clarification
