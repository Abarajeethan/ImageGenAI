import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database import get_db
from app.models import Product, ProductPrompt, PromptLibrary, PromptType, User, ProductStatus, AuditAction
from app.schemas import ProductPromptRead, ProductPromptUpdate, PromptLibraryRead, PromptLibraryCreate, PromptLibraryUpdate
from app.middleware.auth import get_current_user, require_editor, require_admin
from app.services.prompt_service import update_product_prompt, get_or_create_product_prompt
from app.config import get_settings
_settings = get_settings()
from app.services.audit_service import log_action
import uuid as uuid_mod
import asyncio
import base64 as b64mod

router = APIRouter(tags=["prompts"])


# ─── Product-level prompt ─────────────────────────────────

@router.get("/products/{sku_id}/prompt", response_model=ProductPromptRead)
async def get_product_prompt(
    sku_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    prompt = await get_or_create_product_prompt(db, product, current_user.id)
    return prompt


@router.patch("/products/{sku_id}/prompt", response_model=ProductPromptRead)
async def edit_product_prompt(
    sku_id: str,
    body: ProductPromptUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    prompt = await update_product_prompt(db, sku_id, body.prompt_text, current_user.id)

    await log_action(
        db, AuditAction.PROMPT_EDITED,
        user_id=current_user.id, sku_id=sku_id,
        payload={"new_prompt_preview": body.prompt_text[:200]},
        ip_address=request.client.host if request.client else None,
    )
    return prompt


@router.get("/products/{sku_id}/prompt/history", response_model=list[ProductPromptRead])
async def get_prompt_history(
    sku_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(ProductPrompt)
        .options(selectinload(ProductPrompt.created_by))
        .where(ProductPrompt.sku_id == sku_id)
        .order_by(ProductPrompt.created_at.desc())
    )
    return result.scalars().all()


@router.post("/products/{sku_id}/regenerate", response_model=dict)
async def regenerate_ai_images(
    sku_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Enqueue AI regeneration for this product (uses current prompt)."""
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    # Get current prompt — if not user-overridden, rebuild from active PromptLibrary
    # so edits to the general/brand prompt take effect immediately
    prompt_result = await db.execute(
        select(ProductPrompt).where(
            and_(ProductPrompt.sku_id == sku_id, ProductPrompt.is_current == True)
        )
    )
    prompt = prompt_result.scalar_one_or_none()

    if prompt and prompt.is_override:
        # User manually wrote this prompt — respect it as-is
        prompt_text = prompt.prompt_text
    else:
        # Rebuild from active PromptLibrary (general + brand + product context)
        from app.services.prompt_service import build_product_prompt
        prompt_text, general_id, brand_id = await build_product_prompt(db, product)
        # Update the stored ProductPrompt so it reflects the new library version
        if prompt:
            prompt.is_current = False
        new_prompt = ProductPrompt(
            sku_id=sku_id,
            prompt_text=prompt_text,
            general_prompt_id=general_id,
            brand_prompt_id=brand_id,
            is_override=False,
            is_current=True,
            created_by_user_id=current_user.id,
        )
        db.add(new_prompt)
        await db.flush()
        prompt = new_prompt

    if not prompt_text.strip():
        raise HTTPException(400, "No prompt could be built. Add a General prompt in the Prompt Library first.")

    session_id = str(uuid_mod.uuid4())
    import asyncio
    from app.services.ai_runner import run_ai_generation_inline
    asyncio.create_task(run_ai_generation_inline(sku_id, prompt_text, session_id, product.marketing_name or ""))

    product.status = ProductStatus.AI_GENERATING

    await log_action(
        db, AuditAction.AI_REGENERATED,
        user_id=current_user.id, sku_id=sku_id,
        payload={"session_id": session_id, "prompt_id": str(prompt.id)},
        ip_address=request.client.host if request.client else None,
    )

    return {
        "message": "AI regeneration started",
        "session_id": session_id,
    }


# ─── Prompt Library (admin) ───────────────────────────────



@router.get("/prompt-library/system-prompt", response_model=dict)
async def get_system_prompt(
    current_user: User = Depends(get_current_user),
):
    """Return the current system prompt used for Gemini AI analysis."""
    from app.services.google_ai_service import SYSTEM_PROMPT
    return {"prompt_text": SYSTEM_PROMPT.strip()}

@router.get("/prompt-library", response_model=list[PromptLibraryRead])
async def list_prompt_library(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PromptLibrary)
        .where(PromptLibrary.is_active == True)
        .order_by(PromptLibrary.prompt_type, PromptLibrary.created_at)
    )
    return result.scalars().all()


@router.post("/prompt-library", response_model=PromptLibraryRead)
async def create_prompt(
    body: PromptLibraryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Deactivate existing active prompt of same type/brand/department
    existing_result = await db.execute(
        select(PromptLibrary).where(
            and_(
                PromptLibrary.prompt_type == body.prompt_type,
                PromptLibrary.brand_id == body.brand_id,
                PromptLibrary.department == body.department,
                PromptLibrary.is_active == True,
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    next_version = 1
    if existing:
        next_version = existing.version + 1
        existing.is_active = False

    new_prompt = PromptLibrary(
        prompt_type=body.prompt_type,
        brand_id=body.brand_id,
        department=body.department,
        prompt_text=body.prompt_text,
        description=body.description,
        version=next_version,
        is_active=True,
        created_by_user_id=current_user.id,
        updated_by_user_id=current_user.id,
    )
    db.add(new_prompt)
    await db.flush()

    await log_action(
        db, AuditAction.PROMPT_LIBRARY_UPDATED,
        user_id=current_user.id,
        payload={"prompt_type": body.prompt_type, "brand_id": str(body.brand_id), "version": next_version},
    )
    return new_prompt


@router.patch("/prompt-library/{prompt_id}", response_model=PromptLibraryRead)
async def update_prompt(
    prompt_id: uuid.UUID,
    body: PromptLibraryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(PromptLibrary).where(PromptLibrary.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    # Create new version (department can be updated here too)
    new_prompt = PromptLibrary(
        prompt_type=prompt.prompt_type,
        brand_id=prompt.brand_id,
        department=body.department if body.department is not None else prompt.department,
        prompt_text=body.prompt_text,
        description=body.description or prompt.description,
        version=prompt.version + 1,
        is_active=True,
        created_by_user_id=prompt.created_by_user_id,
        updated_by_user_id=current_user.id,
    )
    prompt.is_active = False
    db.add(new_prompt)
    await db.flush()

    await log_action(
        db, AuditAction.PROMPT_LIBRARY_UPDATED,
        user_id=current_user.id,
        payload={"old_version": prompt.version, "new_version": new_prompt.version},
    )
    return new_prompt

# ─── Standalone manual image generation ──────────────

@router.post("/generate/manual", response_model=dict)
async def manual_generate_standalone(
    request: Request,
    prompt: str = Form(...),
    source_image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Standalone manual image generation — not tied to any product."""
    from app.services.gemini_service import generate_images_gemini

    source_bytes = None
    if source_image and source_image.filename:
        source_bytes = await source_image.read()
        if len(source_bytes) == 0:
            source_bytes = None

    images, _ = await asyncio.to_thread(generate_images_gemini, prompt, 1, source_bytes)

    await log_action(db, AuditAction.MANUAL_PHOTOSHOOT, user_id=current_user.id, sku_id=None,
                     payload={"prompt_length": len(prompt), "has_source_image": source_bytes is not None},
                     ip_address=request.client.host if request.client else None)

    return {"image_data": b64mod.b64encode(images[0]).decode(), "mime_type": "image/png"}
