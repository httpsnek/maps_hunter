# Maps Hunter

A Google Maps lead-generation tool for finding Prague businesses that **don't have a real website**. It scrapes Google Maps with Playwright, stores leads in SQLite, and serves a Flask dashboard for reviewing them, generating personalized cold messages with an LLM, and sending those messages over WhatsApp.

The end-to-end flow: **scrape → review in dashboard → generate AI message → send via WhatsApp.**

## Project structure

```
map-auto/
├── scraper/
│   ├── hunter.py          # Main scraper: multi-query Maps scan → leads_v2.db
│   └── maps_profile.py    # Rich per-place scrape (type, about, reviews) for personalization
├── messaging/
│   ├── ai_message.py      # LLM-generated Czech WhatsApp message via OpenRouter
│   └── whatsapp.py        # WhatsApp Web automation (Playwright persistent session)
├── templates/
│   ├── index.html         # Legacy dashboard template
│   └── index_v2.html      # v2 dashboard template
├── dashboard.py           # Legacy dashboard (port 5050)
├── dashboard_v2.py        # Main dashboard with AI + WhatsApp (port 5051)
├── test_batch.py          # Manual test: POST a batch of leads to a Make.com webhook
├── test_webhook.py        # Manual test: POST a single lead to a Make.com webhook
├── requirements.txt
├── .env.example
└── leads_v2.db            # SQLite database (gitignored, created on first run)
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install the Playwright Chromium browser (required for scraping)
playwright install chromium

# Configure secrets
cp .env.example .env        # then edit .env and add your OpenRouter API key
source .env                 # export the variables into your shell
```

`requirements.txt` covers `playwright`, `beautifulsoup4`, and `flask`. The two `test_*.py` helper scripts additionally need `requests` (`pip install requests`).

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes (for AI messages) | Auth for OpenRouter LLM calls. Get one at https://openrouter.ai/keys |
| `OPENROUTER_MODEL` | No | Override the default model (`anthropic/claude-3.5-haiku`) |

## Usage

Run everything from the project root so the `scraper.*` and `messaging.*` package imports resolve.

### 1. Scrape leads

```bash
# Full run — up to 100 saved leads per query
python -m scraper.hunter

# Test mode — 10 leads per query (faster feedback)
python -m scraper.hunter --test

# Show the browser window for debugging
python -m scraper.hunter --no-headless

# Combined
python -m scraper.hunter --test --no-headless
```

Each query scrolls the Maps sidebar to collect up to 200 place URLs, then visits each place and keeps only businesses with **no website or only a social/aggregator link**. New leads are written to `leads_v2.db`.

### 2. Review leads in the dashboard

```bash
# Main dashboard — AJAX updates, AI messaging, WhatsApp sending
python dashboard_v2.py        # http://localhost:5051

# Legacy dashboard — simple status review only
python dashboard.py           # http://localhost:5050
```

The v2 dashboard lets you filter by status and category, mark leads as `new` / `contacted` / `rejected` without a page reload, generate a personalized message per lead, and trigger a WhatsApp send.

### 3. Send WhatsApp messages

The first time a message is sent, a browser window opens with the WhatsApp Web QR code. Scan it once with your phone — the session is saved to `whatsapp_session/` and subsequent sends reuse it.

## How it works

### Scraping (`scraper/hunter.py`)

- **Queries** are defined in the `QUERIES` list at the top of the file — each is a `(search term, category tag)` pair (tattoo, dentist, nail salon, auto repair, yoga, drogerie).
- **Consent handling** dismisses Google's GDPR dialog once up front, trying English, Czech, and German selector variants.
- **Website detection** keeps a business only if its website link is missing or points to a whitelisted non-website domain (instagram.com, facebook.com, menicka.cz, zomato.com, etc.). Any real website causes the place to be skipped.
- **Data captured** per lead: name, address, phone, rating, review count, Maps URL, social link, category, and a short business-type description.

### Profile enrichment (`scraper/maps_profile.py`)

`scrape_profile(url)` opens a single place page and pulls richer context — business-type subtitle, the "About" blurb, and a few review snippets — for use in message personalization.

### AI message generation (`messaging/ai_message.py`)

`generate_whatsapp_message(lead)` builds a short, natural Czech cold message offering website creation. Before the LLM is called it:

- strips SEO-spam words (business-type and district keywords) out of the business name so only the core brand remains;
- converts the numeric rating and review count into a qualitative Czech phrase so **exact numbers never reach the model**;
- selects a category-specific "pain point" the model rephrases freshly each time.

It calls OpenRouter's chat-completions API directly over `urllib` (no SDK dependency).

### WhatsApp automation (`messaging/whatsapp.py`)

`send_message(phone, message)` normalizes the number (adds the Czech `+420` prefix when no country code is present), opens WhatsApp Web with the message pre-filled via a persistent Playwright context, and clicks send.

## Database schema

SQLite database `leads_v2.db`, table `restaurants`:

| Column | Notes |
|--------|-------|
| `id` | Primary key |
| `name`, `address`, `phone` | Business contact details |
| `rating`, `reviews_count` | Google rating and review count |
| `maps_url` | Link to the Maps place |
| `email` | Placeholder, currently unused |
| `social_link` | Instagram/Facebook link found instead of a website |
| `description` | Business-type subtitle scraped from the place page |
| `category` | Query category tag (e.g. `tattoo`, `dentist`) |
| `status` | `new` / `contacted` / `rejected`, managed from the dashboard |

The scraper auto-migrates older databases, adding the `social_link`, `category`, and `description` columns if they're missing.

## Dashboard API (v2)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Lead list, filterable by `status` and `category` |
| `/api/status/<id>` | POST | Update a lead's status (JSON or form) |
| `/api/ai-message/<id>` | POST | Generate a personalized message for the lead |
| `/api/send-whatsapp/<id>` | POST | Send a message to the lead over WhatsApp Web |

## Webhook test scripts

`test_batch.py` and `test_webhook.py` are throwaway scripts that POST sample lead data to a Make.com webhook — useful for wiring up an external automation. They are not part of the core scrape/dashboard flow and require the `requests` package.

## Notes

- Python 3.11+ (modern type hints like `list[str]` and `dict | None` are used).
- The database path is hardcoded as `leads_v2.db` and is resolved relative to the working directory, so run all commands from the project root.
- `leads_v2.db`, `.env`, and `whatsapp_session/` are gitignored.

> **Security:** the `git remote` URL in this repo currently embeds a GitHub personal-access token. Rotate that token and reset the remote to a plain `https://github.com/...` URL so the credential isn't stored in `.git/config`.
