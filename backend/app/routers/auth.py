"""Auth router — local JWT only."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.config import get_settings
from app.models import User
from app.schemas import TokenResponse, LoginRequest, RefreshRequest
from app.middleware.auth import get_current_user
from app.middleware.auth_local import (
    authenticate_user, create_access_token, create_refresh_token, decode_token
)

settings = get_settings()
router = APIRouter(tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.username, body.password)
    await db.commit()
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email, user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Not a refresh token")
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "User not found")
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.email, user.role.value),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    return {
        "id":        str(current_user.id),
        "email":     current_user.email,
        "full_name": current_user.full_name,
        "role":      current_user.role.value,
        "is_active": current_user.is_active,
    }
