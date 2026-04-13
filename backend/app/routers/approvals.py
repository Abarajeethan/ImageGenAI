"""
Approval workflow — image approve / recall / reject / reorder.
All image state lives in JSON (image_metadata) + list columns on the Product row.
Local file paths are stored; served via /static/images.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Product, User, ProductStatus, AuditAction
from app.schemas import ImageApproveRequest, ImageRecallRequest, ImageReorderRequest, ImageRejectRequest
from app.middleware.auth import get_current_user, require_editor
from app.services.storage_local import presign_keys
from app.services.audit_service import log_action
import structlog

router = APIRouter(tags=["approvals"])
log = structlog.get_logger()


def _get_meta(product: Product) -> dict:
    return product.image_metadata or {"ai": [], "original": []}


def _save_meta(product: Product, meta: dict):
    from sqlalchemy.orm.attributes import flag_modified
    product.image_metadata = meta
    flag_modified(product, "image_metadata")


@router.post("/products/{sku_id}/approve", response_model=dict)
async def approve_images(
    sku_id: str,
    body: ImageApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Mark AI images as Approved in the local DB."""
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    meta = _get_meta(product)
    approved = []
    errors = []
    now = datetime.now(timezone.utc)
    approved_keys = list(product.approved_image_keys or [])

    for key in body.keys:
        ai_entry = next((e for e in meta["ai"] if e["key"] == key), None)
        if not ai_entry:
            errors.append({"key": key, "error": "Key not found in AI images"})
            continue
        if ai_entry.get("status") == "APPROVED":
            approved.append(key)  # idempotent
            continue

        ai_entry["status"] = "APPROVED"
        ai_entry["approved_by"] = str(current_user.id)
        ai_entry["approved_at"] = now.isoformat()

        if key not in approved_keys:
            approved_keys.append(key)
        approved.append(key)

    _save_meta(product, meta)
    product.approved_image_keys = approved_keys
    if approved:
        product.status = ProductStatus.APPROVED

    await log_action(
        db, AuditAction.IMAGE_APPROVED,
        user_id=current_user.id, sku_id=sku_id,
        payload={"approved_keys": approved, "errors": errors},
        ip_address=request.client.host if request.client else None,
    )

    return {"approved": approved, "errors": errors, "product_status": product.status.value}


@router.post("/products/{sku_id}/recall", response_model=dict)
async def recall_image(
    sku_id: str,
    body: ImageRecallRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Recall an approved AI image — marks it RECALLED and deletes the local file."""
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    meta = _get_meta(product)
    ai_entry = next((e for e in meta["ai"] if e["key"] == body.key), None)
    if not ai_entry:
        raise HTTPException(404, "Image key not found")

    is_in_approved_keys = body.key in (product.approved_image_keys or [])
    if ai_entry.get("status") != "APPROVED" and not is_in_approved_keys:
        raise HTTPException(400, f"Image is not APPROVED (current: {ai_entry.get('status')})")

    recall_errors = []

    # Delete local image file
    try:
        from app.services.storage_local import delete_object
        delete_object(body.key)
    except Exception as e:
        recall_errors.append(f"storage delete: {str(e)}")

    ai_entry["status"] = "RECALLED"
    ai_entry["recall_reason"] = body.reason
    ai_entry["recalled_by"] = str(current_user.id)
    ai_entry["recalled_at"] = datetime.now(timezone.utc).isoformat()

    approved_keys = [k for k in (product.approved_image_keys or []) if k != body.key]
    product.approved_image_keys = approved_keys
    if not approved_keys:
        product.status = ProductStatus.AI_READY

    _save_meta(product, meta)

    await log_action(
        db, AuditAction.IMAGE_RECALLED, user_id=current_user.id, sku_id=sku_id,
        payload={"key": body.key, "reason": body.reason, "errors": recall_errors},
        ip_address=request.client.host if request.client else None,
    )

    return {"recalled": True, "key": body.key, "errors": recall_errors}


@router.post("/products/{sku_id}/reject-ai-image", response_model=dict)
async def reject_ai_image(
    sku_id: str,
    body: ImageRejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Reject (delete) an AI image regardless of status."""
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    meta = _get_meta(product)
    ai_entry = next((e for e in meta["ai"] if e["key"] == body.key), None)
    if not ai_entry:
        raise HTTPException(404, "Image key not found in AI images")

    product.ai_image_keys       = [k for k in (product.ai_image_keys or [])       if k != body.key]
    product.approved_image_keys = [k for k in (product.approved_image_keys or []) if k != body.key]
    meta["ai"] = [e for e in meta["ai"] if e["key"] != body.key]
    _save_meta(product, meta)

    try:
        from app.services.storage_local import move_to_rejected
        move_to_rejected(body.key)
    except Exception as e:
        log.warning("Failed to move rejected image", key=body.key, error=str(e))

    if not product.ai_image_keys:
        product.status = ProductStatus.AI_READY

    await log_action(
        db, AuditAction.IMAGE_REJECTED, user_id=current_user.id, sku_id=sku_id,
        payload={"key": body.key},
        ip_address=request.client.host if request.client else None,
    )

    return {"rejected": True, "key": body.key}


@router.patch("/products/{sku_id}/image-order", response_model=dict)
async def reorder_images(
    sku_id: str,
    body: ImageReorderRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Reorder AI images — body.ai_keys is the new ordered list of local file keys."""
    result = await db.execute(select(Product).where(Product.sku_id == sku_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    meta = _get_meta(product)
    ai_meta_map = {e["key"]: e for e in meta["ai"]}

    existing_keys = set(product.ai_image_keys or [])
    for key in body.ai_keys:
        if key not in existing_keys:
            raise HTTPException(400, f"Key {key} not found in product AI images")

    for i, key in enumerate(body.ai_keys):
        if key in ai_meta_map:
            ai_meta_map[key]["sort"] = i

    meta["ai"] = [ai_meta_map[k] for k in body.ai_keys if k in ai_meta_map]
    product.ai_image_keys = body.ai_keys
    _save_meta(product, meta)

    await log_action(
        db, AuditAction.IMAGE_REORDERED, user_id=current_user.id, sku_id=sku_id,
        payload={"new_order": body.ai_keys},
        ip_address=request.client.host if request.client else None,
    )

    return {"reordered": True, "new_order": body.ai_keys}


@router.get("/products/{sku_id}/audit-log", response_model=list)
async def get_product_audit_log(
    sku_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models import AuditLog
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(AuditLog).options(selectinload(AuditLog.user))
        .where(AuditLog.sku_id == sku_id)
        .order_by(AuditLog.occurred_at.desc()).limit(100)
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(l.id), "action": l.action.value,
            "user": {"name": l.user.full_name, "email": l.user.email} if l.user else None,
            "payload": l.payload, "occurred_at": l.occurred_at.isoformat(),
        }
        for l in logs
    ]
