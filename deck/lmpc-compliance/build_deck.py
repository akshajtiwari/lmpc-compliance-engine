"""Build the SIH idea-submission deck from the official template.

Fill-in only: the SIH section headings, footer identity placeholders, logos, and
the title-slide submission metadata are left exactly as the template ships them
(the SIH rules forbid changing the template's idea-detail pointers). Each body
text box keeps its section heading paragraph and replaces the template's
instruction bullets with this project's points, drawn from README.md and
docs/evidence/ — figures are copied verbatim from those sources.

The official template ships seven slides; the seventh is the "IMPORTANT
INSTRUCTIONS" slide, which SIH says to delete before submitting (six slides max,
including the title slide). This script deletes it.

Run:  python deck/lmpc-compliance/build_deck.py
Out:  deck/lmpc-compliance/LMPC-Compliance-SIH-Idea.pptx
"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Pt

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "template.pptx"
OUTPUT = Path(__file__).resolve().parent / "LMPC-Compliance-SIH-Idea.pptx"

TEXT_COLOR = RGBColor(0x1F, 0x49, 0x7D)

# Slide index (0-based, template order) -> bullet points under the section heading.
BODIES = {
    # Slide 2 — Proposed Solution (Describe your Idea/Solution/Prototype)
    1: [
        "Legal Metrology officers manually inspect small declarations spread across "
        "every package surface; a missing photograph can be mistaken for a missing "
        "declaration, and an un-updated base PDF can be out of date.",
        "Guided multi-panel capture (camera or gallery, offline-resilient) feeds OCR "
        "and layout analysis; a deterministic rule engine issues a legally traceable "
        "finding citing the exact gazette clause.",
        "Six verdict states (PASS, FAIL, INDETERMINATE, NOT APPLICABLE, REVIEW, "
        "SYSTEM ERROR): “could not read” never becomes “missing” "
        "until the officer asserts full surface coverage.",
        "Applicability gates run before declaration checks, so exempt packages are "
        "never accused.",
        "The law itself is compiled offline from 48 gazette instruments into a "
        "human-reviewed, versioned, SHA-256 rulepack.",
        "No LLM makes compliance decisions — ordinary, auditable Python rules; "
        "officer corrections are append-only and attributed.",
    ],
    # Slide 3 — Technical Approach
    2: [
        "Lane 1 (offline): gazette PDFs → law compiler → versioned, dated, "
        "SHA-256 rulepack — 48 instruments across 3 rule families (2011–2026).",
        "Lane 2 (per scan): guided photos → quality gates → OCR → "
        "layout/extraction → rule engine → six-state verdicts.",
        "One FastAPI service (localhost-capable) with PostgreSQL or a built-in local "
        "store, immutable local object storage, and optional S3.",
        "Clients: installable capture PWA, Android Field app (offline outbox with "
        "idempotent resumable sync), and a Next.js officer review workbench.",
        "Millimetre checks use an ISO ID-1 card as scale reference: corner marks "
        "→ image-to-millimetre homography → panel dimensions in cm; "
        "mis-marked quads are refused and the engine abstains rather than guessing.",
        "E-commerce listings are checked under Rule 6(10) from shopper-visible "
        "listing text plus up to six screenshots.",
    ],
    # Slide 4 — Feasibility and Viability
    3: [
        "Runs today on a laptop: portable Windows EXE for demos, or PostgreSQL plus "
        "local object storage for durable use — no S3 dependency.",
        "Speed: 1.6 seconds per panel on ordinary CPU at the tested 1800 px cap.",
        "Risk: extraction recall (~50%). Mitigation: a dedicated server workstream "
        "with a ≥90% target — meanwhile the engine abstains (INDETERMINATE) "
        "instead of guessing.",
        "Risk: real-device milestone gates (install, LAN pairing, airplane-mode "
        "capture, low storage) are still open. Mitigation: CI-built portable EXE and "
        "APK already published for device drills.",
        "Production legal use requires qualified officer sign-off; the workbench "
        "supports corrections, re-evaluation, and reasoned overrides.",
        "Deployment path: run now → controlled pilot → scale.",
    ],
    # Slide 5 — Impact and Benefits
    4: [
        "Beneficiaries: Legal Metrology officers, consumers, compliant brands, and MSMEs.",
        "Validated on 140 real products (food, cosmetics, household, pet food) with "
        "403 photographs and 2,700 rule evaluations.",
        "0 false accusations and 0 known violations silently passed in the recorded "
        "campaign; 20 defects found and fixed through adversarial testing.",
        "Every finding retains the rulepack version, authority citation, evidence "
        "hash, and evaluation history.",
        "Immutable local object storage with exportable signed PDF and DOCX reports.",
        "The system answers confidently to roughly 10% character error, then stops "
        "answering rather than guessing.",
    ],
    # Slide 6 — Research and References
    5: [
        "Legal Metrology (Packaged Commodities) Rules, 2011 — compiled from 48 "
        "gazette instruments across 3 rule families (2011–2026).",
        "Rule 6(10): online display of packaged commodities — the e-commerce "
        "listing checks.",
        "Rule 7(2): MRP font-height minimum — enforced with perspective-corrected "
        "measurement from an ISO ID-1 scale reference.",
        "Repository and evidence: github.com/akshajtiwari/lmpc-compliance-engine "
        "(README.md, docs/, docs/evidence/).",
        "Preview release: v0.3.0-preview — portable Windows server and Android "
        "Field app, both published with SHA-256 checksums.",
    ],
}

IDEA_TITLE_RUN = "LMPC Compliance Engine"
IDEA_PROMISE = "Photograph a package; receive a deterministic, legally traceable finding"

# Slide 3's template heading ("Technologies to be used …") and its six dense
# bullets overflow the body box at template sizes, so that slide gets a smaller
# heading and bullet size; the others keep the template proportions.
SIZE_OVERRIDES = {2: {"heading_pt": 20, "bullet_pt": 13}}


def add_bullet(text_frame, text: str, size_pt: int) -> None:
    paragraph = text_frame.add_paragraph()
    p_pr = paragraph._p.get_or_add_pPr()
    p_pr.set("marL", "342900")
    p_pr.set("indent", "-342900")
    p_pr.append(p_pr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    p_pr.append(p_pr.makeelement(qn("a:buChar"), {"char": "•"}))
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size_pt)
    run.font.name = "Arial"
    run.font.color.rgb = TEXT_COLOR
    paragraph.alignment = PP_ALIGN.LEFT


def fill_body(slide, bullets: list[str], slide_index: int) -> None:
    box = next(shape for shape in slide.shapes
               if shape.has_text_frame and shape.name == "TextBox 8")
    text_frame = box.text_frame
    # Keep paragraph 0 (the SIH section heading); drop the template's instruction
    # bullets below it, then append this project's points.
    for paragraph in list(text_frame.paragraphs[1:]):
        paragraph._p.getparent().remove(paragraph._p)
    overrides = SIZE_OVERRIDES.get(slide_index, {})
    heading_pt = overrides.get("heading_pt")
    if heading_pt:
        for run in text_frame.paragraphs[0].runs:
            run.font.size = Pt(heading_pt)
    for bullet in bullets:
        add_bullet(text_frame, bullet, overrides.get("bullet_pt", 16))


def fill_title(slide) -> None:
    title = next(shape for shape in slide.shapes
                 if shape.has_text_frame and shape.name == "Title 1")
    runs = title.text_frame.paragraphs[0].runs
    # The template title is an empty run, a line break, then "IDEA TITLE".
    runs[0].text = IDEA_TITLE_RUN
    runs[0].font.size = Pt(36)
    runs[-1].text = IDEA_PROMISE
    runs[-1].font.size = Pt(20)


def replace_footers(slide) -> None:
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                if "SIH Idea submission" in run.text:
                    run.text = "LMPC Compliance Engine"


def delete_slide(prs, index: int) -> None:
    slide_ids = prs.slides._sldIdLst
    entry = list(slide_ids)[index]
    prs.part.drop_rel(entry.rId)
    slide_ids.remove(entry)


def main() -> None:
    prs = Presentation(str(TEMPLATE))
    slides = list(prs.slides)
    for index, bullets in BODIES.items():
        fill_body(slides[index], bullets, index)
    fill_title(slides[1])
    for index in range(6):
        replace_footers(slides[index])
    delete_slide(prs, 6)
    prs.save(str(OUTPUT))
    print(f"wrote {OUTPUT} ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")


if __name__ == "__main__":
    main()