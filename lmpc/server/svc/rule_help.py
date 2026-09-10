"""Plain-language, non-normative explanations for rule-review screens.

The rulepack remains the authority and the engine remains the decision-maker. These
descriptions only explain an already-issued result; they never participate in a verdict.
"""
from __future__ import annotations

from typing import Any

from ..api.errors import ApiError


_GUIDES = {
    "LMPC-R6-1-A-MANUFACTURER": (
        "Manufacturer, packer, or importer details",
        "The package should identify the responsible manufacturer, packer, or importer "
        "with the name and address required for that role.",
        "OCR candidates are scored for declaration wording and layout. An absence is "
        "called a violation only when required surfaces were confirmed and readable.",
        "A legible panel containing the responsible party's name and address.",
    ),
    "LMPC-R6-1-B-GENERIC-NAME": (
        "Common or generic product name",
        "The package should state the common or generic name of the commodity.",
        "The engine looks for a distinct product-name declaration. Because a brand can "
        "be hard to distinguish from a generic name, uncertain cases are withheld for review.",
        "A clear product-name declaration, separate from decorative brand text where possible.",
    ),
    "LMPC-R6-1-C-NET-QUANTITY": (
        "Net quantity declaration",
        "The package should declare the net quantity in an appropriate standard unit.",
        "The engine identifies quantity text and normalises the number and unit. It does "
        "not treat nutrition-table serving values as proof of the package's net quantity.",
        "The panel containing Net Qty, Net Weight, volume, length, number, or count.",
    ),
    "LMPC-R6-1-D-MFG-DATE": (
        "Manufacture, packing, or import date",
        "The applicable month and year of manufacture, pre-packing, or import should be declared.",
        "The engine looks for date wording and a month/year value, then keeps uncertain "
        "readings separate from proven absence.",
        "A legible date declaration and its nearby label, such as MFD, PKD, or Imported.",
    ),
    "LMPC-R6-1-E-MRP": (
        "Maximum retail price",
        "The retail sale price should be declared as the maximum retail price inclusive of taxes.",
        "OCR price candidates are ranked using MRP wording, currency, position, and "
        "confidence. Close competing candidates cause abstention instead of a guess.",
        "The complete MRP line, including currency, amount, and inclusive-of-taxes wording.",
    ),
    "LMPC-R6-1-F-CONSUMER-CARE": (
        "Consumer-care contact",
        "The package should provide the required consumer complaint or care contact details.",
        "The engine looks for consumer-care wording and contact information. Missing "
        "details become a violation only after complete, legible coverage is established.",
        "The consumer-care block, including the printed contact channel or address.",
    ),
    "LMPC-R6-COUNTRY-OF-ORIGIN": (
        "Country of origin for an imported package",
        "An imported package should declare its country of origin.",
        "This check runs only when the inspection is marked Imported. OCR then looks for "
        "country-of-origin wording and a country value.",
        "The import declaration and the correct Imported package selection in scan details.",
    ),
    "LMPC-R6-1-E-MRP-FORM": (
        "MRP wording and format",
        "The price line should contain a currency amount and state that the MRP includes all taxes.",
        "The extracted MRP line is compared with the reviewed formats and accepted wording "
        "stored in the rulepack.",
        "One sharp image showing the complete MRP line without cropping its surrounding words.",
    ),
    "LMPC-R6-1-E-MRP-ROUNDING": (
        "MRP rounding",
        "The declared retail price should follow the permitted rupee or fifty-paise rounding.",
        "The engine parses the MRP amount and applies the numeric rounding predicate from "
        "the versioned rulepack.",
        "A confident MRP amount with clearly visible decimal digits.",
    ),
    "LMPC-R6-1-C-QTY-FORM": (
        "Net quantity number and unit format",
        "The net quantity should contain a readable number and an allowed unit or count form.",
        "The extracted quantity is checked against the reviewed number-and-unit grammar in "
        "the rulepack.",
        "The complete net-quantity line, including its number and unit.",
    ),
    "LMPC-R6-1-D-DATE-FORM": (
        "Date format",
        "The manufacture, packing, or import date should use a recognisable month/year form.",
        "The engine parses numeric and named-month formats and refuses malformed or ambiguous values.",
        "A sharp close view of the whole date declaration.",
    ),
    "LMPC-R10-PIN-CODE": (
        "Postal PIN code",
        "The responsible party's address should include a six-digit Indian postal PIN code where required.",
        "The engine checks the extracted manufacturer or packer address for a six-digit PIN.",
        "The full address block, not only the company name.",
    ),
    "LMPC-R6-1-LL-UNIT-SALE-PRICE": (
        "Unit sale price",
        "Where required, the package should show a unit price using the unit appropriate to its quantity.",
        "The rulepack selects per g, kg, ml, litre, cm, metre, or number from the declared "
        "measure and checks the unit-price wording.",
        "MRP, net quantity, and the complete unit-sale-price line.",
    ),
    "LMPC-R7-3-WIDTH-RATIO": (
        "Character width-to-height ratio",
        "Ordinary declaration characters should not be narrower than one third of their height.",
        "The check needs trustworthy individual-glyph geometry and excludes naturally narrow "
        "characters. Line-level OCR boxes cannot safely prove a violation.",
        "A square, sharp image with sufficient resolution for individual character measurement.",
    ),
    "LMPC-R8-CLEAR-SPACE": (
        "Clear space around net quantity",
        "The net-quantity declaration needs clear space around it relative to numeral height.",
        "The engine compares the visible gaps above/below and left/right with the measured "
        "numeral height, using the factors in the rulepack.",
        "The complete net-quantity line plus unclipped surrounding space.",
    ),
    "LMPC-R7-2-MIN-HEIGHT": (
        "Minimum declaration character height",
        "Declaration letters and numerals must meet the minimum height selected from Table I.",
        "For current law, the engine selects a row from principal-display-panel area and "
        "compares a scale-backed glyph measurement. Boundary uncertainty is withheld.",
        "Panel dimensions, a coplanar scale reference, and a sharp close image of the declaration.",
    ),
    "LMPC-R9-4-LANGUAGE": (
        "Permitted declaration language",
        "Required declarations should appear in Hindi (Devanagari) or English; other languages may be additional.",
        "The engine identifies scripts only in established declaration text. No established "
        "text produces an indeterminate result rather than an accusation.",
        "Legible declaration text in Hindi or English; additional languages may remain visible.",
    ),
    "LMPC-R6-3-MRP-STICKER": (
        "Multiple prices or altered MRP",
        "A sticker should not improperly alter a mandatory declaration; multiple retail prices need careful review.",
        "The engine collects distinct price candidates. A single price makes this check not "
        "applicable; multiple values are sent for officer review with both values retained.",
        "Every panel or sticker showing a retail price, including the original price beneath it.",
    ),
    "LMPC-R6-1-D-DATE-PLAUSIBLE": (
        "Date plausibility",
        "A declared packing or manufacture date should be possible on the inspection date.",
        "The parsed month/year is compared with the inspection date and the commencement of "
        "the rules. Impossible values require review because OCR may have misread them.",
        "A clear date declaration and the correct inspection date in scan details.",
    ),
    "LMPC-R10-1-SMALL-PACKAGE-MARK": (
        "Very small package identification",
        "A package at or below the rulepack's small-capacity limit may use an identifying mark "
        "instead of the full manufacturer name and address.",
        "The check first needs package capacity, then looks for an identifying mark and applies "
        "the recorded relaxation without weakening unrelated requirements.",
        "Package capacity and a legible identifying mark.",
    ),
    "LMPC-XF-UNIT-PRICE-CONSISTENT": (
        "Unit-price arithmetic consistency",
        "The declared unit price should agree with MRP divided by net quantity within the allowed tolerance.",
        "The engine normalises all three declarations, calculates the expected unit price, and "
        "sends material disagreement for review rather than declaring fraud.",
        "MRP, net quantity, and unit sale price read confidently from the same package.",
    ),
}

_OUTCOMES = {
    "PASS": "The required evidence was established and met this check.",
    "FAIL": "The evidence was sufficient to prove that this requirement was not met.",
    "INDETERMINATE": "The engine could not safely decide from the available evidence.",
    "NOT_APPLICABLE": "This requirement does not apply to the selected package context.",
    "REVIEW_REQUIRED": "A qualified officer must resolve a fact or permitted exception.",
    "SYSTEM_ERROR": "A software or dependency failure occurred; this is not a legal finding.",
}


def rule_detail(pack: dict[str, Any], check_code: str) -> dict[str, Any]:
    spec = next((item for item in pack["checks"] if item["check"] == check_code), None)
    if spec is None:
        raise ApiError("E_NOT_FOUND", f"rule check {check_code} not found")
    title, requirement, method, evidence = _GUIDES.get(
        check_code,
        (spec["clause"], "See the cited rulepack entry for this requirement.",
         "The deterministic operator evaluates the established evidence.",
         "Legible evidence relevant to this declaration."),
    )
    return {
        "check": check_code,
        "title": title,
        "clause": spec["clause"],
        "requirement": requirement,
        "method": method,
        "evidence_needed": evidence,
        "effective_from": spec.get("effective_from"),
        "authority": spec.get("citation") or {},
        "important_limits": _limits(spec),
        "outcomes": _OUTCOMES,
        "non_normative_notice": (
            "This is a plain-language aid. The cited gazette and approved rulepack are authoritative."
        ),
    }


def decision_explanation(record) -> dict[str, Any] | None:
    overall = record.overall
    if not overall:
        return None
    ocr_ran = any(image.max_edge_used is not None for image in record.images)
    if overall == "OUT_OF_SCOPE":
        buyer = record.metadata.get("buyer_type", "RETAIL")
        if buyer in {"INDUSTRIAL", "INSTITUTIONAL"}:
            return {
                "heading": "Stopped at the applicability gate — the image was not rejected",
                "summary": (
                    f"This inspection was submitted with Buyer type = {buyer.title()}. "
                    "Rule 3 excludes packages meant for industrial or institutional consumers "
                    "from these Chapter II retail-package checks, so all checks became not applicable."
                ),
                "next_step": (
                    "If this product is sold to an individual consumer, start a new inspection "
                    "and select Retail. Keep this selection only when the buyer really is industrial "
                    "or institutional."
                ),
                "processing_stage": "Applicability gate",
                "ocr_ran": ocr_ran,
            }
        return {
            "heading": "Stopped at the applicability gate",
            "summary": (
                "The scan details matched an exemption or category outside these checks. "
                "The image was stored, but legal declaration checks did not run."
            ),
            "next_step": "Review the category, buyer type, quantity, and package context before resubmitting.",
            "processing_stage": "Applicability gate",
            "ocr_ran": ocr_ran,
        }
    messages = {
        "INCOMPLETE_EVIDENCE": (
            "The engine ran but the evidence could not safely support every decision.",
            "Open Cannot determine findings to see the missing panel, legibility, or measurement need."
        ),
        "NON_COMPLIANT": (
            "At least one requirement has sufficient evidence for a violation finding.",
            "Open each Violation card and verify its evidence and authority before finalising."
        ),
        "REVIEW_REQUIRED": (
            "No proven violation controls the result, but at least one fact needs officer judgement.",
            "Open Needs review findings and record a reasoned override only when justified."
        ),
        "SYSTEM_ERROR": (
            "A software or dependency error prevented a safe result.",
            "Do not treat this as a finding; inspect the System error card and rerun after repair."
        ),
        "COMPLIANT": (
            "Every applicable check was supported by evidence and no violation was found.",
            "Review the evidence set and citations before finalising the report."
        ),
    }
    summary, next_step = messages.get(overall, ("Evaluation finished.", "Review each finding."))
    return {
        "heading": overall.replace("_", " ").title(),
        "summary": summary,
        "next_step": next_step,
        "processing_stage": "Rule evaluation",
        "ocr_ran": ocr_ran,
    }


def _limits(spec: dict[str, Any]) -> list[str]:
    params = spec.get("params") or {}
    operator = spec.get("operator")
    if operator == "ratio_min":
        return [f"Minimum width-to-height ratio: {params['min']:.4f} (about one third)."]
    if operator == "clear_space":
        return [
            f"Above and below: at least {params['above_below_multiple']:g}× numeral height.",
            f"Left and right: at least {params['left_right_multiple']:g}× numeral height.",
        ]
    if operator == "table_lookup":
        rows = params.get("rows") or []
        printed = ", ".join(f"{row['band_as_printed']}: {row['min_mm']:g} mm"
                            for row in rows)
        return [f"Current printed-character Table I bands: {printed}.",
                "A coplanar scale reference is required for an absolute millimetre finding."]
    if operator == "small_package_mark":
        return [f"Recorded capacity limit: {params['capacity_cm3_at_or_below']:g} cm³."]
    if operator == "cross_field":
        return [f"Recorded arithmetic tolerance: {params['tolerance_pct']:g}%."]
    if operator == "script_allowed":
        return ["Hindi in Devanagari or English is required; additional languages are permitted."]
    if spec.get("verdict_ceiling"):
        return [str(spec.get("ceiling_reason") or
                    f"Verdict ceiling: {spec['verdict_ceiling']}.")]
    return []
