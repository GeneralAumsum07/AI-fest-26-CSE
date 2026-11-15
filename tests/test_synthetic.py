"""Task 2: synthetic documents, labelled sets and the freeze manifest."""

import random

from selfaudit.devtools.freeze import freeze, verify
from selfaudit.devtools.synthetic import (
    MVP_ITEM_CATEGORIES, SPECIMEN, generate_set, invalid_aadhaar, load_labels,
    make_document, valid_aadhaar, verhoeff_ok,
)


def test_valid_numbers_pass_the_recogniser_and_invalid_ones_fail():
    from presidio_analyzer.predefined_recognizers import InAadhaarRecognizer
    r, rng = InAadhaarRecognizer(), random.Random(7)
    assert all(r.validate_result(valid_aadhaar(rng)) for _ in range(50))
    assert not any(r.validate_result(invalid_aadhaar(rng)) for _ in range(50))


def test_our_checksum_agrees_with_itself():
    rng = random.Random(2)
    assert all(verhoeff_ok(valid_aadhaar(rng)) for _ in range(50))
    assert not any(verhoeff_ok(invalid_aadhaar(rng)) for _ in range(50))


def test_documents_report_what_they_print(tmp_path):
    doc, values = make_document("aadhaar", random.Random(1))
    assert len(values["number"]) == 12 and values["specimen"] == SPECIMEN


def test_heldout_set_meets_the_spec_quotas(tmp_path, tiny_sources):
    labels = generate_set(tmp_path, split="heldout", seed=1, sources=tiny_sources)
    risky = [l for l in labels if l.categories]
    benign = [l for l in labels if not l.categories]
    assert len(risky) >= 35 and len(benign) >= 25
    assert sum(l.hard_negative for l in benign) >= 12
    assert all(sum(c in l.categories for l in risky) >= 4 for c in MVP_ITEM_CATEGORIES)
    assert load_labels(tmp_path) == labels


def test_same_seed_gives_the_same_set(tmp_path, tiny_sources):
    a = generate_set(tmp_path / "a", split="dev", seed=5, sources=tiny_sources)
    b = generate_set(tmp_path / "b", split="dev", seed=5, sources=tiny_sources)
    assert [(l.caption, l.categories, l.values) for l in a] == [(l.caption, l.categories, l.values) for l in b]


def test_dev_and_heldout_share_no_numbers(tmp_path, tiny_sources):
    dev = generate_set(tmp_path / "d", split="dev", seed=11, sources=tiny_sources)
    held = generate_set(tmp_path / "h", split="heldout", seed=23, sources=tiny_sources)
    nums = lambda ls: {l.values["number"] for l in ls if "number" in l.values}
    assert not nums(dev) & nums(held)


def test_freeze_detects_any_change(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"1")
    freeze(tmp_path)
    assert verify(tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"2")
    assert not verify(tmp_path)


def test_every_hard_negative_poster_is_legible():
    # A hard negative only tests the reader if its text can be read: a dark
    # card with dark ink is a blank picture, not a "looks risky" case.
    from PIL import Image, ImageStat
    from selfaudit.devtools.synthetic import _HARD_KINDS, _hard_negative

    bg = Image.new("RGB", (600, 400), (120, 120, 120))
    for kind in _HARD_KINDS:
        img, _ = _hard_negative(kind, random.Random(1), bg)
        if kind == "occluded_id":
            continue  # a composited photo, not a poster
        grey = img.convert("L")
        card = grey.getpixel((5, 5))
        text = ImageStat.Stat(grey.crop((40, 60, 760, 500))).extrema[0]
        far = max(abs(card - text[0]), abs(card - text[1]))
        assert far >= 100, f"{kind}: ink differs from the card by only {far} grey levels"
