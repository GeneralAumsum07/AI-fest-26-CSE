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


def _contact(text, checked):
    return ground([R("vision", "CONTACT", extracted_text=text, model_confidence="high")],
                  {"p/media-0": ""}, {"p/media-0": "p"}, checked=checked)[0]


def test_a_number_the_phone_checker_rejected_is_not_contact():
    # Debugged 2026-11-15: qwen3.5:4b called a meme's "3947 6152 3589" (fails
    # the Aadhaar checksum, not an Indian phone shape) a phone number, and
    # the vision claim alone made it "likely". When the India-only phone
    # recogniser read the same digits and found no phone, the two readers
    # disagree, and spec 264 says disagreement lowers confidence.
    assert _contact("3947 6152 3589", checked={"p/media-0"}).confidence == "unsure"


def test_without_the_phone_checker_vision_alone_stays_likely():
    # The vision-only ablation (B1) runs no patterns: nothing contradicted it.
    assert _contact("3947 6152 3589", checked=set()).confidence == "likely"


def test_a_written_address_is_not_downgraded():
    # No recogniser here knows Indian addresses, so silence from it is not a
    # contradiction; only a long digit run it rejected is.
    assert _contact("12 MG Road, Indiranagar, Bengaluru 560038", checked={"p/media-0"}).confidence == "likely"


def test_a_real_phone_is_still_confirmed():
    f, = ground([R("vision", "CONTACT", extracted_text="call 90000 47118"),
                 R("patterns", "CONTACT", value="90000 47118")],
                {"p/media-0": ""}, {"p/media-0": "p"}, checked={"p/media-0"})
    assert f.confidence == "confirmed"


def test_college_id_counts_as_institution_not_id():
    assert [f.category for f in G([R("vision", "ID_DOCUMENT", id_subtype="institutional")])] == ["INSTITUTION"]


@pytest.mark.parametrize("mc,conf", [("high", "confirmed"), ("medium", "likely"), ("low", "unsure")])
def test_faces_follow_the_vision_model(mc, conf):
    assert G([R("vision", "FACE_CLEAR", model_confidence=mc)])[0].confidence == conf


def test_user_reports_are_confirmed():
    assert G([R("user", "CONTACT")])[0].confidence == "confirmed"


@pytest.mark.parametrize("reader", ["vision", "caption", "ner"])
def test_model_written_text_never_becomes_the_finding_text(reader):
    # A model's own sentence can carry the very name and number being flagged;
    # the finding's text must come from a fixed phrase, never from the model.
    leaky = "Aadhaar card of Priya Sharma, 2345 6789 0123"
    f, = G([R(reader, "ID_DOCUMENT", what=leaky, value="Priya Sharma")], caption="Priya Sharma 2345 6789 0123")
    assert "Priya" not in f.what and "2345" not in f.what and f.what


def test_fixed_reader_phrases_are_kept():
    # Pattern and word-list phrases are written by us, so they stay as they are.
    f, = G([R("patterns", "CONTACT", what="a phone number", value="98765 43210")], caption="call 98765 43210")
    assert f.what == "a phone number"


def test_value_never_reaches_json():
    f, = G([R("patterns", "CONTACT", value="98765 43210")], caption="call 98765 43210")
    assert f.value == "98765 43210" and "98765" not in f.model_dump_json()


def test_a_short_public_number_is_not_your_contact():
    # dev-031: "women's helpline 181, save it". The caption reader called 181
    # a contact. No personal phone has fewer than 10 digits; 100, 112, 181 and
    # 1098 are public short codes, and knowing them tells a scammer nothing.
    f, = G([R("caption", "CONTACT", value="181")], caption="women's helpline 181, save it")
    assert f.confidence == "unsure"


def test_an_email_or_address_from_the_caption_still_counts():
    f, = G([R("caption", "CONTACT", value="asha@example.com")], caption="mail me at asha@example.com")
    assert f.confidence == "likely"
