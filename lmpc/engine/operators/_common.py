"""Shared machinery for the operators: the repair passes and the result builder.

Everything specific to a rule — the numbers, the regexes, the tables — arrives as
parameters from the rulepack. That separation is why a new amendment needs no code
change: the parameters reload, these functions do not move.
"""
from __future__ import annotations
import re
from ..model import Verdict, Result, Field

# Characters a recogniser routinely swaps. Correcting them can only ever DOWNGRADE a
# FAIL to INDETERMINATE - it never manufactures a PASS - so over-correcting is safe.
# G->6 and Z->2 were tried and removed: the stress run showed them corrupting "MFG02"
# into "MF 602", turning a compliant date into a violation. A repair that can damage a
# neighbouring word is worse than no repair.
_OCR_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})

_NUMERIC_RUN = re.compile(r"[0-9OolISB.,]{2,}")


def fix_numerals(text: str) -> str:
    """Undo digit/letter confusions inside numeric runs only.

    Translating the whole string would break the words the rule depends on: 'Rs.' becomes
    'R5.' and 'incl.' becomes 'inc1.', so a compliant label would still read as a
    violation. Only runs that already contain a real digit are corrected."""
    def sub(m):
        run = m.group(0)
        return run.translate(_OCR_FIX) if any(c.isdigit() for c in run) else run
    return _NUMERIC_RUN.sub(sub, text)


def repair_separators(text: str) -> str:
    """Re-insert separators a recogniser dropped: 'MFG02/2025', '2022were published'."""
    text = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", text)
    return re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)


REPAIRS = [("numeral confusions", fix_numerals),
           ("dropped separators", lambda t: repair_separators(fix_numerals(t)))]


def read_confidently(spec, f: Field, regex: str):
    """MATCH | (ONLY_AFTER_CORRECTION, how) | NO_MATCH.

    A format check may only accuse on text we are confident we read correctly. If the
    declaration matches once known OCR damage is repaired, the label is probably fine and
    the recogniser was wrong - which is a human's call, not a violation. Repair can only
    downgrade FAIL to INDETERMINATE; it never produces a PASS."""
    if re.search(regex, f.text):
        return "MATCH", None
    for how, fn in REPAIRS:
        if re.search(regex, fn(f.text)):
            return "ONLY_AFTER_CORRECTION", how
    return "NO_MATCH", None


def r(spec, verdict: Verdict, reason: str, **ev) -> Result:
    return Result(check=spec["check"], clause=spec["clause"], verdict=verdict,
                  reason=reason, citation=spec.get("citation", {}), evidence=ev)


def lexicon_match(text: str) -> bool:
    from .. import lexicon
    return lexicon.match(text, "mrp") >= lexicon.THRESHOLD