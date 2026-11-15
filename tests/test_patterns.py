"""Task 3: India pattern recognisers and word lists."""

import random

import pytest

from selfaudit.devtools.synthetic import invalid_aadhaar, valid_aadhaar
from selfaudit.ingest.textfix import normalise
from selfaudit.perceive.patterns import build_analyzer, lexicon, recognise


@pytest.fixture(scope="module")
def analyzer():
    return build_analyzer()


def test_checksum_valid_id_is_found_and_lookalikes_are_not(analyzer):
    good = valid_aadhaar(random.Random(3))
    hits = recognise("i", f"Aadhaar {good[:4]} {good[4:8]} {good[8:]}", analyzer)
    ids = [h for h in hits if h.category == "ID_DOCUMENT"]
    assert len(ids) == 1 and ids[0].id_subtype == "government" and normalise(ids[0].value) == good
    for text in (f"Aadhaar {invalid_aadhaar(random.Random(3))}", "order no 123456789012"):
        assert not any(h.category == "ID_DOCUMENT" for h in recognise("i", text, analyzer))


@pytest.mark.parametrize("text,category", [
    ("PAN ABCPE1234F", "ID_DOCUMENT"), ("call me +91 98765 43210", "CONTACT"),
    ("mail asha@example.com", "CONTACT"), ("card 4111 1111 1111 1111", "FINANCIAL")])
def test_other_recognisers(analyzer, text, category):
    assert category in {h.category for h in recognise("i", text, analyzer)}


def test_no_names_or_places_come_from_the_rules_layer(analyzer):
    assert recognise("i", "Asha Rao lives in Hyderabad", analyzer) == []


def test_word_lists():
    assert {f.category for f in lexicon("i", "Happy birthday Amma")} == {"FAMILY_RELATION"}
    assert {f.category for f in lexicon("i", "off to Goa till Sunday ✈️")} == {"AWAY_STATUS"}
    assert lexicon("i", "great biryani") == []


def test_word_lists_read_hindi_and_telugu():
    assert {f.category for f in lexicon("i", "भाई के साथ")} == {"FAMILY_RELATION"}
    assert {f.category for f in lexicon("i", "అమ్మ పుట్టినరోజు")} == {"FAMILY_RELATION"}


def test_word_lists_do_not_fire_inside_other_words():
    # "anna" inside "Hannah", "mom" inside "moment": whole-word matching only.
    assert lexicon("i", "Hannah captured the moment") == []
