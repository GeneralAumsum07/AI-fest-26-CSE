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


def test_a_carousel_caption_is_reported_once(fake_backends):
    # Every image of a 3-image carousel carries the same caption; the user
    # must see "Amma" flagged once, not three identical lines.
    items = [ItemInput(f"a/media-{k}", "a", None, "Happy birthday Amma") for k in range(3)]
    findings, _ = analyse_items(items, fake_backends, use=("patterns", "lexicon"))
    assert [f.category for f in findings].count("FAMILY_RELATION") == 1


def test_failed_image_still_has_its_caption_read(fake_backends, call_log):
    # Plan step 3: "an image that fails still has its caption read".
    fake_backends.vision = Queue([RuntimeError()], call_log)
    analyse_items([ItemInput("a/media-0", "a", b"x", "hi")], fake_backends)
    assert fake_backends.captions.calls == 1


def test_vision_contact_the_phone_checker_rejected_is_unsure(fake_backends, analyzer):
    # The runner must tell grounding which items the phone checker actually
    # read; that is what lets rule 7 tell "checked, no phone" from "never
    # checked". The meme from the careful persona, end to end.
    fake_backends.analyzer = analyzer
    fake_backends.vision = Queue([VisionOutput(findings=[F(extracted_text="3947 6152 3589")])])
    findings, _ = analyse_items([ItemInput("a/media-0", "a", b"x", "lol")], fake_backends,
                                use=("vision", "patterns"))
    assert [(f.category, f.confidence) for f in findings] == [("CONTACT", "unsure")]


def test_a_pattern_error_does_not_count_as_checked(fake_backends):
    # If the checker crashed it said nothing, so it contradicts nothing.
    class Broken:
        def analyze(self, *a, **k):
            raise RuntimeError
    fake_backends.analyzer = Broken()
    fake_backends.vision = Queue([VisionOutput(findings=[F(extracted_text="3947 6152 3589")])])
    findings, _ = analyse_items([ItemInput("a/media-0", "a", b"x", "lol")], fake_backends,
                                use=("vision", "patterns"))
    assert [(f.category, f.confidence) for f in findings] == [("CONTACT", "likely")]
