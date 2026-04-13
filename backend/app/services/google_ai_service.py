"""
Google AI service — uses Gemini via service account JSON to analyze product images
and generate structured editing prompts.

Setup:
  1. Place service-account.json in backend/ folder
  2. Add to .env:
       GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
       GOOGLE_PROJECT_ID=media-enrichment-472610
"""
import asyncio
import base64
import json
import os

from app.config import get_settings

settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/generative-language"]

SYSTEM_PROMPT = """You are a creative AI assistant helping generate product photography prompts and content for a premium retail brand.

## Your Task

You will be given a product image. Carefully analyse the image and:
1. Identify the product category (e.g. fashion/clothing, beauty/cosmetics, home decor, kitchenware, accessories, footwear, furniture, etc.)
2. Describe the product briefly (material, colour, style, likely use case)
3. Generate 3 distinct image generation prompts for creating a lifestyle/model image of this product, each representing a different visual setting or mood.

## Prompt Format

For each of the 3 prompts, provide:
- Setting name (e.g. "Nordic Winter Morning", "Urban Chic", "Scandinavian Home Sanctuary")
- Full image generation prompt — rich, descriptive, ready to send to an image generation model
- Mood tags — 3-5 short descriptors (e.g. warm, minimal, editorial, cosy, luxurious)

## Visual Style Guidelines (apply to all prompts)

- Clean, Scandinavian aesthetic — minimal clutter, intentional composition
- Natural or warm artificial lighting — never harsh or flat
- Colour palette: muted neutrals, soft whites, warm greys, occasional Nordic accents (deep forest green, slate blue, birch white)
- Premium feel — textures, materials, and surroundings should feel high-quality
- Models (if included) should look naturally confident, not posed — real life moments
- Reflect seasonal Nordic context where appropriate (crisp light, soft shadows, natural materials)

## Output

Return your response as structured JSON in this exact format:
{
  "product_category": "...",
  "product_description": "...",
  "suggested_category": "...",
  "marketing_description": "...",
  "meta_keywords": ["...", "...", "...", "...", "..."],
  "prompts": [
    {
      "setting_name": "...",
      "prompt": "...",
      "mood_tags": ["...", "...", "..."]
    },
    {
      "setting_name": "...",
      "prompt": "...",
      "mood_tags": ["...", "...", "..."]
    },
    {
      "setting_name": "...",
      "prompt": "...",
      "mood_tags": ["...", "...", "..."]
    }
  ]
}

Field guidance:
- suggested_category: A short retail category path like "Women > Clothing > Dresses" or "Home > Kitchen > Cookware".
- marketing_description: 2-3 sentences of premium product copy suitable for an e-commerce listing. Highlight material, style, and key selling points in an aspirational tone.
- meta_keywords: 5-10 relevant SEO keywords as a JSON array (e.g. ["wool coat", "women's outerwear", "Nordic fashion", ...]). Focus on searchable product terms.

Only return valid JSON. No extra text, no markdown code fences."""


def _resolve_sa_file(sa_file: str) -> str:
    """
    Resolve service account file path.  Tries, in order:
      1. As-is (absolute or already correct relative path)
      2. Relative to the backend/ directory (where the app is run from)
      3. Relative to this source file's grandparent (backend/)
    """
    if os.path.isabs(sa_file) and os.path.exists(sa_file):
        return sa_file

    # backend/ = two levels up from app/services/
    src_backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    candidates = [
        sa_file,                                    # CWD-relative
        os.path.join(src_backend, sa_file),         # source-tree backend/
        os.path.join(os.getcwd(), sa_file),         # explicit CWD
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    # Nothing found — return the src_backend path for a clear error message
    return os.path.join(src_backend, sa_file)


def _get_authorized_session():
    """Create authorized HTTP session using service account JSON file."""
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError:
        raise RuntimeError("google-auth not installed. Run: pip install google-auth")

    sa_file = settings.google_service_account_file
    if not sa_file:
        raise RuntimeError(
            "Google AI not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json in .env\n"
            "Place service-account.json in the backend/ folder."
        )

    sa_file = _resolve_sa_file(sa_file)

    if not os.path.exists(sa_file):
        raise RuntimeError(
            f"Service account file not found: {sa_file}\n"
            "Place service-account.json in the backend/ folder."
        )

    creds = service_account.Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    return AuthorizedSession(creds)


def _fetch_and_shrink(image_url: str) -> tuple[str, str]:
    """
    Download image, shrink to max 1024px longest side, return (base64_str, mime_type).
    Shrinking keeps the payload well under Gemini's limits and avoids connection resets.
    """
    import urllib.request
    import io

    req = urllib.request.Request(image_url, headers={"User-Agent": "StockRich/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if max(w, h) > 1024:
            scale = 1024 / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"
    except ImportError:
        # Pillow not installed — send as-is
        return base64.b64encode(raw).decode(), "image/jpeg"


def _call_gemini_sync(image_url: str, product_context: str) -> tuple[dict, float]:
    """Download image, shrink it, send as inlineData to Gemini.
    Returns (result_dict, cost_usd).
    Pricing: Gemini 2.0 Flash — $0.10/1M input tokens, $0.40/1M output tokens.
    """
    session = _get_authorized_session()
    model_id = settings.google_ai_prompt_model
    api_url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent"

    image_b64, mime_type = _fetch_and_shrink(image_url)

    full_prompt = SYSTEM_PROMPT + f"\n\nProduct Information:\n{product_context}"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": full_prompt},
                    {"inlineData": {"mimeType": mime_type, "data": image_b64}},
                    {"text": "Analyse this product image and return JSON only."},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "topP": 0.8,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }

    resp = session.post(api_url, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()

    # Calculate cost from usage metadata
    usage = data.get("usageMetadata", {})
    input_tokens = usage.get("promptTokenCount", 0)
    output_tokens = usage.get("candidatesTokenCount", 0)
    cost_usd = input_tokens * 0.10 / 1_000_000 + output_tokens * 0.40 / 1_000_000

    parts = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    output_text = "".join([p.get("text", "") for p in parts])
    return json.loads(output_text), cost_usd


async def generate_prompt_from_image(
    image_url: str,
    marketing_name: str,
    description: str | None = None,
    material_info: str | None = None,
    keywords: list[str] | None = None,
) -> tuple[dict, float]:
    """
    Async wrapper — runs sync Gemini call in thread pool.
    Returns: (result_dict, cost_usd)
      result_dict: {product_category, product_description, prompts: [{setting_name, prompt, mood_tags}]}
      cost_usd: estimated API cost for this call
    """
    context_parts = [f"Product name: {marketing_name}"]
    if description:
        context_parts.append(f"Description: {description[:500]}")
    if material_info:
        context_parts.append(f"Material: {material_info}")
    if keywords:
        context_parts.append(f"Keywords: {', '.join(keywords[:10])}")
    product_context = "\n".join(context_parts)

    return await asyncio.to_thread(_call_gemini_sync, image_url, product_context)
