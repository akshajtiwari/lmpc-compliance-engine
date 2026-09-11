"""Optional scan metadata and client-reported image-quality validation.

The quality measurements are advisory — the server never trusts them for a verdict —
but they are persisted per image so dashboards can show what the phone saw."""
from __future__ import annotations
from typing import Any
from urllib.parse import urlsplit

from ..api.errors import ApiError

BUYER_TYPES = {"RETAIL", "INDUSTRIAL", "INSTITUTIONAL"}
PACKAGE_SHAPES = {"RECTANGULAR", "CYLINDRICAL", "IRREGULAR"}
SCALE_TYPES = {"ISO_ID1_CARD", "APRILTAG_36H11", "MANUAL_DIMENSIONS", "NONE"}
QUALITY_KEYS = {"source", "sharpness", "mean_luma", "glare_fraction", "warnings"}


def validate_metadata(*, mode: str, buyer_type: str, package_shape: str,
                      scale_reference: dict, dimensions: dict, flags: dict,
                      geo: dict, ecommerce: dict) -> dict[str, Any]:
    if buyer_type not in BUYER_TYPES:
        raise ApiError("E_VALIDATION", f"unsupported buyer_type: {buyer_type}")
    if package_shape not in PACKAGE_SHAPES:
        raise ApiError("E_VALIDATION", f"unsupported package_shape: {package_shape}")
    scale_type = scale_reference.get("type", "NONE")
    if scale_type not in SCALE_TYPES:
        raise ApiError("E_VALIDATION", f"unsupported scale reference: {scale_type}")
    numbers = {key: _positive_number(dimensions, key)
               for key in ("h_cm", "w_cm", "capacity_cm3")}
    if (numbers["h_cm"] is None) != (numbers["w_cm"] is None):
        raise ApiError("E_VALIDATION", "dimensions require both h_cm and w_cm")
    expected_flags = {"is_imported", "is_molded", "other_law_requires_same_info"}
    if any(key not in expected_flags or not isinstance(value, bool)
           for key, value in flags.items()):
        raise ApiError("E_VALIDATION", "flags contain an unknown or non-boolean value")
    lat, lng = geo.get("lat"), geo.get("lng")
    numeric_geo = all(not isinstance(value, bool) and isinstance(value, (int, float))
                      for value in (lat, lng) if value is not None)
    if (lat is None) != (lng is None) or not numeric_geo \
            or (lat is not None and not (-90 <= lat <= 90)) \
            or (lng is not None and not (-180 <= lng <= 180)):
        raise ApiError("E_VALIDATION", "geo requires a valid latitude and longitude")
    listing_text = ecommerce.get("listing_text")
    listing_url = ecommerce.get("url")
    if mode == "ECOMMERCE_LISTING" and not (
            isinstance(listing_text, str) and listing_text.strip()):
        raise ApiError("E_VALIDATION", "ecommerce.listing_text is required in listing mode")
    if any(value is not None and not isinstance(value, str)
           for value in (listing_url, listing_text)):
        raise ApiError("E_VALIDATION", "ecommerce url and listing_text must be strings")
    if isinstance(listing_text, str) and len(listing_text) > 50_000:
        raise ApiError("E_VALIDATION", "ecommerce.listing_text exceeds 50000 characters")
    if isinstance(listing_url, str) and listing_url:
        parsed_url = urlsplit(listing_url.strip())
        if (len(listing_url) > 2048 or parsed_url.scheme not in {"http", "https"}
                or not parsed_url.hostname or parsed_url.username is not None
                or parsed_url.password is not None):
            raise ApiError("E_VALIDATION", "ecommerce.url must be an HTTP(S) URL")
    return {
        "buyer_type": buyer_type, "package_shape": package_shape,
        "scale_reference_type": scale_type,
        "scale_reference_data": scale_reference.get("data"),
        "pdp_h_cm": numbers["h_cm"], "pdp_w_cm": numbers["w_cm"],
        "capacity_cm3": numbers["capacity_cm3"],
        "is_imported": flags.get("is_imported", False),
        "is_molded": flags.get("is_molded", False),
        "other_law_requires_same_info": flags.get("other_law_requires_same_info", False),
        "geo_lat": lat, "geo_lng": lng,
        "ecommerce_url": listing_url.strip() if isinstance(listing_url, str) else None,
        "ecommerce_text": listing_text.strip() if isinstance(listing_text, str) else None,
    }


def validate_image_quality(items: list[dict] | None, n_images: int) -> list[dict | None]:
    """Validate client-reported capture quality for each image (plan §8 item 8).

    The measurements are advisory — the server never trusts them for a verdict —
    but they are persisted per image so dashboards can show what the phone saw.
    """
    if items is None:
        return [None] * n_images
    if len(items) != n_images:
        raise ApiError("E_VALIDATION", "one image_quality entry is required per image")
    validated: list[dict | None] = []
    for item in items:
        if item is None or not isinstance(item, dict):
            raise ApiError("E_VALIDATION", "each image_quality entry must be an object")
        unknown = set(item) - QUALITY_KEYS
        if unknown:
            raise ApiError("E_VALIDATION", f"image_quality has unknown keys: {sorted(unknown)}")
        source = item.get("source")
        if source is not None and source not in ("CAMERA", "GALLERY"):
            raise ApiError("E_VALIDATION", "image_quality.source must be CAMERA or GALLERY")
        numbers = {key: item.get(key) for key in
                   ("sharpness", "mean_luma", "glare_fraction")}
        for key, value in numbers.items():
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool) \
                    or value != value or value in (float("inf"), float("-inf")):
                raise ApiError("E_VALIDATION", f"image_quality.{key} must be a number")
        if numbers["sharpness"] is not None and numbers["sharpness"] < 0:
            raise ApiError("E_VALIDATION", "image_quality.sharpness must not be negative")
        if numbers["mean_luma"] is not None and not 0 <= numbers["mean_luma"] <= 255:
            raise ApiError("E_VALIDATION", "image_quality.mean_luma must be within 0..255")
        if numbers["glare_fraction"] is not None and not 0 <= numbers["glare_fraction"] <= 1:
            raise ApiError("E_VALIDATION", "image_quality.glare_fraction must be within 0..1")
        warnings = item.get("warnings", [])
        if not isinstance(warnings, list) or any(
                not isinstance(text, str) or not text or len(text) > 200
                for text in warnings) or len(warnings) > 8:
            raise ApiError("E_VALIDATION", "image_quality.warnings must be at most 8 short strings")
        validated.append({"source": source, **numbers, "warnings": warnings})
    return validated


def _positive_number(values: dict, key: str) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ApiError("E_VALIDATION", f"dimensions.{key} must be a positive number")
    return float(value)
