"""
Import product data from Excel file into the local SQLite database.

Column layout expected in products.xlsx:
  <ID>                           → sku_id
  <Parent ID>                    → sibling grouping
  Markkinointinimi               → marketing_name
  Tuotekuvaus                    → description
  Materiaali                     → material_info
  Avainsanat                     → keywords (comma-separated)
  SeasonName                     → season (;-separated — first value used)
  Campaigns Linked               → campaign_name (-separated — first value used)
  Väri                           → colour
  Koko                           → size
  DC B&M Stock Balance           → dc_stock  (none/low/high)
  Helsinki DS Stock Balance      → hki_stock (none/low/high)
  Brand                          → brand_name
  <Retail Category [Node] Path>  → category hierarchy (| → " > ")
  Image1–5 Path                  → original_image_keys (URLs)
  classicDepartmentName          → classic_department_name
  opilDepartmentName             → opil_department_name
  Object Type                    → object_type

Usage:
    cd backend
    python import_excel.py [path/to/file.xlsx]

Also callable via API: POST /admin/import-excel
"""
import asyncio
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine, Base
from app.models import (
    Brand, Category, Product, ProductPrompt, PromptLibrary,
    ProductStatus, PromptType, UserRole, User,
)

DEFAULT_EXCEL_PATH = os.path.join(os.path.dirname(__file__), "data", "products.xlsx")

GENERAL_PROMPT = (
    "Create a clean, high-quality product photograph on a pure white background. "
    "The product should be centered, well-lit with soft shadows, and styled to appeal to a premium Scandinavian design aesthetic. "
    "Emphasize texture, craftsmanship, and the product's key features. "
    "Photorealistic, editorial quality, suitable for an e-commerce catalog."
)

_HKI_STOCK = {"none": 0, "low": 10, "high": 50}
_DC_STOCK   = {"none": 0, "low": 25, "high": 100}


def _col(row: dict, *names) -> str | None:
    for name in names:
        v = row.get(name)
        if v is not None and str(v).strip() not in ("", "None", "nan"):
            return str(v).strip()
    lower = {k.lower(): v for k, v in row.items()}
    for name in names:
        v = lower.get(name.lower())
        if v is not None and str(v).strip() not in ("", "None", "nan"):
            return str(v).strip()
    return None


def _season(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.split(";")[0].strip() or None


def _campaign(raw: str | None) -> str | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split("-") if p.strip()]
    return parts[0] if parts else raw.strip() or None


def _hierarchy(raw: str | None) -> str | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    return " > ".join(parts) if parts else None


def _keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [k.strip() for k in raw.replace(";", ",").split(",") if k.strip()]


def _images(row: dict) -> list[str]:
    urls = []
    for i in range(1, 6):
        v = _col(row, f"Image{i} Path", f"Image{i} path", f"image{i} path", f"Image{i}")
        if v and v.startswith("http"):
            urls.append(v)
    return urls


def _parse_rows(file_path: str) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if len(rows) < 2:
        return []

    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    return [dict(zip(headers, r)) for r in rows[1:] if any(r)]


async def import_excel(db: AsyncSession, file_path: str = DEFAULT_EXCEL_PATH) -> dict:
    """
    Import products from Excel file. Idempotent — skips existing sku_ids.
    Each row becomes its own product; rows sharing the same <Parent ID> are siblings.
    Returns counts of created items.
    """
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        raise RuntimeError("openpyxl is required: pip install openpyxl")

    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"Excel file not found: {file_path}\n"
            f"Place your products.xlsx in: backend/data/products.xlsx"
        )

    raw_rows = _parse_rows(file_path)
    if not raw_rows:
        return {"brands": 0, "categories": 0, "products": 0}

    # Group by (parent_id, colour) — one product per parent+colour combination.
    colour_groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in raw_rows:
        pid    = _col(row, "<Parent ID>", "Parent ID") or ""
        colour = (_col(row, "V\u00e4ri", "Väri", "Colour", "Color", "Vari") or "").strip()
        colour_groups[(pid, colour)].append(row)

    counts = {"brands": 0, "categories": 0, "products": 0}

    # Ensure a general prompt library entry exists
    res = await db.execute(
        select(PromptLibrary).where(
            PromptLibrary.prompt_type == PromptType.GENERAL,
            PromptLibrary.is_active == True,
        )
    )
    general_prompt_lib = res.scalar_one_or_none()
    if not general_prompt_lib:
        res2 = await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
        admin = res2.scalar_one_or_none()
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

    # Brand cache
    brand_cache: dict[str, Brand] = {}

    async def get_or_create_brand(name: str) -> Brand:
        key = name.strip()
        if key in brand_cache:
            return brand_cache[key]
        res = await db.execute(select(Brand).where(Brand.brand_name == key))
        b = res.scalar_one_or_none()
        if not b:
            b = Brand(brand_name=key)
            db.add(b)
            await db.flush()
            counts["brands"] += 1
        brand_cache[key] = b
        return b

    # Category cache
    cat_cache: dict[str, Category] = {}

    async def get_or_create_category(hierarchy: str) -> Category:
        key = hierarchy.strip()
        if key in cat_cache:
            return cat_cache[key]
        path_key = key.replace(" ", "_").upper()
        res = await db.execute(select(Category).where(Category.category_path_key == path_key))
        c = res.scalar_one_or_none()
        if not c:
            name = key.split(">")[-1].strip() if ">" in key else key
            c = Category(name=name, hierarchy=key, category_path_key=path_key)
            db.add(c)
            await db.flush()
            counts["categories"] += 1
        cat_cache[key] = c
        return c

    # One product per (parent, colour) group
    for (parent_id, colour_key), group in colour_groups.items():
        if not parent_id:
            continue

        child_skus = [
            _col(row, "<ID>", "SKU ID", "sku_id")
            for row in group
            if _col(row, "<ID>", "SKU ID", "sku_id")
        ]
        if not child_skus:
            continue

        sku_id = child_skus[0]

        res = await db.execute(select(Product).where(Product.sku_id == sku_id))
        if res.scalar_one_or_none():
            continue

        first = group[0]

        if not any(_col(row, "Image1 Path", "Image1 path", "image1 path", "Image1") for row in group):
            continue

        seen_urls: set[str] = set()
        images: list[str] = []
        for row in group:
            for url in _images(row):
                if url not in seen_urls and len(images) < 5:
                    seen_urls.add(url)
                    images.append(url)

        brand_name = _col(first, "BrandCopied", "Brand", "Brand Name")
        brand = await get_or_create_brand(brand_name) if brand_name else None

        hierarchy_raw = _hierarchy(_col(
            first,
            "<Retail Category.|Node|.Path>",
            "<Retail Category [Node] Path>",
            "Retail Category [Node] Path",
            "Retail Hierarchy",
        ))
        category = await get_or_create_category(hierarchy_raw) if hierarchy_raw else None

        hki_raw = (_col(first, "Helsinki DS Stock Balance", "Helsinki Stock Level") or "none").lower()
        dc_raw  = (_col(first, "DC B&M Stock Balance", "DC Stock Level") or "none").lower()

        object_type = _col(first, "Object Type")
        classic_dept = _col(first, "classicDepartmentName")
        opil_dept    = _col(first, "opilDepartmentName")

        if object_type == "SKU":
            department = opil_dept or classic_dept
        elif object_type == "OPILSKU":
            department = classic_dept or opil_dept
        else:
            department = classic_dept or opil_dept

        p = Product(
            sku_id=sku_id,
            brand_id=brand.id if brand else None,
            category_id=category.id if category else None,
            marketing_name=_col(first, "Markkinointinimi", "Marketing Name"),
            description=_col(first, "Tuotekuvaus", "Description"),
            material_info=_col(first, "Materiaali", "Material Info"),
            keywords=_keywords(_col(first, "Avainsanat", "Keywords")),
            season=_season(_col(first, "SeasonName", "Season")),
            campaign_name=_campaign(_col(first, "Campaigns Linked", "Campaign Name")),
            colour=_col(first, "V\u00e4ri", "Väri", "Colour", "Color", "Vari"),
            size=_col(first, "Koko", "Size"),
            dc_stock=_DC_STOCK.get(dc_raw, 0),
            hki_stock=_HKI_STOCK.get(hki_raw, 0),
            classic_department_name=classic_dept,
            opil_department_name=opil_dept,
            object_type=object_type,
            department=department,
            status=ProductStatus.PENDING_AI,
            text_approval_date=date.today(),
            original_image_keys=images,
            ai_image_keys=[],
            approved_image_keys=[],
            image_metadata={"ai": [], "original": [{"key": k, "sort": i} for i, k in enumerate(images)]},
            sibling_skus=child_skus,
            ingested_at=datetime.now(timezone.utc),
        )
        db.add(p)
        await db.flush()

        prompt = ProductPrompt(
            sku_id=sku_id,
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
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXCEL_PATH

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        try:
            result = await import_excel(db, path)
            await db.commit()
            print("Import complete:")
            for k, v in result.items():
                print(f"  {k}: {v} created")
        except Exception as e:
            await db.rollback()
            print(f"Import failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
