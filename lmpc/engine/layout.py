"""
Assemble OCR regions into readable lines.

A recogniser returns fragments, not declarations. On real Indian labels the anchor and its
value routinely land in different regions — "NET WEIGHT :" here, "220" three centimetres
to the right — and elsewhere several declarations are merged into one space-less blob
("MRPRS.10/-(INCL.OFALLTAXES)"). An extractor that assumes anchor and value share a
region finds almost nothing on real photographs. Measured: 0 of 60 MRPs before this step.

Nothing here is machine learning. It is geometry: regions that sit on the same baseline
belong to the same statement, and a value directly beneath an anchor usually belongs to it.
"""
from __future__ import annotations
import re
from statistics import median

from .model import Token

SPACE_REPAIR = [(re.compile(r"(?<=[A-Za-z])(?=\d)"), " "),
                (re.compile(r"(?<=\d)(?=[A-Za-z])"), " "),
                (re.compile(r"(?<=[a-z])(?=[A-Z])"), " ")]


def respace(text: str) -> str:
    """Re-insert separators the recogniser dropped: MRPRS.10 -> MRP RS. 10."""
    for pat, rep in SPACE_REPAIR:
        text = pat.sub(rep, text)
    return re.sub(r"\s{2,}", " ", text)


def _same_line(a: Token, b: Token) -> bool:
    if a.panel != b.panel:
        return False
    overlap = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return overlap > 0.45 * min(a.h, b.h)


def _src(t: Token, idx: int | None = None) -> frozenset:
    return t.src or frozenset({idx if idx is not None else id(t)})


def lines(tokens: list[Token], max_gap_ratio: float = 6.0) -> list[Token]:
    """Group regions sharing a baseline into composite line tokens, left to right.

    `max_gap_ratio` caps how far apart two regions may sit and still be read as one
    statement, measured in line heights — otherwise a nutrition column on the far side of
    the pack would be glued onto the quantity declaration.
    """
    for i, t in enumerate(tokens):
        if not t.src:
            t.src = frozenset({i})
    out, used = [], set()
    for i, t in enumerate(tokens):
        if i in used:
            continue
        group = [t]
        used.add(i)
        for j, u in enumerate(tokens):
            if j in used or not _same_line(t, u):
                continue
            ref = max(group, key=lambda g: g.x)
            if u.x - (ref.x + ref.w) > max_gap_ratio * max(t.h, 1):
                continue
            group.append(u)
            used.add(j)
        group.sort(key=lambda g: g.x)
        if len(group) == 1:
            out.append(t)
            continue
        x = min(g.x for g in group); y = min(g.y for g in group)
        out.append(Token(
            text=" ".join(g.text for g in group),
            x=x, y=y,
            w=max(g.x + g.w for g in group) - x,
            h=max(g.y + g.h for g in group) - y,
            conf=min(g.conf for g in group),
            panel=t.panel,
            cap_height_px=median([g.cap_height_px or g.h for g in group]),
            src=frozenset().union(*(g.src for g in group)),
        ))
    return out


def candidates(tokens: list[Token]) -> list[Token]:
    """Every form a declaration might take: the raw region, its line, the line respaced,
    and a line joined with the one below it (labels wrap).

    Scoring picks between these; producing more candidates cannot fabricate a declaration,
    because a candidate is still just the recognised text with its real geometry.
    """
    ls = lines(tokens)
    out = list(tokens) + ls
    for t in ls:
        r = respace(t.text)
        if r != t.text:
            out.append(Token(r, t.x, t.y, t.w, t.h, t.conf, t.panel,
                             t.cap_height_px, t.src, repaired=True))
    by_panel: dict[str, list[Token]] = {}
    for t in ls:
        by_panel.setdefault(t.panel, []).append(t)
    for group in by_panel.values():
        group.sort(key=lambda g: g.y)
        for a, b in zip(group, group[1:]):
            if 0 <= b.y - (a.y + a.h) <= 1.2 * a.h:
                merged = respace(f"{a.text} {b.text}")
                out.append(Token(merged, a.x, a.y, max(a.w, b.w),
                                 b.y + b.h - a.y, min(a.conf, b.conf), a.panel,
                                 a.cap_height_px, a.src | b.src, repaired=True))
    # The same sentence recognised twice (different crops of one photograph) must not
    # stand as each other's rival: the margin rule reads them as an ambiguous call and
    # abstains on a label that says one thing. One representative is enough; the raw
    # regions stay in scan.tokens for the checks that count occurrences.
    seen: set = set()
    uniq = []
    for t in out:
        k = (t.text, t.panel)
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq
