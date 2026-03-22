"""
Scrapes a Google Maps place URL to gather rich context for AI message personalisation.
Extracts: business type subtitle, about text, and visible review snippets.
"""

import asyncio

from playwright.async_api import async_playwright

from scraper.hunter import accept_consent  # reuse existing consent logic

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# Selectors for the business type subtitle shown below the name
_TYPE_SELECTORS = [
    'button[jsaction*="category"]',
    "div.fontBodyMedium span",
    "span.DkEaL",
]

# Selectors for the "About" / description text
_ABOUT_SELECTORS = [
    "div.PYvSYb",           # "About" blurb on main panel
    "div.HlvSq",            # alternate about block
]

# Selector for individual review text spans
_REVIEW_TEXT_SEL  = "span.wiI7pd"
# "See more" buttons inside review cards (expands truncated text)
_REVIEW_MORE_SEL  = "button.w8nwRe"


async def _scrape(url: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="en-US", user_agent=_USER_AGENT)
        page = await ctx.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await accept_consent(page)

        try:
            await page.wait_for_selector("h1.DUwDvf", timeout=10_000)
        except Exception:
            await browser.close()
            return {}

        # ── Business type subtitle ────────────────────────────────────────────
        business_type: str | None = None
        for sel in _TYPE_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.count():
                    text = (await el.inner_text(timeout=2_000)).strip()
                    if text and len(text) < 100:
                        business_type = text
                        break
            except Exception:
                continue

        # ── About / description ───────────────────────────────────────────────
        about: str | None = None
        for sel in _ABOUT_SELECTORS:
            try:
                el = page.locator(sel).first
                if await el.count():
                    text = (await el.inner_text(timeout=2_000)).strip()
                    if text and len(text) > 10:
                        about = text
                        break
            except Exception:
                continue

        # ── Reviews ──────────────────────────────────────────────────────────
        # Scroll down so the review cards render, then expand truncated ones
        await page.evaluate("""
            const el = document.querySelector('div[role="main"]');
            if (el) el.scrollTop = 800;
        """)
        await page.wait_for_timeout(1_500)

        # Expand all "See more" buttons inside review cards
        more_btns = await page.locator(_REVIEW_MORE_SEL).all()
        for btn in more_btns[:6]:
            try:
                await btn.click(timeout=1_000)
            except Exception:
                pass
        await page.wait_for_timeout(600)

        reviews: list[str] = []
        review_els = await page.locator(_REVIEW_TEXT_SEL).all()
        for el in review_els[:5]:
            try:
                text = (await el.inner_text(timeout=1_000)).strip()
                if text and len(text) > 15:
                    reviews.append(text)
            except Exception:
                continue

        await browser.close()

    return {
        "business_type": business_type,
        "about":         about,
        "reviews":       reviews,
    }


def scrape_profile(url: str) -> dict:
    """Synchronous wrapper — returns dict with business_type, about, reviews."""
    if not url or url == "https://maps.google.com":
        return {}
    return asyncio.run(_scrape(url))
