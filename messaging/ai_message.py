"""
AI-powered WhatsApp message generator via OpenRouter.
Writes a short, personalized Czech message offering website creation.
"""

import json
import os
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL   = "meta-llama/llama-3.3-70b-instruct"


def generate_whatsapp_message(lead: dict, maps_context: dict | None = None) -> str:
    """
    Generate a personalized WhatsApp message for a given lead.
    Reads OPENROUTER_API_KEY from the environment.

    maps_context (optional): enriched data from scraper.maps_profile.scrape_profile —
        keys: business_type, about, reviews (list[str])
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set.")

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    name     = (lead.get("name") or "").strip() or "your business"
    category = (lead.get("category") or "").replace("_", " ")
    ctx      = maps_context or {}

    # Build a rich context block from whatever we have
    context_lines: list[str] = [f"Business name: {name}"]

    business_type = ctx.get("business_type") or lead.get("description") or category
    if business_type:
        context_lines.append(f"Business type: {business_type}")

    about = ctx.get("about")
    if about:
        context_lines.append(f"About them: {about}")

    reviews = ctx.get("reviews") or []
    if reviews:
        formatted = "\n".join(f'  - "{r}"' for r in reviews[:4])
        context_lines.append(f"What customers say about them:\n{formatted}")

    context_block = "\n".join(context_lines)

    prompt = (
        "You are helping a web developer write a short, personalised WhatsApp cold-outreach "
        "message in Czech to a local business that has no website.\n\n"
        "BUSINESS PROFILE:\n"
        f"{context_block}\n\n"
        "TASK: Write a 3-sentence WhatsApp message offering to build them a professional website.\n\n"
        "Rules:\n"
        "- Sentence 1: reference something specific you noticed about their business "
        "(use their name, what they do, or a detail from reviews / about section)\n"
        "- Sentence 2: offer to create a website tailored specifically to their business\n"
        "- Sentence 3: ask if they'd be open to a short call\n"
        "- Friendly and natural — not a generic template\n"
        "- No emoji, no salesy buzzwords\n"
        "- Czech language only\n"
        "- Return only the message text, nothing else"
    )

    payload = json.dumps({
        "model": model,
        "max_tokens": 220,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        OPENROUTER_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"OpenRouter error {e.code}: {body}") from e

    return result["choices"][0]["message"]["content"].strip()
