"""
How much resolution does reading a legal declaration actually need?

The spec promises a full result in under 30 seconds. A 50-megapixel photograph of a dense
ingredients panel takes minutes on a CPU, so resolution is not a free parameter - it is
the main lever between "usable in the field" and "reads the small print". This measures
the trade instead of assuming it.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

from lmpc.engine import ocr
from lmpc.engine.extract import extract
from lmpc.engine.engine import FIELD_KINDS
from lmpc.engine.model import Scan

EDGES = [800, 1280, 1800, 2400]


def main(dataset="food", sample=8):
    sample = int(sample)
    recs = json.loads(Path({"food": "real/manifest.json",
                            "wide": "real/wide.json"}[dataset]).read_text())[:sample]
    print(f"{'max edge':<10}{'seconds/panel':<16}{'regions':<10}{'MRP':<7}{'net qty'}")
    print("-" * 56)
    rows = []
    for edge in EDGES:
        t0, regions, mrp, qty = time.time(), 0, 0, 0
        for r in recs:
            toks = []
            for p in r["panels"]:
                toks += ocr.read(p["path"], panel=p["panel"], max_edge=edge)
            regions += len(toks)
            f = extract(Scan(tokens=toks,
                             panels_captured={p["panel"] for p in r["panels"]}),
                        FIELD_KINDS)
            mrp += bool(f.get("mrp")); qty += bool(f.get("net_quantity"))
        panels = sum(len(r["panels"]) for r in recs)
        secs = (time.time() - t0) / panels
        print(f"{edge:<10}{secs:<16.1f}{regions:<10}{mrp}/{len(recs):<5}{qty}/{len(recs)}")
        rows.append({"max_edge": edge, "sec_per_panel": round(secs, 2),
                     "regions": regions, "mrp": mrp, "qty": qty, "products": len(recs)})
    Path(f"real/resolution-{dataset}.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main(*(sys.argv[1:] or ["food"]))
