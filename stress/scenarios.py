"""Stress scenarios. Each states the verdict the LAW requires, not the verdict the code
currently produces — so a regression shows up as a failing expectation."""
from __future__ import annotations
from pathlib import Path
from lmpc.labels.generate import make, COMPLIANT_LINES

OUT = Path("out/labels")


def _lines(**repl):
    out = []
    for panel, text in COMPLIANT_LINES:
        for key, new in repl.items():
            if key.upper().replace("_", " ") in text.upper() or \
               (key == "mrp" and text.startswith("MRP")) or \
               (key == "mfg" and text.startswith("MFG")) or \
               (key == "qty" and text.startswith("Net Qty")):
                text = new
        out.append((panel, text))
    return out


def build():
    S = []

    def add(name, label, expect, note=""):
        S.append({"name": name, "label": label, "expect": expect, "note": note})

    # -- baseline: a label that complies -------------------------------------------
    add("compliant_baseline",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
             write_to=OUT / "compliant.png", net_quantity_g=500),
        {"LMPC-R7-2-MIN-HEIGHT": "PASS", "LMPC-R6-1-E-MRP": "PASS",
         "LMPC-R6-1-E-MRP-FORM": "PASS", "LMPC-R8-CLEAR-SPACE": "PASS"},
        "215 cm2 panel needs 2.5 mm; drawn at 2.8 mm")

    # -- Rule 7(2): the measurement itself ------------------------------------------
    add("font_clearly_below_threshold",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=1.6,
             write_to=OUT / "font_small.png", net_quantity_g=500),
        {"LMPC-R7-2-MIN-HEIGHT": "FAIL"}, "1.6 mm against a required 2.5 mm")

    add("font_on_the_threshold",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.5,
             net_quantity_g=500),
        {"LMPC-R7-2-MIN-HEIGHT": "INDETERMINATE"},
        "measurement straddles 2.5 mm within one pixel; must not accuse")

    add("panel_area_on_a_table_boundary",
        make(lines=COMPLIANT_LINES, pdp_h_cm=25.0, pdp_w_cm=20.0, cap_mm=4.5,
             net_quantity_g=500),
        {"LMPC-R7-2-MIN-HEIGHT": "INDETERMINATE"},
        "exactly 500 cm2 - the '<' vs '≤' reading is unresolved")

    add("molded_container_needs_more",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=3.0,
             net_quantity_g=500, is_molded=True),
        {"LMPC-R7-2-MIN-HEIGHT": "FAIL"}, "molded column requires 4.0 mm, not 2.5")

    # -- evidence sufficiency --------------------------------------------------------
    add("no_scale_reference",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=1.2,
             net_quantity_g=500),
        {"LMPC-R7-2-MIN-HEIGHT": "INDETERMINATE"},
        "no ruler in frame: cannot measure millimetres, so cannot accuse",
        )
    S[-1]["mutate"] = lambda s: setattr(s, "px_per_mm", None)

    add("back_panel_never_photographed",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
             panels=("FRONT",), net_quantity_g=500),
        {"LMPC-R6-1-F-CONSUMER-CARE": "INDETERMINATE",
         "LMPC-R6-1-A-MANUFACTURER": "INDETERMINATE"},
        "absence of evidence is not evidence of absence")

    # -- format ----------------------------------------------------------------------
    add("mrp_missing_inclusive_of_taxes",
        make(lines=_lines(mrp="MRP Rs. 45.00"), pdp_h_cm=18.2, pdp_w_cm=11.8,
             cap_mm=2.8, write_to=OUT / "mrp_no_taxes.png", net_quantity_g=500),
        {"LMPC-R6-1-E-MRP-FORM": "FAIL"}, "2017 amendment prescribes the wording")

    add("mrp_not_rounded",
        make(lines=_lines(mrp="MRP Rs. 45.30 (incl. of all taxes)"), pdp_h_cm=18.2,
             pdp_w_cm=11.8, cap_mm=2.8, net_quantity_g=500),
        {"LMPC-R6-1-E-MRP-ROUNDING": "FAIL"},
        "must round to the nearest rupee or 50 paise")

    add("quantity_crowded_by_other_print",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
             crowd_quantity=True, write_to=OUT / "crowded.png", net_quantity_g=500),
        {"LMPC-R8-CLEAR-SPACE": "FAIL"}, "Rule 8 needs 1x above/below the numeral height")

    # -- applicability: the checks that prevent false accusations --------------------
    add("exempt_small_pack_8g",
        make(lines=[("FRONT", "Sachet")], pdp_h_cm=3.0, pdp_w_cm=2.0, cap_mm=0.8,
             net_quantity_g=8),
        {"LMPC-R6-1-E-MRP": "NOT_APPLICABLE", "LMPC-R7-2-MIN-HEIGHT": "NOT_APPLICABLE"},
        "Rule 26(a): nothing in these rules applies at 10 g or less")

    add("tobacco_8g_is_not_exempt",
        make(lines=[("FRONT", "Sachet")], pdp_h_cm=3.0, pdp_w_cm=2.0, cap_mm=0.8,
             net_quantity_g=8, category="TOBACCO"),
        {"LMPC-R6-1-E-MRP": "FAIL"}, "the proviso removes tobacco from that exemption")

    add("bulk_pack_30kg",
        make(lines=[("FRONT", "Bulk")], pdp_h_cm=40.0, pdp_w_cm=30.0, cap_mm=6.0,
             net_quantity_g=30000),
        {"LMPC-R6-1-E-MRP": "NOT_APPLICABLE"}, "Rule 3(a): over 25 kg")

    add("institutional_buyer",
        make(lines=[("FRONT", "Catering pack")], pdp_h_cm=20.0, pdp_w_cm=15.0,
             cap_mm=3.0, net_quantity_g=2000, buyer_type="INSTITUTIONAL"),
        {"LMPC-R6-1-E-MRP": "NOT_APPLICABLE"}, "Rule 3(c)")

    add("ecommerce_listing",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
             net_quantity_g=500, mode="ECOMMERCE_LISTING"),
        {"LMPC-R6-1-D-MFG-DATE": "NOT_APPLICABLE", "LMPC-R6-1-E-MRP": "PASS"},
        "Rule 6(10): every declaration except month and year of packing")

    # --- Rule 9(4): permitted scripts -------------------------------------------
    hindi = [("FRONT", "अधिकतम खुदरा मूल्य 45.00 रुपये (सभी करों सहित)"),
             ("FRONT", "शुद्ध मात्रा: 500 ग्राम"),
             ("BACK",  "निर्मित: फू फूड्स, पुणे 411001")]
    add("hindi_only_label_is_lawful",
        make(lines=hindi, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8, net_quantity_g=500),
        {"LMPC-R9-4-LANGUAGE": "PASS"},
        "Rule 9(4) permits Hindi in Devanagari OR English")

    add("english_plus_another_script_is_lawful",
        make(lines=COMPLIANT_LINES + [("BACK", "தரமான தயாரிப்பு")],
             pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8, net_quantity_g=500),
        {"LMPC-R9-4-LANGUAGE": "PASS"},
        "the proviso permits any other language IN ADDITION")

    # --- Rule 6(3): the lower-MRP sticker ---------------------------------------
    add("two_prices_on_one_pack",
        make(lines=COMPLIANT_LINES + [("FRONT", "MRP Rs. 40.00 (incl. of all taxes)")],
             pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8, net_quantity_g=500),
        {"LMPC-R6-3-MRP-STICKER": "REVIEW_REQUIRED"},
        "lawful only as a revised lower price that does not cover the original")

    add("single_price_is_not_flagged",
        make(lines=COMPLIANT_LINES, pdp_h_cm=18.2, pdp_w_cm=11.8, cap_mm=2.8,
             net_quantity_g=500),
        {"LMPC-R6-3-MRP-STICKER": "NOT_APPLICABLE"}, "one price, nothing to review")

    # --- date plausibility -------------------------------------------------------
    add("packing_date_in_the_future",
        make(lines=_lines(mfg="MFG 02/2030"), pdp_h_cm=18.2, pdp_w_cm=11.8,
             cap_mm=2.8, net_quantity_g=500),
        {"LMPC-R6-1-D-DATE-PLAUSIBLE": "REVIEW_REQUIRED"},
        "a misprint or a misreading - never an automatic finding")

    # --- Rule 10(1) proviso: very small packages ---------------------------------
    add("sachet_under_10_cubic_cm",
        make(lines=[("FRONT", "Manufactured by Foo Foods, Pune 411001")],
             pdp_h_cm=3.0, pdp_w_cm=2.0, cap_mm=0.9, net_quantity_g=40,
             capacity_cm3=8.0),
        {"LMPC-R10-1-SMALL-PACKAGE-MARK": "PASS"},
        "2017 raised the relaxation from 5 to 10 cubic cm")

    # --- Rule 26(c): drugs are outside these rules entirely ----------------------
    add("dpco_drug_formulation",
        make(lines=COMPLIANT_LINES, pdp_h_cm=10.0, pdp_w_cm=5.0, cap_mm=2.0,
             net_quantity_g=100, category="DRUG_FORMULATION"),
        {"LMPC-R6-1-E-MRP": "NOT_APPLICABLE"},
        "Drugs (Price Control) Order formulations are exempt")

    return S
