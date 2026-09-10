"""Counters the acceptance gates read (Part 19, SC-4).

`lmpc_fail_without_coverage_total` MUST stay 0 for the life of the deployment: a FAIL
issued without an asserted coverage flag is the one way this system can accuse
someone on evidence it does not hold."""
from __future__ import annotations
from collections import Counter

_verdicts: Counter[str] = Counter()
_gauges: dict[str, int] = {"lmpc_fail_without_coverage_total": 0}


def inc_verdict(verdict: str, coverage_asserted: bool) -> None:
    _verdicts[verdict] += 1
    if verdict == "FAIL" and not coverage_asserted:
        _gauges["lmpc_fail_without_coverage_total"] += 1


def exposition() -> str:
    lines = [f"{k} {v}" for k, v in _gauges.items()]
    lines += [f'lmpc_verdict_total{{verdict="{v}"}} {n}' for v, n in sorted(_verdicts.items())]
    return "\n".join(lines) + "\n"