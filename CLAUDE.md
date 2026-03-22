# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Google Maps lead generation tool** for finding Prague businesses without websites. It scrapes Google Maps using Playwright, stores leads in SQLite, and provides a Flask dashboard for reviewing and managing them.

**Core workflow:**
1. `hunter.py` scrapes Google Maps for businesses matching predefined queries
2. Filters out businesses that have real websites (keeps those with only social media)
3. Stores leads in `leads_v2.db` SQLite database with category tags
4. Dashboard apps (`dashboard.py` / `dashboard_v2.py`) provide UI for reviewing and contacting leads

## Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (required for scraping)
playwright install chromium
```

### Running the scraper
```bash
# Full production run (100 leads per query)
python hunter.py

# Test mode (10 leads per query, faster feedback)
python hunter.py --test

# Show browser window for debugging
python hunter.py --no-headless

# Combined test with visible browser
python hunter.py --test --no-headless
```

### Running the dashboard
```bash
# Original dashboard (full page reloads on status updates)
python dashboard.py
# Access at http://localhost:5050

# V2 dashboard (AJAX updates, no page reloads)
python dashboard_v2.py
# Access at http://localhost:5051
```

## Architecture

### Database Schema
Table: `restaurants` (SQLite)
- `id`, `name`, `address`, `phone`, `rating`, `reviews_count`, `maps_url`
- `email` (placeholder, currently unused)
- `social_link` (Instagram/Facebook links found instead of websites)
- `category` (e.g., "tattoo", "dentist", "nail_salon" - set by query)
- `status` ("new", "contacted", "rejected" - managed via dashboard)

### Scraping Logic (hunter.py)

**Multi-query architecture:**
- `QUERIES` list at hunter.py:20 defines search terms and category tags
- Each query always scrolls to collect up to 200 place URLs, then scrapes them until the per-query save limit is reached
- `--test` limits saved leads per query to 10 (vs 100 in production); URL collection target is always 200
- `find_email` (hunter.py:85) is an unimplemented async stub that always returns `""`

**Website detection (hunter.py:218-241):**
- Business is **kept** if it has NO website link or only social/aggregator links
- `NON_WEBSITE_DOMAINS` whitelist: instagram.com, facebook.com, menicka.cz, etc.
- Business is **skipped** if it has a real website (not on whitelist)

**Consent handling (hunter.py:93-124):**
- Multi-strategy GDPR consent dismissal (English, Czech, German selectors)
- Called once globally before queries, then no-op on subsequent searches

**Scrolling strategy (hunter.py:148-203):**
- Locates results feed via multiple fallback selectors
- Collects place URLs while scrolling sidebar
- Stops at 200 URLs or "end of list" sentinel

### Dashboard Variants

**dashboard.py** (port 5050):
- Single status filter (new/contacted/rejected/all)
- Full page reload on status updates
- Template: `templates/index.html`

**dashboard_v2.py** (port 5051):
- **Dual filtering:** status + category filters
- AJAX status updates via `/api/status/<id>` endpoint
- Category counts respect active status filter
- WhatsApp integration with pre-filled Czech message (uses generic "provozovnu", not restaurant-specific)
- `CATEGORY_LABELS` dict (dashboard_v2.py:56) maps category slugs to display names — **must be updated when adding new entries to `QUERIES`**; currently missing `"drogerie"`
- Template: `templates/index_v2.html`

### Key Implementation Details

**Playwright usage:**
- Chromium browser, headless by default
- Random delays (800-1400ms) between requests to avoid rate limiting
- Locale set to "en-US" for consistent selectors
- Custom User-Agent to appear as regular Chrome browser

**Data extraction selectors (hunter.py:206-304):**
- Name: `h1.DUwDvf`
- Address: `button[data-item-id="address"]` aria-label
- Phone: `button[data-item-id*="phone:tel:"]` aria-label
- Rating: `div.F7nice span[aria-hidden='true']`
- Reviews: `div.F7nice span[aria-label]` (extract digits)
- Website: `a[data-item-id="authority"]` (checked to determine skip/keep)

**Database migrations (hunter.py:54-63):**
- Auto-adds missing columns (`social_link`, `category`) for backward compatibility
- Uses `PRAGMA table_info` to detect schema version
- Apply migrations safely before queries run

## Development Notes

- Python 3.13+ required (uses modern type hints like `list[str]`, `dict | None`)
- Database path hardcoded as `leads_v2.db` in both scripts
- Template folder must exist at `templates/` with `index.html` and `index_v2.html`
- No test suite currently present
- No linting configuration (no .pylintrc, .flake8, etc.)