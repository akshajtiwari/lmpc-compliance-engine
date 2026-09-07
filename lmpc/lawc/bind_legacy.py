#!/usr/bin/env python3
"""
bind — turn compiler output into a rulepack diff for human approval.

The point: a binding attaches to a rule-tree NODE ID, not to a value. When an
amendment substitutes the contents of that node, the check parameters reload
automatically and nobody retypes anything. The human approves a diff.
"""
import json, sys

# Six generic operators are written once, in code. Everything else is parameters
# lifted out of the gazette. Bindings are seeded once and survive amendments.
BINDINGS = {
    "lmpc/r7/table-I": {"check": "LMPC-R7-2-MIN-HEIGHT", "operator": "table_lookup",
                        "input": "pdp_area_cm2", "compare": "glyph_height_mm"},
    "lmpc/r7/sr3":     {"check": "LMPC-R7-3-WIDTH-RATIO", "operator": "ratio_min"},
    "lmpc/r7/table-II":{"check": "LMPC-R7-TABLE-II", "operator": "table_lookup"},
    "lmpc/r6/sr9":     {"check": "LMPC-R6-10-ECOMMERCE", "operator": "presence_set"},
}

# What the rulepack held before this amendment was applied (the repealed 2011 table).
CURRENT = {"LMPC-R7-2-MIN-HEIGHT": {
    "status": "ACTIVE", "keyed_by": "net_quantity",
    "rows": [{"band": "up to 200 g/ml", "min_height_mm": 1.0},
             {"band": "200 g/ml - 1 kg/l", "min_height_mm": 2.0},
             {"band": "above 1 kg/l", "min_height_mm": 4.0}]}}

def diff(doc):
    out = []
    for op in doc["ops"]:
        b = BINDINGS.get(op["node"])
        if not b:
            continue
        entry = {"node": op["node"], "operation": op["op"], "check": b["check"],
                 "source": doc["self_gsr"], "file": doc["file"]}
        if op["op"] == "omit":
            entry["effect"] = "REPEAL check — stop evaluating it"
            entry["human_action"] = "confirm repeal"
        elif op["node"] == "lmpc/r7/table-I" and doc.get("table_I"):
            entry["effect"] = "RELOAD parameters — no code change, no retyping"
            entry["was"] = CURRENT["LMPC-R7-2-MIN-HEIGHT"]
            entry["now"] = {"status": "ACTIVE", "keyed_by": "pdp_area_cm2",
                            "rows": doc["table_I"]["rows"]}
            entry["human_action"] = ("confirm %d boundary operators — '≤' glyphs were "
                "lost by text extraction" % sum(r["needs_human_confirmation"]
                                                for r in doc["table_I"]["rows"]))
        else:
            entry["effect"] = "REVIEW clause text — operator may need new parameters"
            entry["human_action"] = "review"
        out.append(entry)
    return out

if __name__ == "__main__":
    data = json.load(open(sys.argv[1]))
    target = sys.argv[2] if len(sys.argv) > 2 else "2017-8xii.pdf"
    doc = next(d for d in data["documents"] if d["file"] == target)
    print(json.dumps({"amendment": doc["self_gsr"], "title": doc["title"],
                      "commencement": doc["commencement"],
                      "rulepack_changes": diff(doc)}, indent=2, ensure_ascii=False))
