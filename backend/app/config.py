from functools import lru_cache
from typing import Literal, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Environment ───────────────────────────────────────────────────────────
    environment: str = "development"

    # ── Mode switches ─────────────────────────────────────────────────────────
    auth_mode: Literal["local"] = "local"
    storage_mode: Literal["local"] = "local"
    ai_mode: Literal["mock", "gemini"] = "mock"
    queue_mode: Literal["inline"] = "inline"

    # ── Database (SQLite) ─────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./imagegen.db"

    # ── Local auth ────────────────────────────────────────────────────────────
    secret_key: str = "local-dev-secret-key-change-me-32chars!!"
    access_token_expire_minutes: int = 480
    dev_admin_email: str = "admin@example.com"
    dev_admin_password: str = "admin123"
    dev_editor_email: str = "editor@example.com"
    dev_editor_password: str = "editor123"

    # ── Local storage ─────────────────────────────────────────────────────────
    local_image_dir: str = "./local-images"
    backend_port: int = 8000

    # ── Google AI / Gemini (only when ai_mode=gemini) ────────────────────────
    # Place service-account.json in the backend/ folder, then set:
    google_service_account_file: Optional[str] = None   # e.g. "service-account.json"
    google_project_id: Optional[str] = None             # e.g. "my-gcp-project"
    google_ai_prompt_model: str = "models/gemini-2.0-flash"
    google_ai_image_model: str = "gemini-2.5-flash-preview-05-20"

    # ── App ───────────────────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:5173"
    product_lock_ttl_seconds: int = 600

    class Config:
        env_file = (".env", "../.env")
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
