from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models import PromptLibrary, ProductPrompt, Product, PromptType, User, Category
import uuid


def _detect_audience(hierarchy: str) -> str | None:
    """
    Detect Male / Female / Children from the retail hierarchy path.
    Handles Finnish and English segment names.
    Returns a human-readable audience string or None.
    """
    h = hierarchy.lower()
    segments = [s.strip() for s in h.replace(">", "|").split("|")]

    CHILD_KEYWORDS  = {"lapset", "lasten", "children", "child", "kids", "junior",
                       "pojat", "tytöt", "poikien", "tyttöjen", "pojille", "tytöille",
                       "baby", "vauva", "vauvoille"}
    MALE_KEYWORDS   = {"miehet", "miesten", "miehille", "men", "male", "herr", "man",
                       "boys", "pojat", "poikien"}
    FEMALE_KEYWORDS = {"naiset", "naisten", "naisille", "women", "female", "dam",
                       "woman", "ladies", "girls", "tytöt", "tyttöjen"}

    for seg in segments:
        if seg in CHILD_KEYWORDS:
            return "Children"
    for seg in segments:
        if seg in MALE_KEYWORDS:
            return "Men"
    for seg in segments:
        if seg in FEMALE_KEYWORDS:
            return "Women"
    return None


async def build_product_prompt(db: AsyncSession, product: Product) -> str:
    """
    Compile the full AI prompt for a product:
    1. General prompt (always)
    2. Brand-specific prompt (if exists)
    3. Product details injected at the end
    """
    # 1. General prompt
    general_result = await db.execute(
        select(PromptLibrary).where(
            and_(
                PromptLibrary.prompt_type == PromptType.GENERAL,
                PromptLibrary.is_active == True,
                PromptLibrary.brand_id == None,
            )
        )
    )
    general_prompt = general_result.scalar_one_or_none()
    general_text = general_prompt.prompt_text if general_prompt else ""

    # 2. Brand-specific prompt
    brand_text = ""
    brand_prompt_id = None
    if product.brand_id:
        # Try to find a department-specific brand prompt first, fall back to brand-only prompt
        brand_result = await db.execute(
            select(PromptLibrary).where(
                and_(
                    PromptLibrary.prompt_type == PromptType.BRAND,
                    PromptLibrary.brand_id == product.brand_id,
                    PromptLibrary.department == product.department,
                    PromptLibrary.is_active == True,
                )
            )
        )
        brand_prompt = brand_result.scalar_one_or_none()
        if not brand_prompt:
            # Fall back to brand prompt without department scope
            brand_result = await db.execute(
                select(PromptLibrary).where(
                    and_(
                        PromptLibrary.prompt_type == PromptType.BRAND,
                        PromptLibrary.brand_id == product.brand_id,
                        PromptLibrary.department == None,
                        PromptLibrary.is_active == True,
                    )
                )
            )
        brand_prompt = brand_result.scalar_one_or_none()
        if brand_prompt:
            brand_text = brand_prompt.prompt_text
            brand_prompt_id = brand_prompt.id

    # 3. Product context
    product_context_parts = []
    if product.marketing_name:
        product_context_parts.append(f"Product name: {product.marketing_name}")
    if product.description:
        product_context_parts.append(f"Description: {product.description}")
    if product.material_info:
        product_context_parts.append(f"Material: {product.material_info}")
    if product.keywords:
        product_context_parts.append(f"Keywords: {', '.join(product.keywords)}")
    if product.campaign_name:
        product_context_parts.append(f"Campaign: {product.campaign_name}")

    # Audience from retail hierarchy
    if product.category_id:
        cat_result = await db.execute(
            select(Category).where(Category.id == product.category_id)
        )
        category = cat_result.scalar_one_or_none()
        if category and category.hierarchy:
            audience = _detect_audience(category.hierarchy)
            if audience:
                product_context_parts.append(f"Target audience: {audience}")
            product_context_parts.append(f"Retail category: {category.hierarchy}")

    product_context = "\n".join(product_context_parts)

    # Assemble
    parts = [p for p in [general_text, brand_text, product_context] if p]
    full_prompt = "\n\n".join(parts)

    return full_prompt, general_prompt.id if general_prompt else None, brand_prompt_id


async def get_or_create_product_prompt(
    db: AsyncSession,
    product: Product,
    user_id: Optional[uuid.UUID] = None,
) -> ProductPrompt:
    """Get current prompt for product or create a new one."""
    # Check for existing current prompt
    result = await db.execute(
        select(ProductPrompt).where(
            and_(ProductPrompt.sku_id == product.sku_id, ProductPrompt.is_current == True)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    # Build new prompt
    prompt_text, general_id, brand_id = await build_product_prompt(db, product)

    new_prompt = ProductPrompt(
        sku_id=product.sku_id,
        prompt_text=prompt_text,
        general_prompt_id=general_id,
        brand_prompt_id=brand_id,
        is_override=False,
        is_current=True,
        created_by_user_id=user_id,
    )
    db.add(new_prompt)
    await db.flush()
    return new_prompt


async def update_product_prompt(
    db: AsyncSession,
    sku_id: str,
    new_prompt_text: str,
    user_id: uuid.UUID,
) -> ProductPrompt:
    """Create a new prompt version (marks old as not current)."""
    # Deactivate previous
    result = await db.execute(
        select(ProductPrompt).where(
            and_(ProductPrompt.sku_id == sku_id, ProductPrompt.is_current == True)
        )
    )
    old = result.scalar_one_or_none()
    if old:
        old.is_current = False

    new_prompt = ProductPrompt(
        sku_id=sku_id,
        prompt_text=new_prompt_text,
        is_override=True,
        is_current=True,
        created_by_user_id=user_id,
    )
    db.add(new_prompt)
    await db.flush()
    return new_prompt
