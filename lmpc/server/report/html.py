"""Sections to HTML, for WeasyPrint."""
from __future__ import annotations

from html import escape
from pathlib import Path

CSS = Path(__file__).with_name("report.css")

_TONE = {"COMPLIANT": "pass", "NON_COMPLIANT": "fail", "SYSTEM_ERROR": "fail"}


def render(sections: list[dict], *, kind: str) -> str:
    body = "".join(_section(item) for item in sections)
    mark = ('<div class="watermark">NOT LEGALLY FINALISED</div>'
            if kind == "FIELD" else "")
    return (f'<!doctype html><meta charset="utf-8"><style>{CSS.read_text()}</style>'
            f"{mark}{body}")


def _section(section: dict) -> str:
    return _RENDERERS[section["kind"]](section)


def _cover(section: dict) -> str:
    tone = _TONE.get(section["verdict"], "unclear")
    rows = "".join(f"<div><dt>{escape(str(label))}</dt>"
                   f"<dd>{escape(str(value))}</dd></div>"
                   for label, value in section["rows"])
    banner = (f'<p class="banner">{escape(section["kind_label"])}</p>'
              if "not legally" in section["kind_label"].lower() else "")
    return (f"<h1>{escape(section['title'])}</h1>"
            f'<p class="lede">Legal Metrology (Packaged Commodities) Rules, 2011</p>'
            f'{banner}<div class="verdict {tone}">'
            f'<div class="word">{escape(section["verdict_word"])}</div>'
            f'<div class="code">{escape(str(section["verdict"] or ""))}</div></div>'
            f'<dl class="kv">{rows}</dl>')


def _counts(section: dict) -> str:
    items = "".join(
        f"<li><b>{count}</b> {escape(section['words'].get(outcome, outcome).lower())}</li>"
        for outcome, count in sorted(section["counts"].items()))
    note = f'<p class="note">{escape(section["note"])}</p>' if section["note"] else ""
    return (f"<h2>{escape(section['title'])}</h2>"
            f'<ul class="counts">{items}</ul>{note}')


def _table(section: dict) -> str:
    head = "".join(f"<th>{escape(column)}</th>" for column in section["columns"])
    body = "".join("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row)
                   + "</tr>" for row in section["rows"])
    if not section["rows"]:
        return ""
    return (f"<h2>{escape(section['title'])}</h2>"
            f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def _images(section: dict) -> str:
    panels = "".join(
        '<div class="panel">'
        + (f'<img src="{item["data_uri"]}">' if item.get("data_uri") else "")
        + f'<div class="label">{escape(item["panel"])}</div>'
        + f'<div class="hash">{escape(item["sha256"])}</div></div>'
        for item in section["images"])
    return (f"<h2>{escape(section['title'])}</h2>"
            f'<div class="panels">{panels}</div>'
            f'<p class="note">{escape(section["note"])}</p>')


def _notapplicable(section: dict) -> str:
    if not section["items"]:
        return ""
    joined = ", ".join(escape(str(item)) for item in section["items"])
    return (f"<h2>{escape(section['title'])}</h2>"
            f'<p class="note">These were evaluated and found not to apply to this '
            f"package: {joined}.</p>")


def _list(section: dict) -> str:
    items = "".join(f"<li>{escape(str(item))}</li>" for item in section["items"])
    return f"<h2>{escape(section['title'])}</h2><ul>{items}</ul>"


def _notes(section: dict) -> str:
    items = "".join(
        f'<p>{escape(note["body"])}<br><span class="note">'
        f'{escape(note.get("author") or "")} · {escape(note.get("created_at") or "")}'
        "</span></p>" for note in section["notes"])
    return f"<h2>{escape(section['title'])}</h2>{items}"


def _signoff(section: dict) -> str:
    return (f"<h2>{escape(section['title'])}</h2>"
            '<div class="signoff"><div>Name</div><div>Signature</div>'
            "<div>Date</div></div>")


def _integrity(section: dict) -> str:
    rows = "".join(f"<div>{escape(str(label))}: {escape(str(value))}</div>"
                   for label, value in section["rows"] if value)
    return (f"<h2>{escape(section['title'])}</h2>"
            f'<div class="integrity">{rows}</div>'
            '<p class="note">The content hash covers the findings, not this layout: the '
            "same inspection re-rendered later produces the same hash.</p>")


_RENDERERS = {"cover": _cover, "counts": _counts, "table": _table, "images": _images,
              "notapplicable": _notapplicable, "list": _list, "notes": _notes, "signoff": _signoff,
              "integrity": _integrity}
