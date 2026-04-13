"""
Seed development database with realistic product data.

Usage (standalone):
    cd backend
    python seed_dev_data.py

Also callable from the API via POST /admin/seed-dev-data
"""
import asyncio
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine, Base
from app.models import (
    Brand, Category, Product, ProductPrompt, PromptLibrary,
    ProductStatus, PromptType, UserRole, User,
)


BRANDS = [
    {"brand_name": "Marimekko"},
    {"brand_name": "Iittala"},
    {"brand_name": "Artek"},
]

CATEGORIES = [
    {"name": "Home & Living",         "hierarchy": "Home > Living",               "category_path_key": "CAT-HOME-001"},
    {"name": "Clothing & Fashion",    "hierarchy": "Clothing > Women > Dresses",   "category_path_key": "CAT-CLTH-001"},
    {"name": "Design Accessories",    "hierarchy": "Accessories > Design",         "category_path_key": "CAT-ACCS-001"},
]

GENERAL_PROMPT = (
    "Create a clean, high-quality product photograph on a pure white background. "
    "The product should be centered, well-lit with soft shadows, and styled to appeal to a premium Scandinavian design aesthetic. "
    "Emphasize texture, craftsmanship, and the product's key features. "
    "Photorealistic, editorial quality, suitable for an e-commerce catalog."
)

PRODUCTS = [
    # Marimekko — Home & Living
    {"sku_id": "SKU-MARI-001", "brand": "Marimekko", "cat": "Home & Living",      "name": "Unikko Tote Bag Large",           "season": "SS25", "desc": "Iconic poppy print canvas tote in bold red and white.", "material": "100% organic cotton canvas", "keywords": ["tote", "canvas", "unikko", "poppy"], "dc_stock": 142, "hki_stock": 38},
    {"sku_id": "SKU-MARI-002", "brand": "Marimekko", "cat": "Home & Living",      "name": "Siirtolapuutarha Mug 400ml",      "season": "SS25", "desc": "Stoneware mug with the charming garden print.", "material": "Stoneware", "keywords": ["mug", "stoneware", "siirtolapuutarha"], "dc_stock": 89, "hki_stock": 21},
    {"sku_id": "SKU-MARI-003", "brand": "Marimekko", "cat": "Clothing & Fashion", "name": "Jokapoika Shirt Dress",           "season": "AW25", "desc": "Classic stripe shirt dress in navy and white cotton.", "material": "100% cotton", "keywords": ["dress", "stripe", "jokapoika"], "dc_stock": 56, "hki_stock": 12},
    {"sku_id": "SKU-MARI-004", "brand": "Marimekko", "cat": "Clothing & Fashion", "name": "Tasaraita Midi Dress",            "season": "SS26", "desc": "Signature stripe midi dress in organic cotton jersey.", "material": "95% organic cotton, 5% elastane", "keywords": ["dress", "midi", "tasaraita", "stripe"], "dc_stock": 73, "hki_stock": 19},
    {"sku_id": "SKU-MARI-005", "brand": "Marimekko", "cat": "Design Accessories", "name": "Unikko Enamel Pin Set",           "season": "AW25", "desc": "Set of 3 enamel pins featuring iconic Marimekko prints.", "material": "Enamel on zinc alloy", "keywords": ["pin", "enamel", "unikko", "accessories"], "dc_stock": 210, "hki_stock": 45},

    # Iittala — Home & Living
    {"sku_id": "SKU-IITT-001", "brand": "Iittala", "cat": "Home & Living",        "name": "Taika Dinner Plate 27cm",         "season": "SS25", "desc": "White porcelain dinner plate with whimsical forest creatures.", "material": "Porcelain", "keywords": ["plate", "taika", "porcelain", "dinner"], "dc_stock": 96, "hki_stock": 24},
    {"sku_id": "SKU-IITT-002", "brand": "Iittala", "cat": "Home & Living",        "name": "Teema Bowl 21cm White",           "season": "SS25", "desc": "Timeless minimalist bowl in pure white porcelain.", "material": "Porcelain", "keywords": ["bowl", "teema", "white", "minimalist"], "dc_stock": 134, "hki_stock": 33},
    {"sku_id": "SKU-IITT-003", "brand": "Iittala", "cat": "Home & Living",        "name": "Aalto Vase 160mm Sea Blue",       "season": "AW25", "desc": "Iconic wave-shaped vase designed by Alvar Aalto in sea blue glass.", "material": "Mouth-blown glass", "keywords": ["vase", "aalto", "glass", "blue"], "dc_stock": 47, "hki_stock": 11},
    {"sku_id": "SKU-IITT-004", "brand": "Iittala", "cat": "Design Accessories",   "name": "Kastehelmi Candleholder Smoke",   "season": "SS26", "desc": "Dewdrop-textured glass candleholder in smoky grey.", "material": "Mouth-blown glass", "keywords": ["candleholder", "kastehelmi", "glass", "smoke"], "dc_stock": 78, "hki_stock": 18},
    {"sku_id": "SKU-IITT-005", "brand": "Iittala", "cat": "Home & Living",        "name": "Essence Wine Glass 2-pack",       "season": "AW25", "desc": "Elegant crystal wine glasses with a long, slender silhouette.", "material": "Crystal glass", "keywords": ["wine", "glass", "crystal", "essence"], "dc_stock": 115, "hki_stock": 27},

    # Artek — Design Accessories & Home
    {"sku_id": "SKU-ARTE-001", "brand": "Artek", "cat": "Home & Living",          "name": "Stool 60 Natural Lacquer",        "season": "SS25", "desc": "Iconic three-legged stool designed by Alvar Aalto in natural lacquered birch.", "material": "Solid birch", "keywords": ["stool", "artek", "aalto", "birch"], "dc_stock": 23, "hki_stock": 6},
    {"sku_id": "SKU-ARTE-002", "brand": "Artek", "cat": "Home & Living",          "name": "Table 81C Natural Lacquer",       "season": "AW25", "desc": "Elegant side table with L-shaped birch legs and white laminate top.", "material": "Birch, laminate", "keywords": ["table", "side", "birch", "aalto"], "dc_stock": 14, "hki_stock": 3},
    {"sku_id": "SKU-ARTE-003", "brand": "Artek", "cat": "Design Accessories",     "name": "Aalto Tray 455mm Natural",        "season": "SS26", "desc": "Wave-edged birch tray inspired by the bentwood technique.", "material": "Birch plywood", "keywords": ["tray", "birch", "wave", "serving"], "dc_stock": 67, "hki_stock": 15},
    {"sku_id": "SKU-ARTE-004", "brand": "Artek", "cat": "Home & Living",          "name": "Siena Blanket White/Natural",     "season": "AW25", "desc": "Warm woolen blanket in classic striped pattern, woven in Finland.", "material": "80% wool, 20% cotton", "keywords": ["blanket", "wool", "siena", "throw"], "dc_stock": 31, "hki_stock": 8},
    {"sku_id": "SKU-ARTE-005", "brand": "Artek", "cat": "Design Accessories",     "name": "Pirkka Cutting Board Small",      "season": "SS25", "desc": "Traditional Finnish pine cutting board with minimal geometric form.", "material": "Pine wood", "keywords": ["cutting board", "pine", "kitchen", "pirkka"], "dc_stock": 88, "hki_stock": 22},
]


async def seed_dev_data(db: AsyncSession) -> dict:
    """
    Seed brands, categories, products and prompts.
    Idempotent — skips items that already exist.
    Returns a dict with counts of created items.
    """
    counts = {"brands": 0, "categories": 0, "products": 0, "prompts": 0}

    # ── Brands ────────────────────────────────────────────────────
    brand_map: dict[str, Brand] = {}
    for bd in BRANDS:
        res = await db.execute(select(Brand).where(Brand.brand_name == bd["brand_name"]))
        existing = res.scalar_one_or_none()
        if existing:
            brand_map[bd["brand_name"]] = existing
        else:
            b = Brand(**bd)
            db.add(b)
            await db.flush()
            brand_map[bd["brand_name"]] = b
            counts["brands"] += 1

    # ── Categories ────────────────────────────────────────────────
    cat_map: dict[str, Category] = {}
    for cd in CATEGORIES:
        res = await db.execute(select(Category).where(Category.category_path_key == cd["category_path_key"]))
        existing = res.scalar_one_or_none()
        if existing:
            cat_map[cd["name"]] = existing
        else:
            c = Category(**cd)
            db.add(c)
            await db.flush()
            cat_map[cd["name"]] = c
            counts["categories"] += 1

    # ── General prompt library entry ─────────────────────────────
    res = await db.execute(
        select(PromptLibrary).where(
            PromptLibrary.prompt_type == PromptType.GENERAL,
            PromptLibrary.is_active == True,
        )
    )
    general_prompt_lib = res.scalar_one_or_none()
    if not general_prompt_lib:
        # Find admin user for created_by
        res = await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
        admin = res.scalar_one_or_none()

        general_prompt_lib = PromptLibrary(
            prompt_type=PromptType.GENERAL,
            prompt_text=GENERAL_PROMPT,
            version=1,
            is_active=True,
            description="Default product photography prompt",
            created_by_user_id=admin.id if admin else None,
        )
        db.add(general_prompt_lib)
        await db.flush()
        counts["prompts"] += 1

    # ── Products + ProductPrompts ──────────────────────────────────
    for pd in PRODUCTS:
        res = await db.execute(select(Product).where(Product.sku_id == pd["sku_id"]))
        if res.scalar_one_or_none():
            continue  # already exists — skip

        brand   = brand_map.get(pd["brand"])
        cat     = cat_map.get(pd["cat"])

        p = Product(
            sku_id=pd["sku_id"],
            brand_id=brand.id if brand else None,
            category_id=cat.id if cat else None,
            marketing_name=pd["name"],
            description=pd["desc"],
            material_info=pd["material"],
            keywords=pd["keywords"],
            season=pd["season"],
            dc_stock=pd["dc_stock"],
            hki_stock=pd["hki_stock"],
            status=ProductStatus.PENDING_AI,
            text_approval_date=date(2025, 1, 15),
            original_image_keys=[],
            ai_image_keys=[],
            approved_image_keys=[],
            image_metadata={"ai": [], "original": []},
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(p)
        await db.flush()

        # Create a ProductPrompt (required for regenerate endpoint)
        prompt = ProductPrompt(
            sku_id=pd["sku_id"],
            prompt_text=GENERAL_PROMPT,
            general_prompt_id=general_prompt_lib.id,
            is_override=False,
            is_current=True,
        )
        db.add(prompt)
        counts["products"] += 1

    await db.flush()
    return counts


async def main():
    """Run seed from command line."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        try:
            result = await seed_dev_data(db)
            await db.commit()
            print("✅ Seed complete:")
            for k, v in result.items():
                print(f"   {k}: {v} created")
        except Exception as e:
            await db.rollback()
            print(f"❌ Seed failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
