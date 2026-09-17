"""A read-only view of the compiled rulepack for the management surface.

The rulepack is the authority and the engine remains the decision-maker; this
module only describes what is loaded — which version, which instruments, which
checks and gates — so a reviewer can see the law the engine applies without
reading the compiled JSON.
"""
from __future__ import annotations

from typing import Any

from .rule_help import rule_detail


def overview(pack: dict[str, Any]) -> dict[str, Any]:
    """Summarise the whole loaded rulepack: its identity, gates and checks."""
    checks = []
    for spec in pack["checks"]:
        detail = rule_detail(pack, spec["check"])
        checks.append({
            "check": detail["check"],
            "title": detail["title"],
            "clause": detail["clause"],
            "operator": spec.get("operator"),
            "requirement": detail["requirement"],
            "evidence_needed": detail["evidence_needed"],
            "effective_from": detail["effective_from"],
            "authority": detail["authority"],
        })
    return {
        "rulepack": {
            "version": pack["version"],
            "built_at": pack["built_at"],
            "sha256": pack["sha256"],
            "check_count": len(pack["checks"]),
            "gate_count": len(pack["gates"]),
            "unverified_bindings": len(pack.get("unverified_bindings", [])),
        },
        "gates": [
            {
                "gate": gate["id"],
                "clause": gate["clause"],
                "operator": gate["operator"],
                "authority": gate.get("citation") or {},
            }
            for gate in pack["gates"]
        ],
        "checks": checks,
    }