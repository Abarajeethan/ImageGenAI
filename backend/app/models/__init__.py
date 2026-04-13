import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Text, Integer, Boolean, DateTime, Date, ForeignKey,
    Enum as SAEnum, JSON, Index, func, UniqueConstraint, Numeric, Uuid
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


# ──────────────── Enums ────────────────

class ProductStatus(str, enum.Enum):
    PENDING_AI    = "PENDING_AI"
    AI_GENERATING = "AI_GENERATING"
    AI_READY      = "AI_READY"
    AI_FAILED     = "AI_FAILED"
    USER_SELECTED = "USER_SELECTED"
    APPROVED      = "APPROVED"


class PromptType(str, enum.Enum):
    GENERAL = "GENERAL"
    BRAND   = "BRAND"


class UserRole(str, enum.Enum):
    ADMIN  = "ADMIN"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"


class AuditAction(str, enum.Enum):
    PRODUCT_SELECTED      = "PRODUCT_SELECTED"
    PRODUCT_DESELECTED    = "PRODUCT_DESELECTED"
    PROMPT_EDITED         = "PROMPT_EDITED"
    AI_GENERATED          = "AI_GENERATED"
    AI_REGENERATED        = "AI_REGENERATED"
    IMAGE_APPROVED        = "IMAGE_APPROVED"
    IMAGE_RECALLED        = "IMAGE_RECALLED"
    IMAGE_REJECTED        = "IMAGE_REJECTED"
    IMAGE_REORDERED       = "IMAGE_REORDERED"
    MANUAL_PHOTOSHOOT     = "MANUAL_PHOTOSHOOT"
    PROMPT_LIBRARY_UPDATED = "PROMPT_LIBRARY_UPDATED"
    USER_CREATED          = "USER_CREATED"
    USER_DEACTIVATED      = "USER_DEACTIVATED"


# ──────────────── Models ────────────────

class Brand(Base):
    __tablename__ = "brands"

    id:          Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    brand_name:  Mapped[str]       = mapped_column(String(255), unique=True, nullable=False)
    ai_forbidden: Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)
    created_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    products:       Mapped[list["Product"]]       = relationship("Product", back_populates="brand")
    prompt_library: Mapped[list["PromptLibrary"]] = relationship("PromptLibrary", back_populates="brand")


class Category(Base):
    __tablename__ = "categories"

    id:               Mapped[uuid.UUID]     = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name:             Mapped[str]           = mapped_column(String(255), nullable=False)
    hierarchy:        Mapped[Optional[str]] = mapped_column(Text)
    category_path_key: Mapped[Optional[str]] = mapped_column(Text, unique=True)

    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    sku_id:      Mapped[str]            = mapped_column(String(100), primary_key=True)
    brand_id:    Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("brands.id"), index=True)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("categories.id"), index=True)

    # Content fields
    marketing_name:  Mapped[Optional[str]] = mapped_column(Text)
    description:     Mapped[Optional[str]] = mapped_column(Text)
    material_info:   Mapped[Optional[str]] = mapped_column(Text)
    keywords:        Mapped[Optional[list]] = mapped_column(JSON, default=list)
    season:          Mapped[Optional[str]] = mapped_column(String(100), index=True)
    campaign_name:   Mapped[Optional[str]] = mapped_column(String(255))
    colour:          Mapped[Optional[str]] = mapped_column(String(100), index=True)
    size:            Mapped[Optional[str]] = mapped_column(Text)
    dc_stock:        Mapped[Optional[int]] = mapped_column(Integer)
    hki_stock:       Mapped[Optional[int]] = mapped_column(Integer)
    classic_department_name: Mapped[Optional[str]] = mapped_column(String(255))
    opil_department_name:    Mapped[Optional[str]] = mapped_column(String(255))
    object_type:     Mapped[Optional[str]] = mapped_column(String(255))
    department:      Mapped[Optional[str]] = mapped_column(String(255))

    # AI-generated content fields
    ai_description:       Mapped[Optional[str]]  = mapped_column(Text)
    ai_keywords:          Mapped[Optional[list]] = mapped_column(JSON, default=list)
    ai_suggested_category: Mapped[Optional[str]] = mapped_column(Text)

    # Status & workflow
    status: Mapped[ProductStatus] = mapped_column(
        SAEnum(ProductStatus), default=ProductStatus.PENDING_AI, index=True
    )
    text_approval_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    is_user_selected:   Mapped[bool]           = mapped_column(Boolean, default=False)

    # Locking (concurrent editing)
    locked_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"))
    locked_at:         Mapped[Optional[datetime]]  = mapped_column(DateTime(timezone=True))

    # Images stored as JSON arrays of local file paths
    original_image_keys: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    ai_image_keys:       Mapped[Optional[list]] = mapped_column(JSON, default=list)
    approved_image_keys: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Per-image metadata: {"ai": [...], "original": [...]}
    image_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Misc
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    sibling_skus:  Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # Google API cost tracking
    google_api_calls:    Mapped[int]   = mapped_column(Integer, default=0, nullable=False)
    google_api_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)

    # Timestamps
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    brand:     Mapped[Optional["Brand"]]     = relationship("Brand", back_populates="products")
    category:  Mapped[Optional["Category"]]  = relationship("Category", back_populates="products")
    prompts:   Mapped[list["ProductPrompt"]] = relationship("ProductPrompt", back_populates="product", order_by="ProductPrompt.created_at.desc()")
    locked_by: Mapped[Optional["User"]]      = relationship("User", foreign_keys=[locked_by_user_id])
    audit_logs: Mapped[list["AuditLog"]]     = relationship("AuditLog", back_populates="product")

    __table_args__ = (
        Index("ix_products_text_approval_date_status", "text_approval_date", "status"),
        Index("ix_products_season_category", "season", "category_id"),
    )


class PromptLibrary(Base):
    __tablename__ = "prompt_library"

    id:          Mapped[uuid.UUID]     = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    prompt_type: Mapped[PromptType]    = mapped_column(SAEnum(PromptType), nullable=False)
    brand_id:    Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("brands.id"))
    department:  Mapped[Optional[str]] = mapped_column(String(255))
    prompt_text: Mapped[str]           = mapped_column(Text, nullable=False)
    version:     Mapped[int]           = mapped_column(Integer, default=1)
    is_active:   Mapped[bool]          = mapped_column(Boolean, default=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"))
    updated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    brand:      Mapped[Optional["Brand"]] = relationship("Brand", back_populates="prompt_library")
    created_by: Mapped[Optional["User"]]  = relationship("User", foreign_keys=[created_by_user_id])
    updated_by: Mapped[Optional["User"]]  = relationship("User", foreign_keys=[updated_by_user_id])


class ProductPrompt(Base):
    """Versioned history of prompts used/edited per product."""
    __tablename__ = "product_prompts"

    id:          Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sku_id:      Mapped[str]       = mapped_column(String(100), ForeignKey("products.sku_id"), index=True)
    prompt_text: Mapped[str]       = mapped_column(Text, nullable=False)

    general_prompt_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("prompt_library.id"))
    brand_prompt_id:   Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("prompt_library.id"))

    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    is_current:  Mapped[bool] = mapped_column(Boolean, default=True)

    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product:    Mapped["Product"]       = relationship("Product", back_populates="prompts")
    created_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by_user_id])


class User(Base):
    __tablename__ = "users"

    id:            Mapped[uuid.UUID]     = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email:         Mapped[str]           = mapped_column(String(255), unique=True, nullable=False)
    full_name:     Mapped[str]           = mapped_column(String(255), nullable=False)
    role:          Mapped[UserRole]      = mapped_column(SAEnum(UserRole), default=UserRole.EDITOR)
    is_active:     Mapped[bool]          = mapped_column(Boolean, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id:         Mapped[uuid.UUID]     = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    sku_id:     Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("products.sku_id"), index=True)
    user_id:    Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    action:     Mapped[AuditAction]   = mapped_column(SAEnum(AuditAction), nullable=False, index=True)
    payload:    Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    occurred_at: Mapped[datetime]     = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="audit_logs")
    user:    Mapped[Optional["User"]]    = relationship("User", back_populates="audit_logs")
