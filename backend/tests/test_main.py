"""
Backend test suite.
Run: pytest tests/ -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.database import Base, get_db
from app.models import Brand, Category, Product, PromptLibrary, User, PromptType, ProductStatus, UserRole

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DB_URL, echo=False, connect_args={"check_same_thread": False})
TestSession = async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session) -> User:
    user = User(
        email="test@example.com",
        full_name="Test User",
        role=UserRole.EDITOR,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_brand(db_session) -> Brand:
    brand = Brand(brand_name="Test Brand", ai_forbidden=False)
    db_session.add(brand)
    await db_session.commit()
    return brand


@pytest_asyncio.fixture
async def test_product(db_session, test_brand) -> Product:
    from datetime import date
    product = Product(
        sku_id="TEST-001",
        brand_id=test_brand.id,
        marketing_name="Test Product",
        description="A great test product",
        material_info="100% Cotton",
        keywords=["test", "product"],
        season="SS25",
        status=ProductStatus.AI_READY,
        text_approval_date=date.today(),
    )
    db_session.add(product)
    await db_session.commit()
    return product


# ─── Health check ────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ─── Products ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_products_unauthorized(client):
    response = await client.get("/products")
    assert response.status_code == 403  # No Bearer token


@pytest.mark.asyncio
async def test_product_model(db_session, test_product):
    """Test product was created correctly."""
    from sqlalchemy import select
    result = await db_session.execute(select(Product).where(Product.sku_id == "TEST-001"))
    p = result.scalar_one()
    assert p.marketing_name == "Test Product"
    assert p.season == "SS25"
    assert p.status == ProductStatus.AI_READY


# ─── Brand exclusion ─────────────────────────────────────

@pytest.mark.asyncio
async def test_ai_forbidden_brand(db_session):
    """Brands with ai_forbidden=True should be excluded."""
    forbidden_brand = Brand(brand_name="Forbidden Brand", ai_forbidden=True)
    allowed_brand = Brand(brand_name="Allowed Brand", ai_forbidden=False)
    db_session.add_all([forbidden_brand, allowed_brand])
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(Brand).where(Brand.ai_forbidden == False))
    allowed = result.scalars().all()
    brand_names = [b.brand_name for b in allowed]
    assert "Forbidden Brand" not in brand_names
    assert "Allowed Brand" in brand_names


# ─── Prompt library ──────────────────────────────────────

@pytest.mark.asyncio
async def test_prompt_library_creation(db_session):
    general = PromptLibrary(
        prompt_type=PromptType.GENERAL,
        prompt_text="Generate a high-quality fashion image.",
        version=1,
        is_active=True,
    )
    db_session.add(general)
    await db_session.commit()

    from sqlalchemy import select, and_
    result = await db_session.execute(
        select(PromptLibrary).where(
            and_(PromptLibrary.prompt_type == PromptType.GENERAL, PromptLibrary.is_active == True)
        )
    )
    p = result.scalar_one()
    assert p.prompt_text == "Generate a high-quality fashion image."
    assert p.version == 1


# ─── Prompt building ─────────────────────────────────────

@pytest.mark.asyncio
async def test_build_product_prompt(db_session, test_product):
    # Add general prompt
    general = PromptLibrary(
        prompt_type=PromptType.GENERAL,
        prompt_text="Generate a high-quality fashion model image.",
        version=1,
        is_active=True,
    )
    db_session.add(general)
    await db_session.commit()

    from app.services.prompt_service import build_product_prompt
    prompt_text, gen_id, brand_id = await build_product_prompt(db_session, test_product)

    assert "Generate a high-quality fashion model image." in prompt_text
    assert "Test Product" in prompt_text
    assert "100% Cotton" in prompt_text
    assert gen_id is not None


# ─── Image status transitions ────────────────────────────

@pytest.mark.asyncio
async def test_product_status_flow(db_session, test_product):
    """Test product status transitions are valid."""
    assert test_product.status == ProductStatus.AI_READY

    test_product.status = ProductStatus.USER_SELECTED
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(Product).where(Product.sku_id == "TEST-001"))
    p = result.scalar_one()
    assert p.status == ProductStatus.USER_SELECTED


# ─── Audit log ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_log_creation(db_session, test_user, test_product):
    from app.services.audit_service import log_action
    from app.models import AuditAction

    entry = await log_action(
        db_session,
        AuditAction.IMAGE_APPROVED,
        user_id=test_user.id,
        sku_id=test_product.sku_id,
        payload={"test": True},
    )
    await db_session.commit()

    from sqlalchemy import select
    from app.models import AuditLog
    result = await db_session.execute(select(AuditLog).where(AuditLog.id == entry.id))
    log = result.scalar_one()
    assert log.action == AuditAction.IMAGE_APPROVED
    assert log.payload == {"test": True}
