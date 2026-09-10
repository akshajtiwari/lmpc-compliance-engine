"""
Real OCR. RapidOCR runs the PP-OCR detection and recognition models under ONNX Runtime —
the same model family as PaddleOCR, without the heavy dependency.

Two things learned from real photographs:

1. A detection box is not a glyph. The box around "MRP Rs. 45.00" spans ascenders and
   descenders and carries padding, so its height OVERSTATES the letter height Rule 7(2)
   measures. Absolute millimetre verdicts must never be taken from box height alone.

2. Resolution is not free. Real phone photos in this corpus reach 9248 x 6936 — 64
   megapixels. Handing that to the recogniser exhausts memory and takes minutes. We cap
   the long edge, and record the cap, because it is the main lever between "usable in the
   field" and "can read the small print".
"""
from __future__ import annotations
import io
from functools import lru_cache
from pathlib import Path

from .model import Token
from . import ocr_select

CAP_RATIO = 0.62      # rough cap-height fraction of a text-line box; a bias, not a fact
MAX_EDGE = 1800       # long edge in pixels handed to the recogniser


def _cuda_available() -> bool:
    """Whether a session ACTUALLY runs on CUDA — not merely whether it is advertised.

    onnxruntime-gpu lists CUDAExecutionProvider in get_available_providers() even when the
    CUDA runtime libraries are absent; session creation then falls back to CPU with only a
    warning. We measured "GPU" timings for an entire round that were silently CPU. Probe
    by building a session and asking what it is really using.
    """
    try:
        import numpy as np, onnxruntime as ort
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            return False
        import tempfile, os
        # A 1-node model is enough to force provider assignment.
        from onnx import helper, TensorProto, save
        g = helper.make_graph(
            [helper.make_node("Relu", ["x"], ["y"])], "probe",
            [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
            [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])])
        f = tempfile.NamedTemporaryFile(suffix=".onnx", delete=False)
        save(helper.make_model(g), f.name)
        sess = ort.InferenceSession(f.name, providers=["CUDAExecutionProvider"])
        used = "CUDAExecutionProvider" in sess.get_providers()
        os.unlink(f.name)
        return used
    except Exception:
        return False


@lru_cache(maxsize=1)
def _engine():
    """Use the GPU when one is present, fall back to CPU when not.

    Not an optimisation detail: on CPU a dense ingredients panel takes minutes, which
    breaks the under-30-seconds promise in the spec. Field devices have no GPU, so the CPU
    number governs the deployment design and the GPU number governs the server.
    """
    import os, tempfile, yaml
    import rapidocr_onnxruntime as R
    if not _cuda_available():
        return R.RapidOCR()
    base = os.path.join(os.path.dirname(R.__file__), "config.yaml")
    cfg = yaml.safe_load(open(base))
    for section in ("Det", "Cls", "Rec"):
        cfg[section]["use_cuda"] = True
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    yaml.safe_dump(cfg, f)
    f.close()
    try:
        return R.RapidOCR(config_path=f.name)
    except Exception:
        return R.RapidOCR()


def prepare(source: str | Path | bytes, max_edge: int = MAX_EDGE):
    """Decode and downscale to `max_edge` on the long side.

    draft() lets the JPEG decoder downscale while decoding, which is far cheaper than
    decoding 50 megapixels and then resampling; it only overshoots, so a LANCZOS pass
    still lands exactly on the cap.
    """
    import numpy as np
    from PIL import Image
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    im = Image.open(stream)
    try:
        im.draft("RGB", (max_edge, max_edge))
    except Exception:
        pass
    im = im.convert("RGB")
    long_edge = max(im.size)
    if long_edge > max_edge:
        f = max_edge / long_edge
        im = im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))),
                       Image.LANCZOS)
    return np.array(im)


def read(path: str | Path, panel: str = "FRONT", min_conf: float = 0.0,
         max_edge: int = MAX_EDGE) -> list[Token]:
    """Recognise one image into Tokens carrying real geometry and real confidence.

    Geometry is expressed in the RESIZED frame. Every check that uses it is a ratio —
    width to height, clear space to numeral height — so a uniform scale cancels out.
    Absolute millimetre checks do not use these boxes; they need a scale reference in the
    frame, which none of these photographs has.
    """
    return _recognise(prepare(path, max_edge), panel, min_conf)


def read_bytes(data: bytes, panel: str = "FRONT", min_conf: float = 0.0,
               max_edge: int = MAX_EDGE) -> list[Token]:
    """Recognise bytes fetched from immutable object storage without a temporary file."""
    return _recognise(prepare(data, max_edge), panel, min_conf)


def _recognise(frame, panel: str, min_conf: float) -> list[Token]:
    result, _ = _engine()(frame)
    toks: list[Token] = []
    for box, text, score in (result or []):
        score = float(score)          # RapidOCR returns confidence as a string
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        x, y = int(min(xs)), int(min(ys))
        w, h = int(max(xs) - x), int(max(ys) - y)
        if not text.strip() or score < min_conf:
            continue
        toks.append(Token(text=text.strip(), x=x, y=y, w=w, h=h,
                          conf=score, panel=panel, cap_height_px=h * CAP_RATIO))
    # M.19: the bundled recogniser cannot emit Devanagari, so every region also gets
    # read by the Devanagari specialist when it is fetched; the higher-quality
    # reading wins per region (Part 8.1).
    if ocr_select.available() and toks:
        ocr_select.rewrite(frame[:, :, ::-1], toks)      # crops expect BGR
        toks = [t for t in toks if t.text.strip() and t.conf >= min_conf]
    return toks


def read_product(rec: dict, min_conf: float = 0.0) -> tuple[list[Token], set[str]]:
    """Read every photographed panel of one product."""
    toks, panels = [], set()
    for p in rec["panels"]:
        toks += read(p["path"], panel=p["panel"], min_conf=min_conf)
        panels.add(p["panel"])
    return toks, panels
