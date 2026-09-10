"""Evidence validation and immutable local object-store guarantees."""
from __future__ import annotations

import hashlib
import io

import pytest
from PIL import Image

from lmpc.server.api.errors import ApiError
from lmpc.server.svc.evidence import validate_image
from lmpc.server.svc.object_store import LocalObjectStore


def _png(size=(5, 4)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "green").save(out, "PNG")
    return out.getvalue()


def test_png_is_decoded_and_addressed_by_its_content():
    data = _png()
    digest = hashlib.sha256(data).hexdigest()
    image = validate_image(
        data=data, filename="label.png", media_type="image/png", expected_sha256=digest,
        max_bytes=10_000, max_pixels=100)
    assert (image.width_px, image.height_px) == (5, 4)
    assert image.storage_key == f"images/{digest[:2]}/{digest}.png"


def test_byte_cap_precedes_image_decode():
    data = _png()
    with pytest.raises(ApiError) as raised:
        validate_image(
            data=data, filename="large.png", media_type="image/png",
            expected_sha256=hashlib.sha256(data).hexdigest(),
            max_bytes=2, max_pixels=100)
    assert raised.value.code == "E_IMAGE_TOO_LARGE"


def test_local_store_rejects_traversal_and_digest_lies(tmp_path):
    store = LocalObjectStore(tmp_path)
    digest = hashlib.sha256(b"safe").hexdigest()
    with pytest.raises(ValueError, match="relative"):
        store.put_immutable("/outside", b"safe", "image/png", digest)
    with pytest.raises(ValueError, match="SHA-256"):
        store.put_immutable("images/lying", b"unsafe", "image/png", digest)
    assert list(tmp_path.rglob("*")) == []


def test_local_store_never_overwrites_an_existing_object(tmp_path):
    store = LocalObjectStore(tmp_path)
    key = "images/aa/evidence.png"
    target = tmp_path / key
    target.parent.mkdir(parents=True)
    target.write_bytes(b"first")
    with pytest.raises(RuntimeError, match="collision"):
        store.put_immutable(key, b"second", "image/png",
                            hashlib.sha256(b"second").hexdigest())
    assert target.read_bytes() == b"first"
