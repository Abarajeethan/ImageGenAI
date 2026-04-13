"""
Gemini image generation service — uses service account JSON to call
the Google Generative Language API for image generation.

Called by ai_runner.py when ai_mode=gemini.
Reuses the same auth pattern as google_ai_service.py (prompt generation).

Setup:
  1. Place service-account.json in backend/ folder
  2. In .env set:
       AI_MODE=gemini
       GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
       GOOGLE_AI_IMAGE_MODEL=models/gemini-2.5-flash-image
"""
import base64
import os

from app.config import get_settings

settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/generative-language"]


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
            "Google AI not configured. Set GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json in .env"
        )

    # Resolve relative path from backend directory
    if not os.path.isabs(sa_file):
        backend_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        sa_file = os.path.join(backend_dir, sa_file)

    if not os.path.exists(sa_file):
        raise RuntimeError(f"Service account file not found: {sa_file}")

    creds = service_account.Credentials.from_service_account_file(
        sa_file, scopes=SCOPES
    )
    return AuthorizedSession(creds)


def generate_images_gemini(
    prompt_text: str,
    count: int = 1,
    source_image_bytes: bytes | None = None,
) -> tuple[list[bytes], float]:
    """
    Generate/edit an image using Gemini image generation model via service account.
    If source_image_bytes is provided, the model edits that image (image-to-image).
    Otherwise generates from text prompt only.
    Returns list of image bytes (PNG/JPEG).
    """
    session = _get_authorized_session()

    model_id = settings.google_ai_image_model
    if not model_id.startswith("models/"):
        model_id = f"models/{model_id}"

    api_url = (
        f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent"
    )

    # Build parts: source image first (if provided), then the instruction
    parts = []
    if source_image_bytes:
        # Detect MIME type from magic bytes
        if source_image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            mime_type = "image/png"
        else:
            mime_type = "image/jpeg"
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": base64.b64encode(source_image_bytes).decode(),
            }
        })
        # Strict garment-preservation instruction for fashion model photography
        effective_prompt = (
            "STRICT RULES — read carefully before generating:\n"
            "1. You are creating a professional FASHION MODEL PHOTO for a retail product listing.\n"
            "2. The garment/product shown in the source image is the HERO — it must appear "
            "on a human model and must be reproduced with PERFECT FIDELITY: "
            "identical design, identical colours, identical patterns, identical textures, "
            "identical stitching, identical logos, identical cut — every single detail unchanged.\n"
            "3. Do NOT simplify, stylise, alter, recolour, or reimagine the garment in any way.\n"
            "4. The model should be a professional fashion model in a clean, premium setting "
            "(minimalist studio or aspirational Nordic interior).\n"
            "5. Lighting: natural, soft, high-end editorial quality.\n\n"
            "NOW FOLLOW THESE ADDITIONAL SCENE INSTRUCTIONS:\n"
            + prompt_text
        )
    else:
        effective_prompt = prompt_text

    parts.append({"text": effective_prompt})

    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    images = []
    total_cost_usd = 0.0
    for _ in range(max(1, count)):
        resp = session.post(api_url, json=payload, timeout=120)

        if resp.status_code != 200:
            error_text = resp.text[:600] if resp.text else "(no response body)"
            raise RuntimeError(
                f"Gemini image generation error {resp.status_code}: {error_text}"
            )

        data = resp.json()

        # Cost: Gemini 2.5 Flash image — ~$0.039/image + input token cost
        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        total_cost_usd += 0.039 + input_tokens * 0.15 / 1_000_000

        found = False
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "inlineData" in part:
                    images.append(base64.b64decode(part["inlineData"]["data"]))
                    found = True
        if not found:
            for part in data.get("parts", []):
                if "inlineData" in part:
                    images.append(base64.b64decode(part["inlineData"]["data"]))

    if not images:
        raise RuntimeError(
            "Gemini returned no images. "
            "Use: models/gemini-2.5-flash-image"
        )

    return images, total_cost_usd
