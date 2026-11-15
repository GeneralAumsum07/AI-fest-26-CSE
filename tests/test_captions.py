"""Task 5: caption reader and the independent name cross-check (both faked)."""

import pytest

from helpers import FakeCaptions, FakeNames
from selfaudit.perceive.captions import CaptionFinding, is_latin, read_caption


def test_caption_findings_keep_the_value_from_the_caption():
    b = FakeCaptions([CaptionFinding(category="INSTITUTION", what="college named", value="Mahindra University")])
    out = read_caption("i", "First day at Mahindra University!", b, FakeNames([("Mahindra University", "organization")]))
    assert {(f.reader, f.category, f.value) for f in out} == {
        ("caption", "INSTITUTION", "Mahindra University"), ("ner", "INSTITUTION", "Mahindra University")}


def test_ner_only_backs_a_finding_it_overlaps():
    b = FakeCaptions([CaptionFinding(category="FAMILY_RELATION", what="mother", value="Amma")])
    out = read_caption("i", "Happy birthday Amma, from Hyderabad", b, FakeNames([("Hyderabad", "location")]))
    assert [f.reader for f in out] == ["caption"]


def test_no_second_reader_for_non_latin_captions():
    names = FakeNames([("अम्मा", "person")])
    read_caption("i", "जन्मदिन मुबारक अम्मा", FakeCaptions([]), names)
    assert names.calls == 0 and is_latin("Happy birthday") and not is_latin("జన్మదిన శుభాకాంక్షలు")


def test_empty_caption_calls_nothing():
    b = FakeCaptions([])
    assert read_caption("i", "  ", b, None) == [] and b.calls == 0


@pytest.mark.gpu
def test_real_gliner_loads_and_finds_a_name():
    # The fakes above cannot catch a model that fails to load. With
    # transformers 5, GLiNER's mDeBERTa tokenizer is rebuilt through
    # SentencePieceExtractor, which needs protobuf; without it every caption
    # that reaches the name reader became a caption_error. (Marked gpu as the
    # opt-in "real models" group, although GLiNER itself runs on the CPU.)
    from selfaudit.perceive.captions import GlinerNames

    found = GlinerNames().names("My brother Ravi studies at Mahindra University.")
    assert ("Ravi", "person") in found


def test_a_crashing_name_reader_keeps_the_caption_findings():
    # The name reader (GLiNER) only adds a second support. If it crashes, the
    # caption model's findings are still good; losing them turned one optional
    # helper's failure into a whole "couldn't check" caption.
    class Broken:
        def names(self, text):
            raise RuntimeError("gliner died")
    b = FakeCaptions([CaptionFinding(category="FAMILY_RELATION", what="mother", value="Amma")])
    out = read_caption("i", "Happy birthday Amma", b, Broken())
    assert [(r.reader, r.value) for r in out] == [("caption", "Amma")]
