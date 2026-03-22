"""
WhatsApp Web automation via Playwright.
Sends a message to a phone number using a persistent browser session.

First run: a browser window opens showing the WhatsApp Web QR code.
Scan it with your phone once — the session is saved to ./whatsapp_session/
and all subsequent sends happen silently in a background window.
"""

import asyncio
import re
import urllib.parse
from pathlib import Path

from playwright.async_api import async_playwright

# Session stored at project root, not inside the messaging/ package
SESSION_DIR = str(Path(__file__).parent.parent / "whatsapp_session")


def _normalize_phone(phone: str) -> str:
    """Strip formatting; add Czech +420 prefix if no country code present."""
    clean = re.sub(r"[\s\-().]+", "", phone)
    if not clean.startswith("+"):
        clean = clean.lstrip("0")
        clean = "+420" + clean
    return clean


async def _send(phone: str, message: str) -> None:
    clean_phone = _normalize_phone(phone)
    url = (
        "https://web.whatsapp.com/send"
        f"?phone={clean_phone}"
        f"&text={urllib.parse.quote(message)}"
    )

    async with async_playwright() as p:
        # Persistent context keeps the WhatsApp Web session across runs
        ctx = await p.chromium.launch_persistent_context(
            SESSION_DIR,
            headless=False,          # required for WhatsApp Web to work
            args=["--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.bring_to_front()
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

        # Wait up to 90 s — covers first-time QR scan and slow connections
        send_btn = page.locator('button[aria-label="Send"]')
        await send_btn.wait_for(state="visible", timeout=90_000)
        await send_btn.click()

        # Give WhatsApp a moment to register the send before closing
        await page.wait_for_timeout(2_500)
        await ctx.close()


def send_message(phone: str, message: str) -> None:
    """Synchronous wrapper — safe to call from a Flask route."""
    asyncio.run(_send(phone, message))
