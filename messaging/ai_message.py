"""
AI-powered WhatsApp message generator via OpenRouter.
Writes a short, personalized Czech message offering website creation.
"""

import json
import os
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL   = "anthropic/claude-3.5-haiku"


def _build_reviews_array(lead: dict) -> str:
    """Format DB review data into a string for the prompt."""
    parts: list[str] = []
    if lead.get("rating"):
        line = f"Overall rating: {lead['rating']} ⭐"
        if lead.get("reviews_count"):
            line += f" based on {lead['reviews_count']} Google Maps reviews"
        parts.append(line)
    # Actual review text is not stored in the DB yet — AI will personalize
    # based on rating and category context instead.
    return "; ".join(parts) if parts else "no review data available"


def generate_whatsapp_message(lead: dict) -> str:
    """
    Generate a personalized WhatsApp message for a given lead using only DB data.
    Reads OPENROUTER_API_KEY from the environment.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set.")

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    name     = (lead.get("name") or "").strip() or "your business"
    category = (lead.get("category") or lead.get("description") or "").replace("_", " ")

    prompt = (
        "You are an expert Czech B2B sales representative living in Prague.\n"
        "Your goal is to write a highly personalized, natural WhatsApp message to a local business owner.\n\n"
        "INPUT DATA FROM DATABASE:\n"
        f"- Business Name: {name}\n"
        f"- Niche/Category: {category}\n"
        f"- Last 3 User Reviews: {_build_reviews_array(lead)}\n\n"
        "STRICT INSTRUCTIONS FOR HYPER-PERSONALIZATION:\n"
        "1. FLAWLESS CZECH: Use 100% natural, conversational Czech (vykání). No robotic phrases. No weird characters.\n"
        "2. THE HOOK (CRITICAL): Read the reviews data. You MUST pick ONE specific, unique detail from the reviews "
        "(e.g., a specific compliment, a recurring theme) and mention it in your first sentence. "
        "Do not just say \"you have good reviews\" — prove that you read them!\n"
        "3. UNIQUE OPENINGS: Never start every message with \"Dobrý den, všiml jsem si...\". Mix it up. "
        "Use variations like \"Zdravím do [Business Name],\", \"Dobrý den, koukal jsem na vaše recenze...\", "
        "\"Přeji pěkný den,\".\n"
        "4. THE PAIN POINT: Naturally transition to the fact that they don't have a website. "
        "Frame it as a missed opportunity for their specific niche "
        "(e.g., if it's a salon, say clients can't book online; if a cafe, say they can't see the menu).\n"
        "5. THE OFFER: Mention that your local tech team builds fast, custom solutions to solve this.\n"
        "6. THE CTA: End by asking permission to send a link to your portfolio. "
        "(e.g., \"Můžu poslat odkaz na naše portfolio?\", \"Zajímala by vás ukázka naší práce?\").\n\n"
        "CONSTRAINTS:\n"
        "- Maximum 3-4 short sentences.\n"
        "- DO NOT use placeholders.\n"
        "- Output ONLY the final Czech text, nothing else."
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
