"""
Fetch real Indian packaged-commodity label photographs from Open Food Facts.

Why this source: the photographs are of actual retail packages sold in India, taken by
ordinary people on ordinary phones — bad lighting, glare, curvature, fingers in frame.
That is precisely the input an enforcement officer will produce.

It also ships partial ground truth. `quantity` ("62 g") and `brands` come from the
product record, so extraction can be scored against something we did not author.
"""
from __future__ import annotations
import json, subprocess, time, hashlib
from pathlib import Path

UA = "lmpc-compliance-research/1.0 (SIH prototype)"

SEARCH = ("https://world.openfoodfacts.org/cgi/search.pl?action=process"
          "&tagtype_0=countries&tag_contains_0=contains&tag_0=india&json=1")
PANEL_OF = {"front": "FRONT", "ingredients": "BACK",
            "nutrition": "BACK", "packaging": "BACK"}


def _get(url: str, retries: int = 4) -> bytes:
    """Fetch with backoff.

    curl rather than urllib: the host answers curl reliably and 503s urllib's default
    headers. Public data sources are flaky by nature - the ingestion layer has to expect
    it, which is the same reason the rulepack is cached rather than fetched per scan.
    """
    last = b""
    for i in range(retries):
        time.sleep(0.4 * i)
        r = subprocess.run(["curl", "-sk", "-m", "90", "-A", UA, url],
                           capture_output=True)
        if r.returncode == 0 and r.stdout and not r.stdout.lstrip()[:15].lower().startswith(b"<!doctype"):
            return r.stdout
        last = r.stdout
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"could not fetch {url[:80]} after {retries} tries")


def search(pages: int = 3, page_size: int = 20,
           cache: Path = Path("real/.search")) -> list[dict]:
    """Page through the index, caching each page to disk.

    The source is a free public API and goes down intermittently - it did so twice during
    this run. A page already fetched is never refetched, and a page that fails is skipped
    rather than aborting the whole harvest. Partial data is still useful; a lost harvest
    is not.
    """
    cache.mkdir(parents=True, exist_ok=True)
    out, failed = [], 0
    for page in range(1, pages + 1):
        f = cache / f"page{page}.json"
        if not f.exists():
            try:
                f.write_bytes(_get(f"{SEARCH}&page_size={page_size}&page={page}"))
            except RuntimeError:
                failed += 1
                continue
            time.sleep(1.2)          # be a good citizen on a free public API
        try:
            out += json.loads(f.read_text()).get("products", [])
        except json.JSONDecodeError:
            f.unlink(missing_ok=True)
            failed += 1
    if failed:
        print(f"  note: {failed} search page(s) unavailable; continuing with {len(out)}")
    return out


def full_res(url: str) -> str:
    """OFF serves 400 px previews by default. Legal-metrology print is small; a 400 px
    render of a biscuit wrapper cannot resolve a 2 mm MRP. Always take the full frame."""
    for suffix in (".400.jpg", ".200.jpg", ".100.jpg"):
        if url.endswith(suffix):
            return url[: -len(suffix)] + ".full.jpg"
    return url


def download(products: list[dict], into: Path, max_products: int = 40,
             min_panels: int = 1) -> list[dict]:
    """Save every available panel image per product. Returns records with local paths."""
    into.mkdir(parents=True, exist_ok=True)
    recs = []
    # Prefer packages photographed from several sides: MRP, packing date and consumer
    # care usually live on the back, which is exactly what a single front shot misses.
    products = sorted(products, key=lambda p: -sum(
        1 for k in PANEL_OF if p.get(f"image_{k}_url")))
    for p in products:
        code = p.get("code")
        panels = []
        for kind, panel in PANEL_OF.items():
            url = p.get(f"image_{kind}_url")
            if not url:
                continue
            f = into / f"{code}_{kind}.jpg"
            if not f.exists():
                try:
                    f.write_bytes(_get(full_res(url), retries=2))
                except Exception:
                    continue
            if f.stat().st_size > 3000:
                panels.append({"panel": panel, "kind": kind, "path": str(f)})
        if len(panels) < min_panels:
            continue
        recs.append({
            "code": code,
            "name": (p.get("product_name") or "").strip(),
            "brands": (p.get("brands") or "").strip(),
            # Ground truth we did not author: the declared net quantity on the record.
            "declared_quantity": (p.get("quantity") or "").strip(),
            "panels": panels,
            "sha256": hashlib.sha256(
                b"".join(Path(x["path"]).read_bytes() for x in panels)).hexdigest()[:16],
        })
        if len(recs) >= max_products:
            break
    return recs


def enrich(products: list[dict], cache: Path = Path("real/.products")) -> list[dict]:
    """Pull the full product record per barcode.

    The search index only exposes the front image. Back, ingredients and packaging
    panels - where MRP, packing date and consumer care actually live - are only on the
    per-product record. A front-only photograph is itself a real and common scenario, so
    products that stay single-panel are kept, not discarded.
    """
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for i, p in enumerate(products, 1):
        code = p.get("code")
        if not code:
            continue
        f = cache / f"{code}.json"
        if not f.exists():
            try:
                f.write_bytes(_get(
                    f"https://world.openfoodfacts.org/api/v0/product/{code}.json",
                    retries=2))
            except RuntimeError:
                out.append(p); continue
            time.sleep(0.4)
        try:
            full = json.loads(f.read_text()).get("product") or {}
        except json.JSONDecodeError:
            f.unlink(missing_ok=True); out.append(p); continue
        merged = dict(p)
        for k, v in full.items():
            if k.startswith("image_") and isinstance(v, str):
                merged[k] = v
        out.append(merged)
        if i % 25 == 0:
            print(f"  enriched {i}/{len(products)}", flush=True)
    return out


def load_or_fetch(into: Path, manifest: Path, max_products: int = 40,
                  pages: int = 8, min_panels: int = 1) -> list[dict]:
    if manifest.exists():
        return json.loads(manifest.read_text())
    recs = download(enrich(search(pages=pages)), into, max_products, min_panels)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(recs, indent=2, ensure_ascii=False))
    return recs


if __name__ == "__main__":
    r = load_or_fetch(Path("real/images"), Path("real/manifest.json"),
                      max_products=60, pages=10, min_panels=1)
    print(f"{len(r)} products, {sum(len(x['panels']) for x in r)} panel images")
    for x in r[:6]:
        print(f"  {x['code']}  {x['name'][:34]:<34} {x['declared_quantity']:<10} "
              f"{len(x['panels'])} panels")
