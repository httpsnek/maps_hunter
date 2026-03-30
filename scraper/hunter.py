#!/usr/bin/env python3
"""
Google Maps Lead Generator
Finds Prague businesses without websites and stores them in SQLite.
Supports multi-query scans with per-query category tagging.
"""

import argparse
import asyncio
import random
import sqlite3
from datetime import datetime

from playwright.async_api import async_playwright

DB_PATH = "leads_v2.db"
MAPS_HOME = "https://www.google.com/maps"

# Each entry: (search query, category tag saved to DB)
QUERIES: list[tuple[str, str]] = [
    ("Tattoo studio Praha",      "tattoo"),
    ("Zubní ordinace Praha",     "dentist"),
    ("Manikúra Vinohrady",       "nail_salon"),
    ("Autoservis Praha 4",       "auto_repair"),
    ("Yoga studio Prague",       "yoga"),
    ("Drogerie Praha",       "drogerie"),
]


# ---------------------------------------------------------------------------
# DB Layer
# ---------------------------------------------------------------------------

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id INTEGER PRIMARY KEY,
            name TEXT,
            address TEXT,
            phone TEXT,
            rating REAL,
            reviews_count INTEGER,
            maps_url TEXT,
            email TEXT DEFAULT NULL,
            social_link TEXT DEFAULT NULL,
            category TEXT DEFAULT NULL,
            status TEXT DEFAULT 'new',
            UNIQUE(name, address)
        )
    """)
    conn.commit()

    # Migrate older DBs that are missing newer columns
    existing = {row[1] for row in conn.execute("PRAGMA table_info(restaurants)")}
    migrations = {
        "social_link":  "ALTER TABLE restaurants ADD COLUMN social_link TEXT DEFAULT NULL",
        "category":     "ALTER TABLE restaurants ADD COLUMN category TEXT DEFAULT NULL",
        "description":  "ALTER TABLE restaurants ADD COLUMN description TEXT DEFAULT NULL",
    }
    for col, sql in migrations.items():
        if col not in existing:
            conn.execute(sql)
    conn.commit()

    return conn


def insert_restaurant(conn: sqlite3.Connection, data: dict) -> bool:
    """Returns True if a new row was inserted (not a duplicate)."""
    conn.execute("""
        INSERT OR IGNORE INTO restaurants
            (name, address, phone, rating, reviews_count, maps_url, email, social_link, category, description, status)
        VALUES
            (:name, :address, :phone, :rating, :reviews_count, :maps_url, :email, :social_link, :category, :description, 'new')
    """, data)
    conn.commit()
    changed = conn.execute("SELECT changes()").fetchone()[0]
    return changed > 0


# ---------------------------------------------------------------------------
# Email Layer (placeholder)
# ---------------------------------------------------------------------------

async def find_email(name: str) -> str:
    return ""


# ---------------------------------------------------------------------------
# Browser / Scraping Layer
# ---------------------------------------------------------------------------

async def accept_consent(page) -> bool:
    """
    Click the GDPR consent button if present.
    Returns True if a consent dialog was found and dismissed.
    Tries multiple selector strategies to handle Google's A/B variants.
    """
    strategies = [
        # Attribute-based (most stable across locales)
        'button[aria-label*="Accept"]',
        'button[aria-label*="Agree"]',
        # Text-based English
        'button:has-text("Accept all")',
        'button:has-text("Agree to all")',
        # Czech
        'button:has-text("Přijmout vše")',
        'button:has-text("Souhlasím")',
        # German fallback
        'button:has-text("Alle akzeptieren")',
    ]
    for selector in strategies:
        try:
            btn = page.locator(selector).first
            await btn.wait_for(state="visible", timeout=3000)
            await btn.click()
            print(f"  [consent] clicked via: {selector}")
            # Wait for the overlay to disappear
            await btn.wait_for(state="hidden", timeout=5000)
            await page.wait_for_timeout(1500)  # extra settle time after redirect
            return True
        except Exception:
            continue
    return False  # No consent screen found


async def find_feed(page, query: str = "") -> object | None:
    """
    Try several selectors to find the results sidebar.
    Returns the Locator of the feed element, or None.
    """
    candidates = [
        f'div[aria-label="Results for {query}"]',
        'div[role="feed"]',
        'div[role="main"]',
    ]
    for selector in candidates:
        loc = page.locator(selector).first
        try:
            await loc.wait_for(state="visible", timeout=8000)
            print(f"  [feed] found via: {selector}")
            return loc
        except Exception:
            continue
    return None


async def scroll_results(page, target_count: int = 300, query: str = "") -> list[str]:
    """Scroll the sidebar feed and collect place URLs."""
    feed = await find_feed(page, query)
    if feed is None:
        print("[WARN] Feed not found after trying all selectors.")
        # Dump page title and URL so we can debug
        print(f"  Page URL : {page.url}")
        print(f"  Page title: {await page.title()}")
        return []

    seen: set[str] = set()
    urls: list[str] = []
    stall_count = 0
    prev_count = 0

    while len(urls) < target_count and stall_count < 3:
        # Collect current links
        links = await page.locator('a[href*="/maps/place/"]').all()
        for link in links:
            href = await link.get_attribute("href")
            if href:
                normalised = href.split("?")[0]
                if normalised not in seen:
                    seen.add(normalised)
                    urls.append(normalised)

        if len(urls) <= prev_count:
            stall_count += 1
        else:
            stall_count = 0
            prev_count = len(urls)

        # Check for "end of results" sentinel
        end_text = await page.locator(
            "text=You've reached the end of the list"
        ).count()
        if end_text > 0:
            break

        # Scroll whichever element is the scrollable container
        await page.evaluate("""
            const selectors = [
                'div[role="feed"]',
                'div[role="main"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                    break;
                }
            }
        """)
        await page.wait_for_timeout(random.randint(800, 1200))

    return urls[:target_count]


async def extract_place_data(page, url: str) -> dict | None:
    """
    Navigate to a place URL and extract data.
    Returns None if the place has a website (should be skipped).
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_selector("h1.DUwDvf", timeout=10000)
    except Exception as e:
        print(f"[WARN] Failed to load {url}: {e}")
        return None

    # Domains that are NOT a real business website — keep the restaurant
    NON_WEBSITE_DOMAINS = (
        # Social media
        "instagram.com", "facebook.com", "fb.me", "linktr.ee",
        # Aggregators / review sites
        "menicka.cz", "zomato.com", "tripadvisor.com", "restu.cz", "foursquare.com",
        # Google self-reference
        "google.com",
    )

    # Check whether a website link is present and classify it
    social_link: str | None = None
    try:
        authority = page.locator('a[data-item-id="authority"]').first
        if await authority.count() > 0:
            href = (await authority.get_attribute("href") or "").strip()
            if any(domain in href for domain in NON_WEBSITE_DOMAINS):
                social_link = href
                print(f"  Found non-website link ({href}) — keeping restaurant.")
            else:
                # Has a real website — skip this place
                return None
    except Exception:
        pass

    # Extract name
    name = "N/A"
    try:
        name = await page.locator("h1.DUwDvf").inner_text(timeout=3000)
        name = name.strip()
    except Exception:
        pass

    # Extract address
    address = "N/A"
    try:
        addr_btn = page.locator('button[data-item-id="address"]')
        if await addr_btn.count() > 0:
            address = await addr_btn.get_attribute("aria-label") or "N/A"
            address = address.replace("Address: ", "").replace("Adresa: ", "").strip()
    except Exception:
        pass

    # Extract phone
    phone = "N/A"
    try:
        phone_btn = page.locator('button[data-item-id*="phone:tel:"]')
        if await phone_btn.count() > 0:
            phone = await phone_btn.get_attribute("aria-label") or "N/A"
            phone = phone.replace("Phone: ", "").replace("Telefon: ", "").strip()
    except Exception:
        pass

    # Extract rating
    rating = None
    try:
        rating_el = page.locator("div.F7nice span[aria-hidden='true']").first
        if await rating_el.count() > 0:
            rating_text = await rating_el.inner_text(timeout=2000)
            rating = float(rating_text.replace(",", ".").strip())
    except Exception:
        pass

    # Extract reviews count
    reviews_count = None
    try:
        review_spans = page.locator("div.F7nice span[aria-label]")
        if await review_spans.count() > 0:
            review_label = await review_spans.first.get_attribute("aria-label") or ""
            # "1,234 reviews" → extract digits
            digits = "".join(filter(str.isdigit, review_label.replace(",", "").replace(".", "")))
            if digits:
                reviews_count = int(digits)
    except Exception:
        pass

    # Extract business description / type subtitle shown below the name
    # Google Maps renders this as a clickable category button or a plain span.
    # We try several selectors and take the first non-empty result.
    description: str | None = None
    _desc_selectors = [
        'button[jsaction*="category"]',   # clickable category label
        "div.fontBodyMedium span",        # subtitle span below h1
        "span.DkEaL",                     # alternate class used in some variants
    ]
    for sel in _desc_selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                text = (await el.inner_text(timeout=2000)).strip()
                if text and len(text) < 120:  # sanity-check: skip huge blobs
                    description = text
                    break
        except Exception:
            continue

    return {
        "name": name,
        "address": address,
        "phone": phone,
        "rating": rating,
        "reviews_count": reviews_count,
        "maps_url": url,
        "email": "",
        "social_link": social_link,
        "category": None,       # filled in by the caller
        "description": description,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_table(rows: list[dict]) -> None:
    if not rows:
        print("No results found.")
        return

    col_widths = {
        "name": 30,
        "address": 35,
        "phone": 18,
        "rating": 6,
        "reviews_count": 8,
    }
    headers = ["name", "address", "phone", "rating", "reviews_count"]

    def fmt(val, width):
        s = str(val) if val is not None else "N/A"
        return s[:width].ljust(width)

    sep = "+" + "+".join("-" * (w + 2) for w in col_widths.values()) + "+"
    header_row = "|" + "|".join(f" {h.upper()[:col_widths[h]].ljust(col_widths[h])} " for h in headers) + "|"

    print(sep)
    print(header_row)
    print(sep)
    for row in rows:
        line = "|" + "|".join(f" {fmt(row.get(h), col_widths[h])} " for h in headers) + "|"
        print(line)
    print(sep)
    print(f"\nTotal: {len(rows)} restaurants without websites")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_query(page, conn, query: str, category: str, limit: int) -> list[dict]:
    """Search one query, scrape up to `limit` new leads, return saved rows."""
    results: list[dict] = []

    print(f"\n{'='*60}")
    print(f"[{datetime.now():%H:%M:%S}] Query: '{query}'  (category: {category})")
    print(f"{'='*60}")

    # Navigate to Maps home and search
    await page.goto(MAPS_HOME, wait_until="domcontentloaded", timeout=30000)
    await accept_consent(page)  # no-op after first dismissal

    search_box_found = False
    try:
        await page.wait_for_selector("input#searchboxinput", timeout=8000)
        search_box_found = True
    except Exception:
        print("  [search] search box not found, falling back to direct URL…")

    if search_box_found:
        await page.fill("input#searchboxinput", query)
        await page.press("input#searchboxinput", "Enter")
    else:
        import urllib.parse
        await page.goto(
            f"https://www.google.com/maps/search/{urllib.parse.quote(query)}/",
            wait_until="domcontentloaded",
            timeout=30000,
        )

    await page.wait_for_timeout(2500)

    print(f"[{datetime.now():%H:%M:%S}] Scrolling (target: 200 URLs)…")
    urls = await scroll_results(page, target_count=200, query=query)
    print(f"[{datetime.now():%H:%M:%S}] Collected {len(urls)} place URLs.")

    for i, url in enumerate(urls):
        if len(results) >= limit:
            break

        print(f"[{datetime.now():%H:%M:%S}] [{i+1}/{len(urls)}] {url[:70]}…")
        data = await extract_place_data(page, url)

        if data is None:
            print("  → skipped (has website or load failed)")
        else:
            data["category"] = category
            is_new = insert_restaurant(conn, data)
            if is_new:
                results.append(data)
                print(f"  → saved: {data['name']} | {data['phone']}")
            else:
                print(f"  → duplicate: {data['name']}")

        await page.wait_for_timeout(random.randint(800, 1400))

    print(f"[{datetime.now():%H:%M:%S}] Query done — {len(results)} new leads saved.")
    return results


async def main(limit: int, headless: bool = True) -> None:
    conn = init_db()
    all_results: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        # Dismiss GDPR consent once on the home page before the query loop
        print(f"[{datetime.now():%H:%M:%S}] Opening Google Maps for consent check…")
        await page.goto(MAPS_HOME, wait_until="domcontentloaded", timeout=30000)
        dismissed = await accept_consent(page)
        if dismissed:
            print("  [consent] dismissed.")
            await page.wait_for_timeout(1500)

        for query, category in QUERIES:
            rows = await run_query(page, conn, query, category, limit)
            all_results.extend(rows)

        await browser.close()

    conn.close()
    print(f"\n{'='*60}")
    print(f"Total new leads across all queries: {len(all_results)}")
    print(f"{'='*60}\n")
    print_table(all_results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Maps lead generator — multi-query barbershop scan")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: stop each query after 10 results and print a table",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True for speed)",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        help="Show the browser window (useful for debugging)",
    )
    args = parser.parse_args()

    limit = 10 if args.test else 100
    asyncio.run(main(limit, headless=args.headless))
