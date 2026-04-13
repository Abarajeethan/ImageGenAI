from typing import Optional, Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models import AuditLog, AuditAction


async def log_action(
    db: AsyncSession,
    action: AuditAction,
    user_id: Optional[uuid.UUID] = None,
    sku_id: Optional[str] = None,
    payload: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        sku_id=sku_id,
        user_id=user_id,
        action=action,
        payload=payload or {},
        ip_address=ip_address,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    return entry
