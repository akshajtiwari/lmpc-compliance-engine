"""Selection-rule tests. The recogniser itself needs its model files; the policy does not."""
import io

from PIL import Image

from lmpc.engine.ocr import prepare
from lmpc.engine.ocr_select import _dev_fraction, pick


def test_the_specialist_wins_when_only_it_carries_the_script():
    en = ("00000.00000 2", 0.87)          # the bundled model's Hindi output is garbage
    dev = ("अधिकतम खुदरा मूल्य", 0.72)
    assert pick(en, dev) == dev


def test_the_specialist_does_not_touch_latin_regions():
    en = ("MRP Rs. 45.00", 0.75)
    dev = ("M 4S.30", 0.81)               # the specialist is slightly worse on English
    assert pick(en, dev) == en


def test_absent_readings_fall_to_whichever_model_answered():
    assert pick(None, ("मूल्य", 0.5)) == ("मूल्य", 0.5)
    assert pick(("MRP", 0.5), None) == ("MRP", 0.5)
    assert pick(None, None) is None


def test_dev_fraction_measures_devanagari_glyphs_only():
    assert _dev_fraction("अधिकतम") == 1.0
    assert _dev_fraction("MRP 45") == 0.0
    assert _dev_fraction("  ") == 0.0


def test_object_store_bytes_follow_the_same_bounded_decode_path():
    encoded = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(encoded, "PNG")
    frame = prepare(encoded.getvalue(), max_edge=50)
    assert frame.shape == (25, 50, 3)
