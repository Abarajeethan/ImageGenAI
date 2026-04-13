from datetime import date, timedelta, datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case

from app.database import get_db
from app.models import Product, User, AuditLog, Brand, AuditAction, ProductStatus
from app.middleware.auth import get_current_user
from app.schemas import AnalyticsSummary, DailyStat, BrandStat

router = APIRouter(tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    total_ingested = (await db.execute(
        select(func.count(Product.sku_id)).where(Product.text_approval_date >= since)
    )).scalar() or 0

    total_manual = (await db.execute(
        select(func.count(AuditLog.id)).where(
            and_(AuditLog.action == AuditAction.MANUAL_PHOTOSHOOT, AuditLog.occurred_at >= cutoff)
        )
    )).scalar() or 0

    total_ai_gen = (await db.execute(
        select(func.count(AuditLog.id)).where(
            and_(AuditLog.action == AuditAction.AI_GENERATED, AuditLog.occurred_at >= cutoff)
        )
    )).scalar() or 0

    total_approved = (await db.execute(
        select(func.count(Product.sku_id)).where(Product.status == ProductStatus.APPROVED)
    )).scalar() or 0

    total_recalled = (await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.action == AuditAction.IMAGE_RECALLED)
    )).scalar() or 0

    total_rejected = (await db.execute(
        select(func.count(AuditLog.id)).where(AuditLog.action == AuditAction.IMAGE_REJECTED)
    )).scalar() or 0

    cost_row = (await db.execute(
        select(func.sum(Product.google_api_calls), func.sum(Product.google_api_cost_usd))
    )).one()

    approval_rate = round(total_approved / total_ai_gen * 100, 1) if total_ai_gen > 0 else 0

    # Daily trend
    daily_rows = (await db.execute(
        select(
            func.date(AuditLog.occurred_at).label("date"),
            func.sum(case((AuditLog.action == AuditAction.AI_GENERATED, 1), else_=0)).label("generated"),
            func.sum(case((AuditLog.action == AuditAction.IMAGE_APPROVED, 1), else_=0)).label("approved"),
            func.sum(case((AuditLog.action == AuditAction.IMAGE_RECALLED, 1), else_=0)).label("recalled"),
        )
        .where(AuditLog.occurred_at >= cutoff)
        .group_by(func.date(AuditLog.occurred_at))
        .order_by(func.date(AuditLog.occurred_at))
    )).all()

    daily_trend = [
        DailyStat(date=row.date, generated=row.generated or 0, approved=row.approved or 0, recalled=row.recalled or 0)
        for row in daily_rows
    ]

    # By brand
    brand_rows = (await db.execute(
        select(
            Brand.brand_name,
            func.count(Product.sku_id).label("total"),
            func.sum(case((Product.status == ProductStatus.AI_READY, 1), else_=0)).label("ai_ready"),
            func.sum(case((Product.status == ProductStatus.APPROVED, 1), else_=0)).label("approved"),
        )
        .join(Product, Product.brand_id == Brand.id)
        .where(Product.text_approval_date >= since)
        .group_by(Brand.brand_name)
        .order_by(func.count(Product.sku_id).desc())
        .limit(20)
    )).all()

    by_brand = [
        BrandStat(
            brand_name=row.brand_name,
            total_products=row.total or 0,
            ai_ready=row.ai_ready or 0,
            approved=row.approved or 0,
            approval_rate=round((row.approved or 0) / (row.total or 1) * 100, 1),
        )
        for row in brand_rows
    ]

    return AnalyticsSummary(
        total_products_ingested=total_ingested,
        total_ai_generated=total_ai_gen,
        total_manual_photoshoot=total_manual,
        total_approved=total_approved,
        total_recalled=total_recalled,
        total_ai_rejected=total_rejected,
        approval_rate=approval_rate,
        total_google_api_calls=int(cost_row[0] or 0),
        total_google_cost_usd=float(cost_row[1] or 0),
        daily_trend=daily_trend,
        by_brand=by_brand,
    )
