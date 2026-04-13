"""
Local JWT auth — users stored in DB with bcrypt-hashed passwords.
Access tokens signed with SECRET_KEY, no external service needed.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, UserRole
from app.config import get_settings

settings = get_settings()
bearer = HTTPBearer(auto_error=False)

ALGORITHM = "HS256"


# ─── Password helpers ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ─── Token helpers ───────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str, role: str, expires_minutes: int = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "email": email, "role": role, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=30)
    return jwt.encode(
        {"sub": user_id, "type": "refresh", "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


# ─── Login ───────────────────────────────────────────────────────────────────

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.password_hash:
        raise HTTPException(status_code=401, detail="User has no password set")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user.last_login_at = datetime.now(timezone.utc)
    return user


# ─── Dependencies ────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=403, detail="Not authenticated")

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id), User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def require_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.EDITOR, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Editor role required")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


# ─── Seed default dev users ──────────────────────────────────────────────────

async def seed_dev_users(db: AsyncSession):
    """
    Called on startup in dev mode.
    Creates default admin + editor users if they don't exist.
    """
    users_to_create = [
        {
            "email": settings.dev_admin_email,
            "password": settings.dev_admin_password,
            "full_name": "Dev Admin",
            "role": UserRole.ADMIN,
        },
        {
            "email": settings.dev_editor_email,
            "password": settings.dev_editor_password,
            "full_name": "Dev Editor",
            "role": UserRole.EDITOR,
        },
    ]

    for u in users_to_create:
        result = await db.execute(select(User).where(User.email == u["email"]))
        existing = result.scalar_one_or_none()
        if not existing:
            db.add(User(
                id=uuid.uuid4(),
                email=u["email"],
                full_name=u["full_name"],
                role=u["role"],
                is_active=True,
                password_hash=hash_password(u["password"]),
            ))
            print(f"  ✓ Created dev user: {u['email']} / {u['password']} ({u['role'].value})")
        elif not existing.password_hash:
            existing.password_hash = hash_password(u["password"])
            print(f"  ✓ Set password for existing user: {u['email']} / {u['password']}")

    await db.commit()
