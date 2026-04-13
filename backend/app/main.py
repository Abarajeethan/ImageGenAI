"""FastAPI application — local dev only, SQLite + local file storage."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import engine, AsyncSessionLocal, Base
import app.models  # noqa: F401 — must be imported before create_all so all tables are registered
from app.routers import products, prompts, approvals, auth, analytics, admin

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    print(f"\nImageGen Local — {settings.environment.upper()}")
    print(f"  auth={settings.auth_mode}  storage={settings.storage_mode}  ai={settings.ai_mode}")

    # Create DB tables (models imported at top of file ensures Base.metadata is populated)
    table_names = list(Base.metadata.tables.keys())
    print(f"\nRegistered tables ({len(table_names)}): {', '.join(sorted(table_names))}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  ✓ Tables created")

    # Seed default local users
    from app.middleware.auth_local import seed_dev_users
    async with AsyncSessionLocal() as db:
        print("\nUsers:")
        await seed_dev_users(db)

    # Create local image directories
    Path(settings.local_image_dir).mkdir(parents=True, exist_ok=True)
    print(f"\nLocal images: {Path(settings.local_image_dir).resolve()}")
    print(f"\nReady at http://localhost:{settings.backend_port}")
    print(f"  Docs:  http://localhost:{settings.backend_port}/docs\n")

    yield

    await engine.dispose()


app = FastAPI(
    title="ImageGen Local",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Serve local images ────────────────────────────────────────────────────────
local_dir = Path(settings.local_image_dir)
local_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/images", StaticFiles(directory=str(local_dir)), name="images")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/api/auth")
app.include_router(products.router,  prefix="/api/products")
app.include_router(prompts.router,   prefix="/api")
app.include_router(approvals.router, prefix="/api")
app.include_router(analytics.router, prefix="/api/analytics")
app.include_router(admin.router,     prefix="/api/admin")


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "environment": settings.environment,
        "ai_mode": settings.ai_mode,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    import traceback
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": str(exc)})
