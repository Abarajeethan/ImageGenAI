from __future__ import annotations
import uuid
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.models import ProductStatus, PromptType, UserRole, AuditAction


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ──────────────── Brand ────────────────

class BrandBase(BaseSchema):
    brand_name: str
    ai_forbidden: bool = False

class BrandRead(BrandBase):
    id: uuid.UUID
    created_at: datetime

class BrandUpdate(BaseSchema):
    ai_forbidden: Optional[bool] = None


# ──────────────── Category ────────────────

class CategoryRead(BaseSchema):
    id: uuid.UUID
    name: str
    hierarchy: Optional[str] = None


# ──────────────── Images ────────────────

class ImageItem(BaseSchema):
    key: str
    url: str
    sort: int
    status: str = "PENDING"
    recall_reason: Optional[str] = None

class ProductImages(BaseSchema):
    original: List[ImageItem] = []
    ai: List[ImageItem] = []

class ImageApproveRequest(BaseSchema):
    keys: List[str] = Field(..., description="File keys of AI images to approve")

class ImageRecallRequest(BaseSchema):
    key: str = Field(..., description="File key of the image to recall")
    reason: str = Field(..., min_length=5, max_length=500)

class ImageRejectRequest(BaseSchema):
    key: str = Field(..., description="File key of the AI image to reject/delete")

class ImageReorderRequest(BaseSchema):
    ai_keys: List[str]


# ──────────────── Prompt ────────────────

class PromptLibraryRead(BaseSchema):
    id: uuid.UUID
    prompt_type: PromptType
    brand_id: Optional[uuid.UUID]
    department: Optional[str]
    prompt_text: str
    version: int
    is_active: bool
    description: Optional[str]
    updated_at: datetime

class PromptLibraryCreate(BaseSchema):
    prompt_type: PromptType
    brand_id: Optional[uuid.UUID] = None
    department: Optional[str] = None
    prompt_text: str = Field(..., min_length=10)
    description: Optional[str] = None

class PromptLibraryUpdate(BaseSchema):
    prompt_text: str = Field(..., min_length=10)
    description: Optional[str] = None
    department: Optional[str] = None

class ProductPromptRead(BaseSchema):
    id: uuid.UUID
    sku_id: str
    prompt_text: str
    is_override: bool
    is_current: bool
    created_at: datetime
    created_by: Optional[UserSummary] = None

class ProductPromptUpdate(BaseSchema):
    prompt_text: str = Field(..., min_length=10)


# ──────────────── Product ────────────────

class ProductSummary(BaseSchema):
    sku_id: str
    marketing_name: Optional[str]
    status: ProductStatus
    season: Optional[str]
    text_approval_date: Optional[date]
    is_user_selected: bool
    dc_stock: Optional[int]
    hki_stock: Optional[int]
    colour: Optional[str] = None
    size: Optional[str] = None
    department: Optional[str] = None
    campaign_name: Optional[str]
    brand: Optional[BrandRead]
    category: Optional[CategoryRead]
    original_image_count: int = 0
    ai_image_count: int = 0
    approved_image_count: int = 0
    thumbnail_url: Optional[str] = None
    preview_urls: List[str] = []
    updated_at: datetime


class ProductDetail(ProductSummary):
    description: Optional[str]
    material_info: Optional[str]
    keywords: Optional[List[str]]
    sibling_skus: Optional[List[str]]
    images: ProductImages = ProductImages()
    current_prompt: Optional[ProductPromptRead] = None
    locked_by: Optional[UserSummary] = None
    locked_at: Optional[datetime]
    ingested_at: datetime
    ai_description: Optional[str] = None
    ai_keywords: Optional[List[str]] = None
    ai_suggested_category: Optional[str] = None
    generation_error: Optional[str] = None
    google_api_calls: int = 0
    google_api_cost_usd: float = 0.0

class ProductSelectRequest(BaseSchema):
    selected: bool


# ──────────────── User ────────────────

class UserSummary(BaseSchema):
    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole

class UserRead(UserSummary):
    is_active: bool
    last_login_at: Optional[datetime]
    created_at: datetime

class UserCreate(BaseSchema):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.EDITOR

class UserUpdate(BaseSchema):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


# ──────────────── Auth ────────────────

class TokenResponse(BaseSchema):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"

class LoginRequest(BaseSchema):
    username: str
    password: str

class RefreshRequest(BaseSchema):
    refresh_token: str


# ──────────────── Audit ────────────────

class AuditLogRead(BaseSchema):
    id: uuid.UUID
    sku_id: Optional[str]
    action: AuditAction
    payload: Optional[dict]
    ip_address: Optional[str]
    occurred_at: datetime
    user: Optional[UserSummary]


# ──────────────── Analytics ────────────────

class DailyStat(BaseSchema):
    date: date
    generated: int
    approved: int
    recalled: int

class BrandStat(BaseSchema):
    brand_name: str
    total_products: int
    ai_ready: int
    approved: int
    approval_rate: float

class AnalyticsSummary(BaseSchema):
    total_products_ingested: int
    total_ai_generated: int
    total_manual_photoshoot: int
    total_approved: int
    total_recalled: int
    total_ai_rejected: int
    approval_rate: float
    total_google_api_calls: int = 0
    total_google_cost_usd: float = 0.0
    daily_trend: List[DailyStat]
    by_brand: List[BrandStat]


# ──────────────── Filters / Pagination ────────────────

class ProductFilters(BaseSchema):
    approval_date: Optional[date] = None
    season: Optional[str] = None
    brand_id: Optional[uuid.UUID] = None
    category_id: Optional[uuid.UUID] = None
    status: Optional[ProductStatus] = None
    search: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)

class PaginatedProducts(BaseSchema):
    items: List[ProductSummary]
    total: int
    page: int
    page_size: int
    pages: int


# Fix forward refs
ProductPromptRead.model_rebuild()
ProductDetail.model_rebuild()
ProductSummary.model_rebuild()
