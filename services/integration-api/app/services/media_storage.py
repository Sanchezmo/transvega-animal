"""Media storage service for dog intake."""

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from app.core.config import settings
from app.core.exceptions import ValidationException


@dataclass
class MediaAsset:
    """
    Unified media asset structure.

    Attributes:
        id: Unique identifier (file hash)
        dog_id: Dog's internal ID (e.g., DOG-2026-00001)
        type: "photo" or "video"
        variant: "original", "cover", "listing_01", "listing_02", "social_square", "social_story", "social_facebook"
        path: Full filesystem path
        mime_type: MIME type (image/jpeg, video/mp4, etc.)
        width: Image width in pixels
        height: Image height in pixels
        status: "pending", "ready", "failed", "published"
    """

    id: str
    dog_id: str
    type: str  # "photo" | "video"
    variant: (
        str  # "original" | "cover" | "listing_01" | "listing_02" | "social_square" | "social_story" | "social_facebook"
    )
    path: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    duration_seconds: int | None = None
    status: str = "ready"

    def to_dict(self) -> dict:
        return asdict(self)


def get_media_root() -> Path:
    """Get the media root directory from settings or default."""
    root = getattr(settings, "DOG_MEDIA_ROOT", None)
    if root is None:
        # default to /data/dogs relative to project root
        root = os.path.join(os.path.dirname(__file__), "../../..", "data", "dogs")
    return Path(root).resolve()


def ensure_media_dirs(dog_internal_id: str) -> tuple[Path, Path, Path, Path]:
    """Ensure the directory structure for a dog exists.
    Returns (originals_dir, listing_dir, social_dir, processed_dir)

    Structure:
    /data/dogs/{dog_internal_id}/
        originals/
        listing/
            cover.jpg
            image_01.jpg
            image_02.jpg
            ...
        social/
            square.jpg
            story.jpg
            facebook.jpg
        processed/
    """
    base = get_media_root() / dog_internal_id
    originals = base / "originals"
    listing = base / "listing"
    social = base / "social"
    processed = base / "processed"
    for d in [originals, listing, social, processed]:
        d.mkdir(parents=True, exist_ok=True)
    return originals, listing, social, processed


def get_variant_dir(dog_internal_id: str, variant: str) -> Path:
    """Get the directory for a specific variant."""
    base = get_media_root() / dog_internal_id
    if variant == "original":
        return base / "originals"
    elif variant in [
        "cover",
        "listing_01",
        "listing_02",
        "listing_03",
        "listing_04",
        "listing_05",
        "listing_06",
        "listing_07",
        "listing_08",
        "listing_09",
        "listing_10",
    ]:
        return base / "listing"
    elif variant in ["social_square", "social_story", "social_facebook"]:
        return base / "social"
    elif variant == "processed":
        return base / "processed"
    else:
        # Default to originals for unknown variants
        return base / "originals"


def get_variant_filename(variant: str, ext: str) -> str:
    """Get the standard filename for a variant."""
    variant_map = {
        "original": f"original{ext}",
        "cover": "cover.jpg",
        "listing_01": "image_01.jpg",
        "listing_02": "image_02.jpg",
        "listing_03": "image_03.jpg",
        "listing_04": "image_04.jpg",
        "listing_05": "image_05.jpg",
        "listing_06": "image_06.jpg",
        "listing_07": "image_07.jpg",
        "listing_08": "image_08.jpg",
        "listing_09": "image_09.jpg",
        "listing_10": "image_10.jpg",
        "social_square": "square.jpg",
        "social_story": "story.jpg",
        "social_facebook": "facebook.jpg",
        "processed": f"processed{ext}",
    }
    return variant_map.get(variant, f"{variant}{ext}")


def save_uploaded_file(
    file_content: bytes,
    filename: str,
    dog_internal_id: str,
    variant: str = "original",
    uploaded_by: int = 1,
) -> MediaAsset:
    """Save an uploaded file with unified structure and return MediaAsset.

    Args:
        file_content: raw bytes of the file
        filename: original filename (for extension, etc.)
        dog_internal_id: the dog's internal ID (e.g., DOG-2026-00001)
        variant: one of 'original', 'cover', 'listing_01'-'listing_10', 'social_square', 'social_story', 'social_facebook', 'processed'
        uploaded_by: user ID who uploaded

    Returns:
        MediaAsset with metadata
    """
    valid_variants = [
        "original",
        "cover",
        "listing_01",
        "listing_02",
        "listing_03",
        "listing_04",
        "listing_05",
        "listing_06",
        "listing_07",
        "listing_08",
        "listing_09",
        "listing_10",
        "social_square",
        "social_story",
        "social_facebook",
        "processed",
    ]
    if variant not in valid_variants:
        raise ValidationException(f"Invalid variant: {variant}. Valid: {valid_variants}")

    # Compute SHA-256 hash
    file_hash = hashlib.sha256(file_content).hexdigest()

    # Determine file extension and mime type
    ext = Path(filename).suffix.lower()
    if ext in [".jpg", ".jpeg"]:
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    elif ext == ".mp4":
        mime_type = "video/mp4"
    else:
        mime_type = "application/octet-stream"

    # Determine media type
    if mime_type.startswith("image/"):
        media_type = "photo"
    elif mime_type.startswith("video/"):
        media_type = "video"
    else:
        media_type = "unknown"

    # Get target directory
    try:
        target_dir = get_variant_dir(dog_internal_id, variant)
    except Exception as e:
        raise ValidationException(f"Failed to prepare media directories: {e}")

    # Generate standard filename for variant
    target_filename = get_variant_filename(variant, ext)
    target_path = target_dir / target_filename

    # Write file
    try:
        with open(target_path, "wb") as f:
            f.write(file_content)
    except Exception as e:
        raise ValidationException(f"Failed to write file: {e}")

    # For images, we could extract width/height; for video, duration.
    width = None
    height = None
    duration_seconds = None
    # TODO: integrate with PIL or ffprobe if needed

    # Create MediaAsset
    asset = MediaAsset(
        id=file_hash,
        dog_id=dog_internal_id,
        type=media_type,
        variant=variant,
        path=str(target_path),
        mime_type=mime_type,
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        status="ready",
    )

    return asset


def get_media_asset(dog_internal_id: str, asset_id: str, variant: str) -> MediaAsset | None:
    """Locate a stored asset by hash and variant."""
    base = get_media_root() / dog_internal_id
    variant_dir = get_variant_dir(dog_internal_id, variant)
    if not variant_dir.exists():
        return None

    # We don't know extension; iterate files with hash as stem
    for ext in [".jpg", ".jpeg", ".png", ".mp4"]:
        candidate = variant_dir / f"{asset_id}{ext}"
        if candidate.exists():
            stat = candidate.stat()
            return MediaAsset(
                id=asset_id,
                dog_id=dog_internal_id,
                type="photo" if ext in [".jpg", ".jpeg", ".png"] else "video",
                variant=variant,
                path=str(candidate),
                mime_type="image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png" if ext == ".png" else "video/mp4",
                width=None,
                height=None,
                duration_seconds=None,
                status="ready",
            )
    return None


def list_dog_assets(dog_internal_id: str) -> list[MediaAsset]:
    """List all media assets for a dog."""
    assets = []
    base = get_media_root() / dog_internal_id
    if not base.exists():
        return assets

    for variant_dir_name in ["originals", "listing", "social", "processed"]:
        variant_dir = base / variant_dir_name
        if not variant_dir.exists():
            continue

        for file_path in variant_dir.iterdir():
            if not file_path.is_file():
                continue

            # Extract hash from filename (stem)
            asset_id = file_path.stem
            # If filename is not a hash (e.g., cover.jpg), use the filename as id
            if len(asset_id) != 64 or not all(c in "0123456789abcdef" for c in asset_id):
                asset_id = file_path.name

            ext = file_path.suffix.lower()
            mime_type = "application/octet-stream"
            if ext in [".jpg", ".jpeg"]:
                mime_type = "image/jpeg"
            elif ext == ".png":
                mime_type = "image/png"
            elif ext == ".mp4":
                mime_type = "video/mp4"

            media_type = (
                "photo" if mime_type.startswith("image/") else "video" if mime_type.startswith("video/") else "unknown"
            )

            # Determine variant from directory and filename
            if variant_dir_name == "originals":
                variant = "original"
            elif variant_dir_name == "listing":
                variant = file_path.stem  # e.g., cover, image_01, etc.
            elif variant_dir_name == "social":
                variant = file_path.stem  # e.g., square, story, facebook
            elif variant_dir_name == "processed":
                variant = "processed"
            else:
                variant = "unknown"

            assets.append(
                MediaAsset(
                    id=asset_id,
                    dog_id=dog_internal_id,
                    type=media_type,
                    variant=variant,
                    path=str(file_path),
                    mime_type=mime_type,
                    width=None,
                    height=None,
                    duration_seconds=None,
                    status="ready",
                )
            )

    return assets


def get_assets_for_publishing(dog_internal_id: str, platform: str) -> dict:
    """Get assets ready for publishing to a specific platform."""
    base = get_media_root() / dog_internal_id

    assets = {
        "cover": None,
        "photos": [],
        "social": {},
    }

    if platform == "milanuncios":
        # Cover image
        cover_path = base / "listing" / "cover.jpg"
        if cover_path.exists():
            assets["cover"] = str(cover_path)

        # Listing photos (up to 20)
        listing_dir = base / "listing"
        if listing_dir.exists():
            for i in range(1, 21):
                img_path = listing_dir / f"image_{i:02d}.jpg"
                if img_path.exists():
                    assets["photos"].append(str(img_path))

        assets["max_photos"] = 20

    elif platform in ["meta", "instagram", "facebook"]:
        # Social assets
        square_path = base / "social" / "square.jpg"
        story_path = base / "social" / "story.jpg"
        facebook_path = base / "social" / "facebook.jpg"

        if square_path.exists():
            assets["social"]["post_image"] = str(square_path)
        if story_path.exists():
            assets["social"]["story_image"] = str(story_path)
        if facebook_path.exists():
            assets["social"]["facebook_image"] = str(facebook_path)

    return assets
