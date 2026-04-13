"""
Inline AI runner — runs the full AI generation pipeline as a FastAPI background task.
Uses its own DB session per operation to avoid request-session lifetime issues.
"""
import uuid
import json
import asyncio
from datetime import datetime, timezone

import structlog

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Product, ProductStatus

settings = get_settings()
log = structlog.get_logger()

# ── Canvas spec (photoshoot output template) ──────────────────────────────
_CANVAS_W, _CANVAS_H = 2360, 3152   # full image dimensions
_SAFE_W,   _SAFE_H   = 1870, 2662   # safe/printable zone
_TARGET_DPI = (72, 72)


async def run_ai_generation_inline(sku_id: str, prompt_text: str, session_id: str, product_name: str = ""):
    """
    Called as an asyncio background task from the /regenerate endpoint.
    Generates images and saves keys to product row — same outcome as the worker.
    Uses its own DB session to avoid using the closed request session.
    """
    log.info("Inline AI generation starting", sku_id=sku_id, session_id=session_id)

    try:
        # Small delay so UI can show the "generating" state before polling resolves
        await asyncio.sleep(0.5)

        # ── Fetch original source image for image-to-image generation ─────────
        # Run in executor so the event loop stays free for polling requests
        source_image_bytes = None
        async with AsyncSessionLocal() as src_db:
            from sqlalchemy import select as sa_select
            src_result = await src_db.execute(sa_select(Product).where(Product.sku_id == sku_id))
            src_product = src_result.scalar_one_or_none()
            if src_product and src_product.original_image_keys:
                orig_key = src_product.original_image_keys[0]
                source_image_bytes = await asyncio.get_event_loop().run_in_executor(
                    None, _fetch_image_bytes, orig_key
                )

        # ── Generate images (blocking HTTP — run in thread so loop stays free) ─
        image_bytes_list, generation_cost = await asyncio.get_event_loop().run_in_executor(
            None, _generate_images, sku_id, product_name, prompt_text, source_image_bytes
        )

        # ── Format to canvas spec ─────────────────────────────────────────────
        image_bytes_list = [_format_image(b) for b in image_bytes_list]

        # ── Save to storage ───────────────────────────────────────────────────
        upload_fn = _get_upload_fn()
        uploaded_keys = []
        for i, img_bytes in enumerate(image_bytes_list):
            key = upload_fn(img_bytes, sku_id, session_id, i)
            uploaded_keys.append({"key": key, "sort": i})

        # ── Update product in DB ──────────────────────────────────────────────
        # Re-fetch to avoid stale session issues
        async with AsyncSessionLocal() as fresh_db:
            from sqlalchemy import select
            from sqlalchemy.orm.attributes import flag_modified
            result = await fresh_db.execute(select(Product).where(Product.sku_id == sku_id))
            p = result.scalar_one_or_none()
            if p:
                new_keys = [item["key"] for item in uploaded_keys]

                existing = p.image_metadata or {}
                # Build a new dict so SQLAlchemy always detects the change
                new_meta = {
                    "original": existing.get("original", []),
                    "ai": [
                        {
                            "key": item["key"],
                            "status": "PENDING",
                            "sort": item["sort"],
                            "session_id": session_id,
                            "recall_reason": None,
                        }
                        for item in uploaded_keys
                    ],
                }

                p.ai_image_keys = new_keys
                p.image_metadata = new_meta
                flag_modified(p, "image_metadata")
                p.status = ProductStatus.AI_READY
                p.google_api_calls = (p.google_api_calls or 0) + 1
                p.google_api_cost_usd = float(p.google_api_cost_usd or 0) + generation_cost

                from app.models import AuditLog, AuditAction
                fresh_db.add(AuditLog(
                    action=AuditAction.AI_GENERATED,
                    sku_id=sku_id,
                    payload={"session_id": session_id, "image_count": len(uploaded_keys)},
                ))
                await fresh_db.commit()

        log.info("Inline AI generation complete", sku_id=sku_id, images=len(uploaded_keys))

    except Exception as e:
        log.error("Inline AI generation failed", sku_id=sku_id, error=str(e))
        async with AsyncSessionLocal() as fresh_db:
            from sqlalchemy import select
            from sqlalchemy.orm.attributes import flag_modified
            result = await fresh_db.execute(select(Product).where(Product.sku_id == sku_id))
            p = result.scalar_one_or_none()
            if p:
                p.status = ProductStatus.AI_FAILED
                # Store error in metadata so frontend can display it
                meta = dict(p.image_metadata or {})
                meta["error"] = str(e)
                meta["error_at"] = datetime.now(timezone.utc).isoformat()
                p.image_metadata = meta
                flag_modified(p, "image_metadata")
                await fresh_db.commit()


def _generate_images(sku_id: str, name: str, prompt_text: str, source_image_bytes: bytes | None = None) -> tuple[list[bytes], float]:
    if settings.ai_mode == "mock":
        from app.services.ai_mock import generate_mock_images
        return generate_mock_images(sku_id, name, 1), 0.0
    else:
        from app.services.gemini_service import generate_images_gemini
        return generate_images_gemini(prompt_text, count=1, source_image_bytes=source_image_bytes)


def _fetch_image_bytes(key: str) -> bytes | None:
    """Fetch image bytes from a CDN URL or local file path."""
    try:
        if key.startswith("https://") or key.startswith("http://"):
            import urllib.request
            req = urllib.request.Request(key, headers={"User-Agent": "StockRich/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()
        else:
            from pathlib import Path
            filepath = Path(settings.local_image_dir) / key
            if filepath.exists():
                return filepath.read_bytes()
    except Exception as e:
        log.warning("Could not fetch source image for generation", key=key, error=str(e))
    return None


def _get_upload_fn():
    from app.services.storage_local import upload_ai_image
    return upload_ai_image


def _format_image(img_bytes: bytes) -> bytes:
    """
    Format AI-generated image to canvas spec:
      • 2360 × 3152 px canvas, white background
      • Safe zone 1870 × 2662 px centered on the canvas
      • Input image scaled to fill the safe zone (aspect-ratio preserved)
        and centered inside it
      • Output: JPEG, 72 DPI, quality 96

    Falls back to the original bytes if Pillow is not installed.
    """
    try:
        import io
        from PIL import Image
    except ImportError:
        log.warning("Pillow not installed — skipping canvas formatting. Run: pip install Pillow")
        return img_bytes

    try:
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        orig_w, orig_h = img.size

        # Scale to fit inside the safe zone
        scale = min(_SAFE_W / orig_w, _SAFE_H / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        img   = img.resize((new_w, new_h), Image.LANCZOS)

        # White canvas
        canvas   = Image.new("RGB", (_CANVAS_W, _CANVAS_H), (255, 255, 255))
        offset_x = (_CANVAS_W - _SAFE_W) // 2   # 245 px on each side
        offset_y = (_CANVAS_H - _SAFE_H) // 2   # 245 px top & bottom
        paste_x  = offset_x + (_SAFE_W - new_w) // 2
        paste_y  = offset_y + (_SAFE_H - new_h) // 2
        canvas.paste(img, (paste_x, paste_y))

        buf = io.BytesIO()
        canvas.save(
            buf, format="JPEG",
            dpi=_TARGET_DPI,
            quality=96,
            optimize=True,
            progressive=True,
        )
        buf.seek(0)
        formatted = buf.read()
        log.info("Image formatted to canvas spec", orig=f"{orig_w}x{orig_h}", final=f"{_CANVAS_W}x{_CANVAS_H}")
        return formatted

    except Exception as e:
        log.warning("Canvas formatting failed — using original bytes", error=str(e))
        return img_bytes
