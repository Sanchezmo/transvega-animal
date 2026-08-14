"""Media storage service for dog intake."""

import hashlib
import os
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import ValidationException


def get_media_root() -> Path:
    """Get the media root directory from settings or default."""
    root = getattr(settings, "DOG_MEDIA_ROOT", None)
    if root is None:
        # default to /data/dogs relative to project root
        root = os.path.join(os.path.dirname(__file__), "../../..", "data", "dogs")
    return Path(root).resolve()


def ensure_media_dirs(dog_internal_id: str) -> tuple[Path, Path, Path, Path]:
    """Ensure the directory structure for a dog exists.
    Returns (original_dir, processed_dir, social_dir, listing_dir)
    """
    base = get_media_root() / dog_internal_id
    original = base / "original"
    processed = base / "processed"
    social = base / "social"
    listing = base / "listing"
    for d in [original, processed, social, listing]:
        d.mkdir(parents=True, exist_ok=True)
    return original, processed, social, listing


def save_uploaded_file(
    file_content: bytes,
    filename: str,
    dog_internal_id: str,
    purpose: str = "original",
    uploaded_by: int = 1,
) -> dict:
    """Save an uploaded file, compute hash, and return media metadata.

    Args:
        file_content: raw bytes of the file
        filename: original filename (for extension, etc.)
        dog_internal_id: the dog's internal ID (e.g., DOG-2026-00001)
        purpose: one of 'original', 'processed', 'social', 'listing'
        uploaded_by: user ID who uploaded

    Returns:
        dict suitable for DogMediaCreate
    """
    if purpose not in ["original", "processed", "social", "listing"]:
        raise ValidationException(f"Invalid purpose: {purpose}")

    # Compute SHA-256 hash
    file_hash = hashlib.sha256(file_content).hexdigest()

    # Determine file extension and mime type (simple)
    ext = Path(filename).suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    elif ext == ".mp4":
        mime_type = "video/mp4"
    else:
        # default
        mime_type = "application/octet-stream"

    # Determine media type
    if mime_type.startswith("image/"):
        media_type = "photo"
    elif mime_type.startswith("video/"):
        media_type = "video"
    else:
        media_type = "unknown"  # but we'll restrict later

    # Get directories
    try:
        original_dir, processed_dir, social_dir, listing_dir = ensure_media_dirs(
            dog_internal_id
        )
    except Exception as e:
        raise ValidationException(f"Failed to prepare media directories: {e}")

    # Choose target directory based on purpose
    target_dir = {
        "original": original_dir,
        "processed": processed_dir,
        "social": social_dir,
        "listing": listing_dir,
    }[purpose]

    # Generate a safe filename: hash + original extension (or keep original name?)
    # To avoid collisions, use hash as base name
    safe_filename = f"{file_hash}{ext}"
    target_path = target_dir / safe_filename

    # Write file
    try:
        with open(target_path, "wb") as f:
            f.write(file_content)
    except Exception as e:
        raise ValidationException(f"Failed to write file: {e}")

    # For images, we could extract width/height; for video, duration.
    # For now, leave as None; could be filled by a separate processing job.
    width = None
    height = None
    duration_seconds = None
    # TODO: integrate with PIL or ffprobe if needed

    # Return metadata for DogMediaCreate
    return {
        "file_path": str(target_path),
        "file_hash": file_hash,
        "mime_type": mime_type,
        "width": width,
        "height": height,
        "duration_seconds": duration_seconds,
        "media_type": media_type,
        "purpose": purpose,
        "dog_id": 0,  # will be set later after dog ID known
        "uploaded_by": uploaded_by,
    }


def get_media_file_path(
    dog_internal_id: str, file_hash: str, purpose: str
) -> Path | None:
    """Locate a stored file by hash and purpose."""
    base = get_media_root() / dog_internal_id
    purpose_dir = {
        "original": base / "original",
        "processed": base / "processed",
        "social": base / "social",
        "listing": base / "listing",
    }.get(purpose)
    if not purpose_dir or not purpose_dir.exists():
        return None
    # We don't know extension; iterate files with hash as stem
    for ext in [".jpg", ".jpeg", ".png", ".mp4"]:
        candidate = purpose_dir / f"{file_hash}{ext}"
        if candidate.exists():
            return candidate
    return None
