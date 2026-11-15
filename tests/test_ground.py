"""Task 6: grounding and two-support confidence."""

import pytest

from helpers import R
from selfaudit.perceive.ground import ground


def G(raws, caption=""):
    return ground(raws, {"p/media-0": caption}, {"p/media-0": "p"})


def test_vision_plus_checksum_is_confirmed():
    f, = G([R("vision", "ID_DOCUMENT", extracted_text="2345 6789 0123", id_subtype="government"),
            R("patterns", "ID_DOCUMENT", value="2345 6789 0123")])
    assert (f.confidence, sorted(f.supports), f.value) == ("confirmed", ["patterns", "vision"], "2345 6789 0123")


def test_one_reader_is_only_likely():
    assert G([R("vision", "TRAVEL_DOC", model_confidence="medium")])[0].confidence == "likely"


def test_low_confidence_alone_is_unsure():
    assert G([R("vision", "ID_DOCUMENT", model_confidence="low")])[0].confidence == "unsure"


def test_an_invented_value_is_dropped_and_stops_counting():
    f, = G([R("caption", "FAMILY_RELATION", value="Lakshmi")], caption="Happy birthday Amma")
    assert f.value is None and f.confidence == "unsure"


def test_caption_plus_word_list_is_confirmed():
    f, = G([R("caption", "FAMILY_RELATION", value="Amma"), R("lexicon", "FAMILY_RELATION")], caption="Happy birthday Amma")
    assert f.confidence == "confirmed"


def test_college_id_counts_as_institution_not_id():
    assert [f.category for f in G([R("vision", "ID_DOCUMENT", id_subtype="institutional")])] == ["INSTITUTION"]


@pytest.mark.parametrize("mc,conf", [("high", "confirmed"), ("medium", "likely"), ("low", "unsure")])
def test_faces_follow_the_vision_model(mc, conf):
    assert G([R("vision", "FACE_CLEAR", model_confidence=mc)])[0].confidence == conf


def test_user_reports_are_confirmed():
    assert G([R("user", "CONTACT")])[0].confidence == "confirmed"


def test_value_never_reaches_json():
    f, = G([R("patterns", "CONTACT", value="98765 43210")], caption="call 98765 43210")
    assert f.value == "98765 43210" and "98765" not in f.model_dump_json()
