"""Security validation and metadata extraction for uploaded evidence images."""
from __future__ import annotations

import hashlib
import io
import re
import warnings
from dataclasses import dataclass, replace

from PIL import Image, UnidentifiedImageError

from ..api.errors import ApiError

_DIGEST = re.compile(r"[0-9a-f]{64}")
_MIME = {
    "JPEG": {"image/jpeg", "image/jpg"},
    "PNG": {"image/png"},
    "HEIF": {"image/heic", "image/heif"},
}
_EXT = {"JPEG": "jpg", "PNG": "png", "HEIF": "heic"}


@dataclass(frozen=True)
class EvidenceImage:
    filename: str
    media_type: str
    data: bytes
    sha256: str
    width_px: int
    height_px: int
    storage_key: str
    panel_label: str = ""
    max_edge_used: int | None = None

    def on_panel(self, panel: str) -> "EvidenceImage":
        return replace(self, panel_label=panel)

    def without_data(self) -> "EvidenceImage":
        return replace(self, data=b"")

    def with_max_edge(self, value: int) -> "EvidenceImage":
        return replace(self, max_edge_used=value)


def validate_image(*, data: bytes, filename: str, media_type: str,
                   expected_sha256: str, max_bytes: int,
                   max_pixels: int) -> EvidenceImage:
    if len(data) > max_bytes:
        raise ApiError("E_IMAGE_TOO_LARGE", f"{filename} exceeds the image cap")
    expected = expected_sha256.strip().lower()
    if not _DIGEST.fullmatch(expected):
        raise ApiError("E_VALIDATION", f"{filename} has an invalid SHA-256")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ApiError("E_VALIDATION", f"SHA-256 mismatch for {filename}")

    kind = _magic_kind(data)
    claimed = media_type.lower().split(";", 1)[0].strip()
    if kind is None or claimed not in _MIME[kind]:
        raise ApiError("E_UNSUPPORTED_MEDIA", f"{filename} MIME and file signature disagree")
    width, height = _decode_dimensions(data, kind, filename)
    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise ApiError("E_UNSUPPORTED_MEDIA", f"{filename} exceeds the pixel cap")
    key = f"images/{digest[:2]}/{digest}.{_EXT[kind]}"
    return EvidenceImage(filename, claimed, data, digest, width, height, key)


def _magic_kind(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brands = data[8:16]
        if any(brand in brands for brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1")):
            return "HEIF"
    return None


def _decode_dimensions(data: bytes, kind: str, filename: str) -> tuple[int, int]:
    if kind == "HEIF":
        try:
            import pillow_heif

            pillow_heif.register_heif_opener()
        except ImportError as exc:
            raise ApiError("E_UNSUPPORTED_MEDIA", "HEIC decoder is not installed") from exc
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != kind:
                    raise ApiError("E_UNSUPPORTED_MEDIA", f"{filename} has the wrong image format")
                size = image.size
                image.verify()
                return size
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ApiError("E_UNSUPPORTED_MEDIA", f"{filename} is not a valid image") from exc
