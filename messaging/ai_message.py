"""
AI-powered WhatsApp message generator via OpenRouter.
Writes a short, personalized Czech message offering website creation.
"""

import json
import os
import re
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL  = "anthropic/claude-3.5-haiku"

# Generic business-type words that pollute SEO-stuffed names.
# Anything after these (or the separator before them) gets stripped.
_SEO_NOISE: set[str] = {
    # Business type words
    "tattoo", "tetování", "tetovani", "piercing", "barber", "barbershop",
    "hair", "salon", "salón", "studio", "studia", "shop", "store",
    "nail", "beauty", "spa", "wellness", "fitness", "gym", "cafe",
    "restaurant", "restaurace", "bar", "bistro", "dental", "dent",
    "auto", "servis", "service", "drogerie", "yoga", "pilates",
    # Czech city / district names commonly stuffed into business names
    "praha", "prague", "brno", "ostrava", "plzen", "plzeň",
    "vinohrady", "žižkov", "zizkov", "smíchov", "smichov",
    "holešovice", "holesovice", "dejvice", "nusle", "nusli",
}

# Separators used to jam extra keywords into a business name
_SEP_RE = re.compile(r"\s*[&|/,]\s*|\s+-\s+")


def _shorten_name(raw: str) -> str:
    """
    Return only the core brand name, stripping SEO-spam words anywhere in the name.

    'Hell Tattoo & Piercing Praha'       → 'Hell'
    'Nayana Tattoo'                      → 'Nayana'
    'TATTOO studio Nikolay Lukashenko'   → 'Nikolay Lukashenko'
    'Tattoo Studio Elite Ink'            → 'Elite Ink'
    'Barbershop Karel'                   → 'Karel'
    'Studio Nikolay Lukashenko'          → 'Nikolay Lukashenko'
    """
    if not raw:
        return raw

    # Split on explicit separators first — each chunk may be a pure keyword block
    segments = _SEP_RE.split(raw.strip())

    # Find the first segment whose first word is NOT a noise word
    brand: str | None = None
    for seg in segments:
        words = seg.split()
        first = words[0].lower().rstrip("s") if words else ""
        if first not in _SEO_NOISE:
            brand = seg.strip()
            break

    if brand is None:
        # Every segment starts with noise (e.g. "TATTOO studio Nikolay Lukashenko").
        # Skip ALL leading noise words across the full raw string and take the rest.
        all_words = raw.split()
        remaining: list[str] = []
        skipping = True
        for w in all_words:
            if skipping and w.lower().rstrip("s") in _SEO_NOISE:
                continue
            skipping = False
            remaining.append(w)
        brand = " ".join(remaining) if remaining else raw.strip()

    # Drop trailing noise words within the winning segment
    # e.g. "Nayana Tattoo" → "Nayana", "Elite Ink Tattoo" → "Elite Ink"
    words = brand.split()
    trimmed: list[str] = []
    for w in words:
        if w.lower().rstrip("s") in _SEO_NOISE:
            break
        trimmed.append(w)

    return " ".join(trimmed) if trimmed else brand


# ── Qualitative reputation signals (no raw numbers leak to the LLM) ──────────

def _reputation_signal(rating: float | None, reviews: int | None) -> str:
    """
    Convert numeric rating + review count into a natural Czech qualitative phrase.
    The LLM never sees the actual numbers.
    """
    if rating is None:
        return "vaše studio má na Googlu hezké hodnocení"

    if rating >= 4.8:
        if reviews and reviews >= 100:
            return "lidi vaši práci v recenzích neskutečně chválí — máte jedno z nejlepších hodnocení ve svém okolí"
        return "lidi vaši práci v recenzích neskutečně chválí"
    if rating >= 4.5:
        return "na Googlu máte skvělé hodnocení a spousta lidí vaši práci doporučuje"
    if rating >= 4.0:
        return "na Googlu vás zákazníci hodnotí velmi dobře"
    return "na Googlu máte solidní hodnocení"


# ── Category pain points — English conceptual descriptions only.
# These are NEVER shown verbatim in output; the LLM must express them freely in Czech.
_PAIN_POINTS: dict[str, str] = {
    "tattoo":      (
        "Without a website, potential clients cannot browse the artist's portfolio, "
        "so the studio gets constant phone interruptions during active tattoo sessions."
    ),
    "barbershop":  (
        "Without a website, clients cannot view haircut photos or book online, "
        "so the barber gets phone calls that interrupt active cuts."
    ),
    "salon":       (
        "Without a website, clients cannot see examples of the work or book an appointment "
        "online, forcing them to call and interrupt the stylist mid-session."
    ),
    "nail_salon":  (
        "Without a website, clients cannot check the service menu or prices "
        "and must call to book, which interrupts the nail technician's work."
    ),
    "dentist":     (
        "Without a website, new patients cannot find out which treatments are offered "
        "or book an appointment online — they simply go to a competitor who has one."
    ),
    "auto_repair": (
        "Without a website, customers cannot check available services or request a quote "
        "online and must call the workshop directly, disrupting the mechanics."
    ),
    "restaurant":  (
        "Without a website, guests cannot browse the menu or check opening hours "
        "before deciding whether to visit."
    ),
    "cafe":        (
        "Without a website, guests have no way to check the menu or daily specials "
        "before showing up."
    ),
    "drogerie":    (
        "Without a website, customers cannot browse the product range or confirm "
        "opening hours before making a trip."
    ),
}

_DEFAULT_PAIN_POINT = (
    "Without a website, potential customers cannot find basic information about the business "
    "online and may simply choose a competitor who has one."
)


def _pain_point_for(category: str) -> str:
    slug = category.lower().replace(" ", "_")
    for key, text in _PAIN_POINTS.items():
        if key in slug:
            return text
    return _DEFAULT_PAIN_POINT


# ── LLM call helper ───────────────────────────────────────────────────────────

def _call_llm(system: str, user: str, max_tokens: int = 280) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set.")

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    payload = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0.8,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
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


# ── Public API ────────────────────────────────────────────────────────────────

def generate_whatsapp_message(lead: dict) -> str:
    """
    Generate a personalized cold WhatsApp message for a lead.

    Pre-processing:
    - Business name is stripped of SEO noise before hitting the LLM.
    - Rating/review count are converted to qualitative phrases — exact
      numbers never appear in the output.
    """
    raw_name    = (lead.get("name") or "").strip()
    short_name  = _shorten_name(raw_name) or raw_name or "vaše studio"
    category    = (lead.get("category") or lead.get("description") or "").replace("_", " ")

    try:
        rating_val = float(lead["rating"]) if lead.get("rating") else None
    except (ValueError, TypeError):
        rating_val = None

    try:
        reviews_val = int(lead["reviews_count"]) if lead.get("reviews_count") else None
    except (ValueError, TypeError):
        reviews_val = None

    reputation = _reputation_signal(rating_val, reviews_val)
    pain_point = _pain_point_for(category)

    greeting = f"Zdravím do {short_name},"

    system = """\
Jsi zkušený český B2B copywriter z Prahy. Píšeš krátkou, přirozenou zprávu na WhatsApp \
majiteli lokální firmy — nabízíš mu vytvoření webových stránek.

STRUKTURA (jeden plynulý text, BEZ nadpisů nebo číslování):
1. POZDRAV: Použij PŘESNĚ pozdrav uvedený v uživatelské zprávě pod klíčem "Pozdrav". \
   Nič ho, nezkracuj, nenahrazuj. Je to první slovo zprávy.
2. POCHVALA: Přirozeně pochval jejich reputaci na Googlu — použij dodanou kvalitativní frázi. \
   NIKDY nevypisuj přesné číslo hodnocení (např. "4.8") ani přesný počet recenzí (např. "50 recenzí"). \
   Znění musí být konverzační, ne jako výpis ze statistiky.
3. PROBLÉM: Express the conceptual pain point provided in the user message entirely in your \
   OWN words in natural Czech. You MUST generate completely unique wording every single time — \
   never reuse the same sentence structure twice. Do NOT copy or translate the English \
   description literally. Invent a fresh, conversational Czech formulation each time. \
   Do NOT use any fixed opener templates. Forbidden phrases (never use): \
   "Přitom mi ale přijde škoda", "Zarazila mě ale jedna věc", \
   "a to znamená, že zájemci nemají kde prohlédnout vaše portfolio".
4. NABÍDKA: Jednou větou zmiň, že váš pražský tým dělá rychlé, přehledné weby na míru.
5. CTA: Ukonči krátkou otázkou o svolení poslat odkaz na portfolio. \
   Např. "Můžu vám poslat odkaz na naše portfolio?" nebo "Zajímala by vás ukázka naší práce?"

PŘÍSNÁ PRAVIDLA:
- Zpráva MUSÍ začínat přesně pozdravem z pole "Pozdrav" — žádná jiná varianta.
- Maximálně 4 krátké věty celkem.
- 100 % přirozená čeština (vykání). Žádné robotické fráze.
- ŽÁDNÉ placeholdery, závorky ani anglická slova.
- Výstup = POUZE finální text zprávy, nic jiného.\
"""

    user = (
        f"Pozdrav (použij doslova jako první slova zprávy): {greeting}\n"
        f"Kategorie: {category}\n"
        f"Kvalitativní hodnocení (použij tuto frázi, NEZMĚŇUJ čísla — žádná čísla nejsou): {reputation}\n"
        f"Konkrétní problém pro jejich obor: {pain_point}\n"
    )

    return _call_llm(system, user, max_tokens=280)
