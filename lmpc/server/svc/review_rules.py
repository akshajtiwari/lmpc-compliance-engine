"""What a scan patch is allowed to invalidate.

Shared by both stores and the route, so the database path and the in-memory path cannot
disagree about whether a correction made a standing verdict stale.
"""
from __future__ import annotations

#: Fields the rule engine actually reads. Changing one of these makes a verdict stale.
#: An officer's remark is an observation about the inspection, not an input to it, so
#: typing one must not throw away an evaluation that has already run.
EVALUATION_INPUTS = frozenset({"product_id", "package_shape", "category", "dimensions"})


def affects_evaluation(changes: dict) -> bool:
    return bool(EVALUATION_INPUTS & set(changes))
