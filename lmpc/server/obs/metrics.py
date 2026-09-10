"""Counters the acceptance gates read (Part 19, SC-4).

`lmpc_fail_without_coverage_total` MUST stay 0 for the life of the deployment: a FAIL
issued without an asserted coverage flag is the one way this system can accuse
someone on evidence it does not hold."""
from __future__ import annotations
from collections import Counter
from threading import Lock

_counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
_stage_count: Counter[str] = Counter()
_stage_sum: Counter[str] = Counter()
_gauges: dict[str, int] = {
    "lmpc_fail_without_coverage_total": 0, "lmpc_chain_incomplete": 0,
}
_lock = Lock()


def inc(name: str, **labels: str) -> None:
    with _lock:
        _counters[(name, tuple(sorted(labels.items())))] += 1


def inc_verdict(verdict: str, coverage_asserted: bool, check: str = "") -> None:
    inc("lmpc_verdict_total", check=check, outcome=verdict)
    if verdict == "FAIL" and not coverage_asserted:
        with _lock:
            _gauges["lmpc_fail_without_coverage_total"] += 1


def observe_stage(stage: str, seconds: float) -> None:
    with _lock:
        _stage_count[stage] += 1
        _stage_sum[stage] += seconds


def set_chain_complete(complete: bool) -> None:
    with _lock:
        _gauges["lmpc_chain_incomplete"] = int(not complete)


def exposition() -> str:
    with _lock:
        lines = [f"# TYPE {name} gauge\n{name} {value}"
                 for name, value in sorted(_gauges.items())]
        for (name, labels), value in sorted(_counters.items()):
            rendered = ",".join(f'{key}="{_escape(label)}"' for key, label in labels)
            suffix = f"{{{rendered}}}" if rendered else ""
            lines.append(f"# TYPE {name} counter\n{name}{suffix} {value}")
        for stage in sorted(_stage_count):
            label = f'{{stage="{_escape(stage)}"}}'
            lines.append("# TYPE lmpc_pipeline_duration_seconds summary\n"
                         f"lmpc_pipeline_duration_seconds_count{label} {_stage_count[stage]}\n"
                         f"lmpc_pipeline_duration_seconds_sum{label} {_stage_sum[stage]:.6f}")
    return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
