"""Evidence photographs, small enough to embed in a report.

The images are already content-addressed in the object store, so a thumbnail is derived
from bytes the manifest already pins — it adds nothing to the hashed snapshot.
"""
from __future__ import annotations

import base64
import io

MAX_PANELS = 6
LONG_EDGE = 480
QUALITY = 70


def render(objects, images: list[dict]) -> list[dict]:
    """Return each panel with `data_uri` and `raw` bytes, skipping what cannot be read.

    A report must still be produced when a thumbnail fails: the finding is the point, the
    picture is corroboration.
    """
    from PIL import Image

    out: list[dict] = []
    for item in images[:MAX_PANELS]:
        entry = {**item, "data_uri": None, "raw": None}
        try:
            source = objects.read(item["storage_key"])
            with Image.open(io.BytesIO(source)) as opened:
                opened = opened.convert("RGB")
                opened.thumbnail((LONG_EDGE, LONG_EDGE))
                buffer = io.BytesIO()
                opened.save(buffer, format="JPEG", quality=QUALITY)
            entry["raw"] = buffer.getvalue()
            entry["data_uri"] = ("data:image/jpeg;base64,"
                                 + base64.b64encode(entry["raw"]).decode())
        except Exception:                                   # noqa: BLE001
            pass
        out.append(entry)
    return out
