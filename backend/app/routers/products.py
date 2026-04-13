from datetime import datetime, timezone, timedelta
from typing import Optional
import math
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Product, ProductPrompt, User, ProductStatus
from app.schemas import (
    PaginatedProducts, ProductDetail, ProductSummary,
    ProductSelectRequest, ProductImages, ImageItem
)
from app.middleware.auth import get_current_user, require_editor
from app.services.prompt_service import get_or_create_product_prompt
from app.services.audit_service import log_action
from app.models import AuditAction
from app.config import get_settings
import structlog

router = APIRouter(tags=["products"])
settings = get_settings()

from app.services.storage_local import presign_keys, get_presigned_url
log = structlog.get_logger()


def _build_images(product: Product) -> ProductImages:
    """
    Convert local file keys stored on product → ImageItem list with presigned URLs.
    image_metadata holds per-image status/sort info.
    """
    meta = product.image_metadata or {}
    ai_meta = {item["key"]: item for item in meta.get("ai", [])}
    orig_meta = {item["key"]: item for item in meta.get("original", [])}

    original_keys = product.original_image_keys or []
    ai_keys = product.ai_image_keys or []
    approved_keys_set = set(product.approved_image_keys or [])

    # Batch presign all keys in one go
    all_keys = original_keys + ai_keys
    if not all_keys:
        return ProductImages()

    original_urls = presign_keys(original_keys)
    ai_urls = presign_keys(ai_keys)

    original_items = [
        ImageItem(
            key=key,
            url=url,
            sort=orig_meta.get(key, {}).get("sort", i),
            status="APPROVED",
        )
        for i, (key, url) in enumerate(zip(original_keys, original_urls))
    ]

    def _ai_status(key: str) -> str:
        # Prefer the status recorded in metadata; fall back to approved_image_keys
        # as the authoritative source.
        return (
            ai_meta.get(key, {}).get("status")
            or ("APPROVED" if key in approved_keys_set else "PENDING")
        )

    ai_items = [
        ImageItem(
            key=key,
            url=url,
            sort=ai_meta.get(key, {}).get("sort", i),
            status=_ai_status(key),
            recall_reason=ai_meta.get(key, {}).get("recall_reason"),
        )
        for i, (key, url) in enumerate(zip(ai_keys, ai_urls))
    ]

    return ProductImages(original=original_items, ai=ai_items)


@router.get("/seasons", response_model=list[str])
async def get_distinct_seasons(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product.season).where(Product.season.isnot(None)).distinct().order_by(Product.season)
    )
    return [row[0] for row in result.all()]


@router.get("/colours", response_model=list[str])
async def get_distinct_colours(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product.colour).where(Product.colour.isnot(None)).distinct().order_by(Product.colour)
    )
    return [row[0] for row in result.all()]


@router.get("/campaigns", response_model=list[str])
async def get_distinct_campaigns(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product.campaign_name).where(Product.campaign_name.isnot(None)).distinct().order_by(Product.campaign_name)
    )
    return [row[0] for row in result.all()]


@router.get("/departments", response_model=list[str])
async def get_distinct_departments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product.department).where(Product.department.isnot(None)).distinct().order_by(Product.department)
    )
    return [row[0] for row in result.all()]


@router.get("", response_model=PaginatedProducts)
async def list_products(
    approval_date: Optional[str] = Query(None),
    ingestion_date: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    brand_id: Optional[uuid.UUID] = Query(None),
    category_id: Optional[uuid.UUID] = Query(None),
    colour: Optional[str] = Query(None),
    campaign_name: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    stock_level: Optional[str] = Query(None),   # "none" | "low" | "high"
    status: Optional[ProductStatus] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import datetime as dt_module
    from sqlalchemy import cast, Date

    parsed_date = None
    if approval_date:
        try:
            parsed_date = dt_module.date.fromisoformat(approval_date)
        except ValueError:
            raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")

    parsed_ingestion_date = None
    if ingestion_date:
        try:
            parsed_ingestion_date = dt_module.date.fromisoformat(ingestion_date)
        except ValueError:
            raise HTTPException(400, "Invalid ingestion_date format, use YYYY-MM-DD")

    base_where = []
    if parsed_date:
        base_where.append(Product.text_approval_date == parsed_date)
    if parsed_ingestion_date:
        base_where.append(cast(Product.ingested_at, Date) == parsed_ingestion_date)
    if season:
        base_where.append(Product.season == season)
    if brand_id:
        base_where.append(Product.brand_id == brand_id)
    if category_id:
        base_where.append(Product.category_id == category_id)
    if colour:
        base_where.append(Product.colour == colour)
    if campaign_name:
        base_where.append(Product.campaign_name == campaign_name)
    if department:
        base_where.append(Product.department == department)
    if stock_level:
        # hki_stock: none = 0, low = 1-19, high = 20+
        if stock_level == "none":
            base_where.append(or_(Product.hki_stock == 0, Product.hki_stock.is_(None)))
        elif stock_level == "low":
            base_where.append(and_(Product.hki_stock >= 1, Product.hki_stock < 20))
        elif stock_level == "high":
            base_where.append(Product.hki_stock >= 20)
    if status:
        base_where.append(Product.status == status)
    if search:
        term = f"%{search}%"
        base_where.append(or_(Product.sku_id.ilike(term), Product.marketing_name.ilike(term)))

    count_q = select(func.count()).select_from(Product).where(and_(*base_where))
    data_q = (
        select(Product)
        .options(selectinload(Product.brand), selectinload(Product.category))
        .where(and_(*base_where))
        .order_by(Product.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    total = (await db.execute(count_q)).scalar()
    products = (await db.execute(data_q)).scalars().all()

    items = []
    for p in products:
        ai_keys = p.ai_image_keys or []
        approved_keys = p.approved_image_keys or []
        orig_keys = p.original_image_keys or []

        # Thumbnail: first approved AI, first AI, or first original image
        thumb_key = (approved_keys or ai_keys or orig_keys or [None])[0]
        thumb_url = get_presigned_url(thumb_key) if thumb_key else None

        # Preview URLs: original + AI images merged, up to 5 for hover cycling on the grid
        seen: set = set()
        merged: list = []
        for k in (orig_keys + ai_keys):
            if k not in seen:
                seen.add(k)
                merged.append(k)
        preview_keys = merged[:5]
        preview_urls = [get_presigned_url(k) for k in preview_keys if k]

        items.append(ProductSummary(
            sku_id=p.sku_id,
            marketing_name=p.marketing_name,
            status=p.status,
            season=p.season,
            text_approval_date=p.text_approval_date,
            is_user_selected=p.is_user_selected,
            dc_stock=p.dc_stock,
            hki_stock=p.hki_stock,
            colour=p.colour,
            size=p.size,
            department=p.department,
            campaign_name=p.campaign_name,
            brand=p.brand,
            category=p.category,
            original_image_count=len(orig_keys),
            ai_image_count=len(ai_keys),
            approved_image_count=len(approved_keys),
            thumbnail_url=thumb_url,
            preview_urls=preview_urls,
            updated_at=p.updated_at,
        ))

    return PaginatedProducts(
        items=items, total=total, page=page,
        page_size=page_size, pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/{sku_id}", response_model=ProductDetail)
async def get_product(
    sku_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Product)
        .options(selectinload(Product.brand), selectinload(Product.category),
                 selectinload(Product.prompts).selectinload(ProductPrompt.created_by),
                 selectinload(Product.locked_by))
        .where(Product.sku_id == sku_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, f"Product {sku_id} not found")

    prompt = await get_or_create_product_prompt(db, product, current_user.id)
    images = _build_images(product)   # S3 keys → presigned URLs

    ai_keys = product.ai_image_keys or []
    approved_keys = product.approved_image_keys or []
    orig_keys = product.original_image_keys or []

    return ProductDetail(
        sku_id=product.sku_id,
        marketing_name=product.marketing_name,
        description=product.description,
        material_info=product.material_info,
        keywords=product.keywords,
        season=product.season,
        text_approval_date=product.text_approval_date,
        is_user_selected=product.is_user_selected,
        dc_stock=product.dc_stock,
        hki_stock=product.hki_stock,
        campaign_name=product.campaign_name,
        department=product.department,
        sibling_skus=product.sibling_skus,
        brand=product.brand,
        category=product.category,
        status=product.status,
        images=images,
        current_prompt=prompt,
        locked_by=product.locked_by,
        locked_at=product.locked_at,
        original_image_count=len(orig_keys),
        ai_image_count=len(ai_keys),
        approved_image_count=len(approved_keys),
        ingested_at=product.ingested_at,
        updated_at=product.updated_at,
        ai_description=product.ai_description,
        ai_keywords=product.ai_keywords,
        ai_suggested_category=product.ai_suggested_category,
        generation_error=(product.image_metadata or {}).get("error"),
        google_api_calls=product.google_api_calls or 0,
        google_api_cost_usd=float(product.google_api_cost_usd or 0),
    )


@router.patch("/{sku_id}/select", response_model=dict)
async def select_product(
    sku_id: str,
    body: ProductSelectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    product.is_user_selected = body.selected
    await log_action(db, AuditAction.PRODUCT_SELECTED if body.selected else AuditAction.PRODUCT_DESELECTED,
                     user_id=current_user.id, sku_id=sku_id,
                     payload={"selected": body.selected},
                     ip_address=request.client.host if request.client else None)
    return {"sku_id": sku_id, "selected": body.selected}


@router.post("/{sku_id}/lock", response_model=dict)
async def lock_product(sku_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_editor)):
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    now = datetime.now(timezone.utc)
    if (product.locked_by_user_id and product.locked_by_user_id != current_user.id
            and product.locked_at and (now - product.locked_at).seconds < settings.product_lock_ttl_seconds):
        raise HTTPException(409, "Product is being edited by another user")

    product.locked_by_user_id = current_user.id
    product.locked_at = now
    return {"locked": True, "expires_in": settings.product_lock_ttl_seconds}


@router.post("/{sku_id}/unlock", response_model=dict)
async def unlock_product(sku_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_editor)):
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    if product.locked_by_user_id == current_user.id:
        product.locked_by_user_id = None
        product.locked_at = None
    return {"unlocked": True}


@router.post("/{sku_id}/generate-prompt", response_model=dict)
async def generate_ai_prompt(
    sku_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """
    Use Google Gemini to analyze the product's original image and generate
    an AI editing prompt. The generated prompt is returned for user review
    and is NOT automatically saved — the user can edit and then save it.
    """
    result = await db.execute(
        select(Product).options(selectinload(Product.brand)).where(Product.sku_id == sku_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    orig_keys = product.original_image_keys or []
    if not orig_keys:
        raise HTTPException(400, "Product has no original images to analyze")

    # Use first original image (presigned / CDN URL)
    image_url = get_presigned_url(orig_keys[0])

    try:
        from app.services.google_ai_service import generate_prompt_from_image
        result_data, prompt_cost = await generate_prompt_from_image(
            image_url=image_url,
            marketing_name=product.marketing_name or sku_id,
            description=product.description,
            material_info=product.material_info,
            keywords=product.keywords,
        )
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        log.error("Google AI prompt generation failed", sku_id=sku_id, error=str(e))
        raise HTTPException(500, f"Prompt generation failed: {str(e)}")

    # Save AI-generated content to dedicated AI fields
    if result_data.get("marketing_description"):
        product.ai_description = result_data["marketing_description"]
    if result_data.get("meta_keywords"):
        product.ai_keywords = result_data["meta_keywords"]
    if result_data.get("suggested_category"):
        product.ai_suggested_category = result_data["suggested_category"]

    # Accumulate Google API cost
    product.google_api_calls = (product.google_api_calls or 0) + 1
    product.google_api_cost_usd = float(product.google_api_cost_usd or 0) + prompt_cost

    await db.commit()

    return {
        "sku_id": sku_id,
        "prompts": result_data.get("prompts", []),
        "analysis": result_data,
    }


@router.post("/{sku_id}/manual-generate", response_model=dict)
async def manual_generate_image(
    sku_id: str,
    prompt: str = Form(...),
    source_image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """
    Generate an image from a custom prompt and optional uploaded source image.
    Calls Gemini image generation and returns base64-encoded result directly.
    """
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    source_bytes = None
    if source_image and source_image.filename:
        source_bytes = await source_image.read()
        if len(source_bytes) == 0:
            source_bytes = None

    try:
        import asyncio
        import base64 as b64mod
        from app.services.gemini_service import generate_images_gemini

        images = await asyncio.to_thread(generate_images_gemini, prompt, 1, source_bytes)
        if not images:
            raise HTTPException(500, "Gemini returned no images")

        return {
            "image_data": b64mod.b64encode(images[0]).decode(),
            "mime_type": "image/png",
        }
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except HTTPException:
        raise
    except Exception as e:
        log.error("Manual image generation failed", sku_id=sku_id, error=str(e))
        raise HTTPException(500, f"Image generation failed: {str(e)}")
