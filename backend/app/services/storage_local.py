"""
Local storage service — replaces S3 for dev.
Images saved to LOCAL_IMAGE_DIR and served as static files by FastAPI.
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def _image_dir() -> Path:
    d = Path(settings.local_image_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _date_prefix() -> str:
    return datetime.now().strftime("%m-%d-%Y")


def upload_ai_image(
    image_bytes: bytes,
    sku_id: str,
    session_id: str,
    image_index: int,
    content_type: str = "image/jpeg",
) -> str:
    folder = _image_dir() / "generatedImage" / _date_prefix() / sku_id / session_id
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{image_index:02d}.jpg"
    (folder / filename).write_bytes(image_bytes)
    return f"generatedImage/{_date_prefix()}/{sku_id}/{session_id}/{filename}"


def get_presigned_url(key: str, expiry_seconds: int = 86400) -> str:
    if key and (key.startswith("https://") or key.startswith("http://")):
        return key
    base = f"http://localhost:{settings.backend_port}/static/images"
    return f"{base}/{key}"


def presign_keys(keys: list[str], expiry_seconds: int = 86400) -> list[str]:
    return [get_presigned_url(k, expiry_seconds) for k in keys]


def move_to_rejected(s3_key: str) -> str:
    """Move image from generatedImage/ to rejectedImage/{MM-DD-YYYY}/."""
    src = _image_dir() / s3_key
    # Determine relative sub-path
    if s3_key.startswith("generatedImage/"):
        parts = s3_key.split("/", 2)
        rel = parts[2] if len(parts) > 2 else s3_key
    elif s3_key.startswith("ai/"):
        rel = s3_key[3:]
    else:
        rel = s3_key
    rejected_key = f"rejectedImage/{_date_prefix()}/{rel}"
    dst = _image_dir() / rejected_key
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dst))
    return rejected_key


def move_to_approved(s3_key: str, image_file_path: str, image_file_name: str) -> str:
    """Mirror the S3 move for local dev — reorganise under ImageFilePath."""
    src = _image_dir() / s3_key
    new_key = f"{image_file_path}/{image_file_name}"
    dst = _image_dir() / new_key
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.move(str(src), str(dst))
    return new_key


def get_image_bytes(key: str) -> bytes:
    """Read image bytes directly from local filesystem."""
    filepath = _image_dir() / key
    return filepath.read_bytes()


def delete_object(key: str) -> None:
    filepath = _image_dir() / key
    if filepath.exists():
        filepath.unlink()
