import asyncio
import sys
import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db, AsyncSessionLocal
from app.models import User, Brand, AuditLog, UserRole, AuditAction, Product, ProductPrompt, ProductStatus
from app.schemas import UserRead, UserCreate, UserUpdate, BrandRead, BrandUpdate, AuditLogRead
from app.middleware.auth import require_admin, require_editor, get_current_user
from app.services.audit_service import log_action

router = APIRouter(tags=["admin"])


# ─── Users ───────────────────────────────────────────────

@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("/users", response_model=UserRead)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new local user."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "User with this email already exists")

    from app.middleware.auth_local import hash_password
    user = User(
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        password_hash=hash_password("changeme123"),  # user must reset on first login
    )
    db.add(user)
    await db.flush()

    await log_action(db, AuditAction.USER_CREATED, user_id=current_user.id,
                     payload={"email": body.email, "role": body.role.value})
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            await log_action(db, AuditAction.USER_DEACTIVATED, user_id=current_user.id,
                             payload={"target_user": str(user_id)})
    return user


# ─── Categories ──────────────────────────────────────────

@router.get("/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models import Category
    result = await db.execute(select(Category).order_by(Category.name))
    cats = result.scalars().all()
    return [{"id": str(c.id), "name": c.name, "hierarchy": c.hierarchy} for c in cats]


# ─── Brands ──────────────────────────────────────────────

@router.get("/brands", response_model=list[BrandRead])
async def list_brands(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Brand).order_by(Brand.brand_name))
    return result.scalars().all()


@router.patch("/brands/{brand_id}", response_model=BrandRead)
async def update_brand(
    brand_id: uuid.UUID,
    body: BrandUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = await db.execute(select(Brand).where(Brand.id == brand_id))
    brand = result.scalar_one_or_none()
    if not brand:
        raise HTTPException(404, "Brand not found")
    if body.ai_forbidden is not None:
        brand.ai_forbidden = body.ai_forbidden
    return brand


# ─── Dev Tools ────────────────────────────────────────────

@router.post("/generate-all-pending", response_model=dict)
async def generate_all_pending(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_editor),
):
    """Queue AI generation for all PENDING_AI products."""
    from app.services.ai_runner import run_ai_generation_inline

    result = await db.execute(
        select(Product, ProductPrompt)
        .join(ProductPrompt, (ProductPrompt.sku_id == Product.sku_id) & (ProductPrompt.is_current == True))
        .where(Product.status == ProductStatus.PENDING_AI)
    )
    rows = result.all()

    if not rows:
        return {"queued": 0, "message": "No PENDING_AI products found"}

    jobs = [(p.sku_id, p.marketing_name or "", pp.prompt_text) for p, pp in rows]

    for product, _ in rows:
        product.status = ProductStatus.AI_GENERATING
    await db.commit()

    async def _run_one(sku_id: str, marketing_name: str, prompt_text: str, session_id: str):
        await run_ai_generation_inline(sku_id, prompt_text, session_id, marketing_name)

    for sku_id, marketing_name, prompt_text in jobs:
        session_id = str(uuid.uuid4())
        asyncio.create_task(_run_one(sku_id, marketing_name, prompt_text, session_id))

    return {"queued": len(jobs), "message": f"Generation started for {len(jobs)} products"}


@router.post("/import-excel", response_model=dict)
async def import_excel_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Import products from backend/data/products.xlsx (idempotent)."""
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from import_excel import import_excel, DEFAULT_EXCEL_PATH
    excel_path = os.path.join(backend_dir, "data", "products.xlsx")
    try:
        result = await import_excel(db, excel_path)
        await db.commit()
        return {"message": "Import complete", "created": result}
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Import failed: {str(e)}")


# ─── Audit Trail ─────────────────────────────────────────

@router.get("/audit-trail", response_model=list[AuditLogRead])
async def get_audit_trail(
    limit: int = Query(200, ge=1, le=1000),
    action: str = Query(None),
    sku_id: str = Query(None),
    user_id: str = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime, timezone
    from sqlalchemy import and_

    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if sku_id:
        filters.append(AuditLog.sku_id == sku_id)
    if user_id:
        try:
            filters.append(AuditLog.user_id == uuid.UUID(user_id))
        except ValueError:
            pass
    if date_from:
        try:
            filters.append(AuditLog.occurred_at >= datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    if date_to:
        try:
            filters.append(AuditLog.occurred_at <= datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc))
        except ValueError:
            pass

    q = select(AuditLog).options(selectinload(AuditLog.user))
    if filters:
        from sqlalchemy import and_
        q = q.where(and_(*filters))
    q = q.order_by(AuditLog.occurred_at.desc()).limit(limit)

    result = await db.execute(q)
    return result.scalars().all()
