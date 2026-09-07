"""
Real-world run: real photographs of real Indian retail packages, real OCR, real rulepack.

Everything before this was rendered or simulated. Here nothing is: the images are phone
photos taken by members of the public, the text comes out of PP-OCR, and the only ground
truth is the net quantity recorded on the product record — which we did not author.
"""
from __future__ import annotations
import json, re, sys, time
from collections import Counter
from pathlib import Path

from lmpc.lawc.build import load
from lmpc.engine.engine import run, FIELD_KINDS
from lmpc.engine.extract import extract
from lmpc.engine.model import Scan, Verdict
from lmpc.engine import ocr, normalize
from lmpc.labels.openfoodfacts import load_or_fetch

G, R, Y, D, E = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
IMAGES, MANIFEST, CACHE = Path("real/images"), Path("real/manifest.json"), Path("real/ocr.json")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def ocr_all(recs: list[dict]) -> dict:
    """OCR every panel once and cache it — recognition is the slow part, not the rules."""
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for i, r in enumerate(recs, 1):
        if r["code"] in cache:
            continue
        toks = []
        for p in r["panels"]:
            for t in ocr.read(p["path"], panel=p["panel"]):
                toks.append({"text": t.text, "x": t.x, "y": t.y, "w": t.w, "h": t.h,
                             "conf": round(t.conf, 3), "panel": t.panel,
                             "cap": round(t.cap_height_px, 1)})
        cache[r["code"]] = toks
        print(f"  [{i}/{len(recs)}] {r['code']} {r['name'][:30]:<30} {len(toks)} regions",
              flush=True)
        CACHE.write_text(json.dumps(cache))
    return cache


def to_scan(rec: dict, toks: list[dict]) -> Scan:
    from lmpc.engine.model import Token
    q = normalize.quantity(rec.get("declared_quantity", "") or "")
    return Scan(
        tokens=[Token(t["text"], t["x"], t["y"], t["w"], t["h"], t["conf"],
                      t["panel"], t["cap"]) for t in toks],
        panels_captured={p["panel"] for p in rec["panels"]},
        # No ruler, no marker card, no known package dimensions — these are photographs
        # from a public database, not calibrated captures. Millimetre checks must abstain.
        px_per_mm=None, pdp_h_cm=None, pdp_w_cm=None,
        net_quantity_g=q["value"] if q and q["unit"] == "g" else None,
        net_quantity_ml=q["value"] if q and q["unit"] == "ml" else None,
    )


def main() -> int:
    pack = load()
    recs = load_or_fetch(IMAGES, MANIFEST, max_products=45, pages=10, min_panels=2)
    print(f"{Y}REAL-WORLD RUN{E}  {len(recs)} products, "
          f"{sum(len(r['panels']) for r in recs)} photographs")
    print(f"rulepack {pack['version']} · current to "
          f"{pack['currency']['newest_instrument']}\n")

    t0 = time.time()
    cache = ocr_all(recs)
    print(f"{D}OCR: {time.time()-t0:.0f}s for {sum(len(v) for v in cache.values())} "
          f"text regions{E}\n")

    found = Counter(); outcomes = Counter(); per_check = {}
    qty_hit = qty_total = 0
    false_fail_backpanel = 0
    devanagari_products = 0
    rows = []

    for r in recs:
        toks = cache.get(r["code"], [])
        scan = to_scan(r, toks)
        fields = extract(scan, FIELD_KINDS)
        res = run(pack, scan)
        for k, v in fields.items():
            if v:
                found[k] += 1
        for x in res["results"]:
            outcomes[x.verdict.value] += 1
            per_check.setdefault(x.check, Counter())[x.verdict.value] += 1
            # A declaration that lives on an unphotographed panel must never be a FAIL.
            if x.verdict is Verdict.FAIL and x.check.startswith("LMPC-R6-1") and \
                    "BACK" not in scan.panels_captured:
                false_fail_backpanel += 1
        if any(DEVANAGARI.search(t["text"]) for t in toks):
            devanagari_products += 1
        # Ground truth we did not author: the recorded net quantity.
        truth = normalize.quantity(r.get("declared_quantity") or "")
        if truth:
            qty_total += 1
            got = fields.get("net_quantity")
            if got and got.normalized.get("value") == truth["value"] and \
                    got.normalized.get("unit") == truth["unit"]:
                qty_hit += 1
        rows.append((r, res, fields, toks))

    n = len(recs)
    print(f"{Y}FIELD EXTRACTION (share of products where the field was identified){E}")
    for k in ["mrp", "net_quantity", "mfg_date", "consumer_care", "manufacturer_block",
              "country_of_origin", "unit_sale_price", "generic_name"]:
        bar = "#" * int(found[k] / n * 34)
        print(f"  {k:<20}{found[k]:>3}/{n}  {found[k]/n:>5.0%}  {D}{bar}{E}")

    print(f"\n{Y}NET QUANTITY vs THE PRODUCT RECORD (ground truth we did not write){E}")
    print(f"  exact value+unit match: {qty_hit}/{qty_total} = "
          f"{qty_hit/qty_total:.0%}" if qty_total else "  no ground truth available")

    print(f"\n{Y}VERDICTS ACROSS ALL CHECKS{E}")
    tot = sum(outcomes.values())
    for k, v in outcomes.most_common():
        print(f"  {k:<18}{v:>5}  {v/tot:>5.0%}")

    print(f"\n{Y}SAFETY{E}")
    print(f"  FAIL issued for a declaration on an unphotographed panel: "
          f"{G if false_fail_backpanel == 0 else R}{false_fail_backpanel}{E}  (must be 0)")
    print(f"  Devanagari detected on {devanagari_products}/{n} products")

    print(f"\n{Y}PER-CHECK OUTCOMES{E}")
    for chk, c in per_check.items():
        parts = " ".join(f"{k[:4]}={v}" for k, v in c.most_common())
        print(f"  {chk:<32}{parts}")

    json.dump({"products": n, "found": dict(found), "outcomes": dict(outcomes),
               "qty_hit": qty_hit, "qty_total": qty_total,
               "per_check": {k: dict(v) for k, v in per_check.items()},
               "false_fail_backpanel": false_fail_backpanel,
               "devanagari_products": devanagari_products},
              open("real/summary.json", "w"), indent=2)
    return 0 if false_fail_backpanel == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
