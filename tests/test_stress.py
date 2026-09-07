"""Run the full stress suite as a test, so a regression fails CI rather than a demo."""
from lmpc.lawc.build import load
from lmpc.engine.engine import run
from stress.scenarios import build
from stress.run import verdicts, noise_sweep, sensitivity_sweep


def test_all_scenarios_meet_expectations():
    pack, unmet = load(), []
    for s in build():
        scan = s["label"].scan
        if "mutate" in s:
            s["mutate"](scan)
        got = verdicts(run(pack, scan))
        unmet += [(s["name"], c, w, got.get(c)) for c, w in s["expect"].items()
                  if got.get(c) != w]
    assert not unmet, unmet


def test_no_false_accusations_under_ocr_noise():
    assert noise_sweep(load(), levels=(0.0, 0.05, 0.1, 0.2), trials=25) <= 0.02


def test_no_violation_silently_passes():
    rows = sensitivity_sweep(load(), levels=(0.0, 0.05, 0.1), trials=25)
    assert sum(m for *_, m in rows) == 0
