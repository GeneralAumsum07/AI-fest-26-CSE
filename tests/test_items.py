"""Task 7: the item runner's isolation, reader switches and GPU ordering."""

from helpers import F, Queue

from selfaudit.perceive.items import ItemInput, analyse_items
from selfaudit.perceive.vision import VisionOutput


def test_one_bad_image_does_not_stop_the_others(fake_backends):
    fake_backends.vision = Queue([RuntimeError(), VisionOutput(findings=[F()])])
    findings, skipped = analyse_items(
        [ItemInput("a/media-0", "a", b"x", ""), ItemInput("b/media-0", "b", b"y", "")], fake_backends)
    assert [s.ref for s in skipped] == ["a/media-0"] and [f.post_id for f in findings] == ["b"]


def test_readers_can_be_switched_off(fake_backends):
    analyse_items([ItemInput("a/media-0", "a", b"x", "call +91 98765 43210")], fake_backends,
                  use=("patterns", "lexicon"))
    assert fake_backends.vision.calls == 0 and fake_backends.captions.calls == 0


def test_vision_runs_for_every_item_before_any_other_model(fake_backends, call_log):
    analyse_items([ItemInput("a/media-0", "a", b"x", "hi"), ItemInput("b/media-0", "b", b"y", "yo")],
                  fake_backends)
    assert [c for c in call_log if c != "ner"] == ["vision", "vision", "caption", "caption", "unload"]


def test_failed_image_still_has_its_caption_read(fake_backends, call_log):
    # Plan step 3: "an image that fails still has its caption read".
    fake_backends.vision = Queue([RuntimeError()], call_log)
    analyse_items([ItemInput("a/media-0", "a", b"x", "hi")], fake_backends)
    assert fake_backends.captions.calls == 1
