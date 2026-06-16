# Maps Hunter

**Automated lead generation tool that scrapes Google Maps to find businesses without websites — ready for outreach.**

Designed for B2B sales teams targeting specific niches in Prague (tattoo studios, dentists, nail salons, auto repair, yoga studios, barbershops). Maps Hunter collects contact details, filters out businesses that already have real websites, stores everything in a local database, and provides a web dashboard to manage and act on leads via WhatsApp.

---

## Features

- **Smart filtering** — Skips businesses with real websites; keeps those only on Instagram, Facebook, TripAdvisor, etc.
- **Automated scraping** — Playwright-driven Chromium handles GDPR consent, infinite scroll, and data extraction
- **Lead database** — SQLite storage with deduplication (unique on name + address)
- **Web dashboard** — Flask-based UI with status filtering, category badges, and AJAX updates
- **WhatsApp integration** — One-click pre-filled outreach message in Czech
- **Test mode** — Quick 10-result runs for development/validation

---

## Tech Stack

- **Python 3.10+**
- [Playwright](https://playwright.dev/python/) — browser automation
- [Flask](https://flask.palletsprojects.com/) — dashboard web server
- [SQLite3](https://docs.python.org/3/library/sqlite3.html) — local database
- BeautifulSoup4 — HTML parsing

---

## Installation

```bash
# Clone the repo
git clone <your-repo-url>
cd map-auto

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser
playwright install chromium
```

---

## Usage

### 1. Run the Scraper

```bash
# Test mode — 10 results per query, browser visible
python hunter.py --test --no-headless

# Production mode — up to 100 results per query, headless
python hunter.py

# Explicit headless flag
python hunter.py --headless
```

The scraper will:
1. Open Google Maps and accept the GDPR consent prompt
2. Search each configured query (e.g. `"Tattoo studio Praha"`)
3. Scroll through results and visit each place
4. Skip businesses with real websites
5. Save remaining leads to `leads_v2.db`
6. Print a summary table of new leads collected

**Example output:**
```
[12:34:56] Query: 'Tattoo studio Praha' (category: tattoo)
[12:34:57] Scrolling (target: 200 URLs)…
[12:35:10] Collected 142 place URLs.
  → saved: Tattoo Studio XYZ | +420...

Total new leads across all queries: 47
```

### 2. Open the Dashboard

```bash
# Recommended (v2 — AJAX, category filters, toast notifications)
python dashboard_v2.py
# → http://localhost:5051

# Original version (simpler, full-page reloads)
python dashboard.py
# → http://localhost:5050
```

### 3. Manage & Contact Leads

In the dashboard you can:
- Filter leads by **status** (New / Contacted / Rejected) and **category**
- Open the business directly on **Google Maps**
- Send a **WhatsApp message** with a pre-filled Czech outreach text
- Mark leads as **Contacted** or **Rejected** (with undo support in v2)

---

## Database Schema

```sql
CREATE TABLE restaurants (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    address       TEXT,
    phone         TEXT,
    rating        REAL,
    reviews_count INTEGER,
    maps_url      TEXT,
    email         TEXT DEFAULT NULL,
    social_link   TEXT DEFAULT NULL,
    category      TEXT DEFAULT NULL,
    status        TEXT DEFAULT 'new',
    UNIQUE(name, address)
)
```

**Status values:** `new` · `contacted` · `rejected`
**Category values:** `tattoo` · `dentist` · `nail_salon` · `auto_repair` · `yoga` · `barbershop`

---

## Configuration

Runtime settings are defined directly in `hunter.py`:

| Setting | Location | Default |
|---|---|---|
| Search queries | `QUERIES` list (~line 20) | Tattoo, Dentist, Nail, Auto, Yoga in Prague |
| Results limit | `--test` flag | 10 (test) / 100 (prod) |
| Database path | `DB_PATH` constant | `leads_v2.db` |
| Non-website domains | `NON_WEBSITE_DOMAINS` set | Instagram, Facebook, TripAdvisor, etc. |

To target a different city or niche, update the `QUERIES` list:
```python
QUERIES = [
    ("Coffee shop Brno", "coffee"),
    ("Hair salon Brno", "hair_salon"),
]
```

---

## Project Structure

```
map-auto/
├── hunter.py           # Core scraper (Playwright automation)
├── dashboard.py        # Flask dashboard v1 (port 5050)
├── dashboard_v2.py     # Flask dashboard v2 (port 5051, recommended)
├── templates/
│   ├── index.html      # Dashboard v1 UI
│   └── index_v2.html   # Dashboard v2 UI (AJAX, category filters)
├── leads_v2.db         # SQLite database (auto-created on first run)
└── requirements.txt    # Python dependencies
```

---

## Workflow

```
hunter.py            →      leads_v2.db      →      dashboard_v2.py
(scrape Google Maps)    (store & deduplicate)    (review & outreach)
```

1. **Scrape** — Run `hunter.py` to populate the database with fresh leads
2. **Review** — Open the dashboard to browse leads by category and status
3. **Outreach** — Click WhatsApp to send a message, then mark the lead as Contacted

---

## Legal & Ethical Notice

This tool automates browser interactions with Google Maps. Use it responsibly:
- Respect Google's [Terms of Service](https://policies.google.com/terms)
- Do not run at high frequency or volume that could constitute abuse
- Only contact businesses in compliance with applicable privacy and marketing laws (e.g. GDPR)
