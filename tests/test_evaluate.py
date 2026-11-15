"""Task 15: the interval, the ablation's isolation, and the freeze guard."""

import pytest

from selfaudit.devtools.evaluate import _meets, main, run_system, wilson
from selfaudit.devtools.freeze import freeze


def test_wilson_interval():
    lo, hi = wilson(0, 25); assert lo == 0 and 0.13 < hi < 0.14
    lo, hi = wilson(30, 35); assert 0.70 < lo < 0.72 and 0.93 < hi < 0.95
    assert wilson(0, 0) == (0.0, 1.0)


def test_rules_only_never_touches_a_model(tmp_path, fake_backends, tiny_split):
    run_system("B0", tiny_split, fake_backends)
    assert fake_backends.vision.calls == 0 and fake_backends.captions.calls == 0


def test_heldout_will_not_run_if_it_changed_since_the_freeze(tmp_path, fake_backends, tiny_split):
    freeze(tiny_split); (tiny_split / "labels.json").write_text("[]")
    with pytest.raises(SystemExit):
        main(["--split", str(tiny_split), "--out", str(tmp_path), "--frozen"], backends=fake_backends)


def test_persona_expectations():
    assert _meets("high", "high") and not _meets("medium", "high")
    assert _meets(None, None) and not _meets("low", None)
    assert _meets("medium", "max:medium") and _meets(None, "max:medium") and not _meets("high", "max:medium")
