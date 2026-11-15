"""Task 10: ingredient roll-up and recipe levels."""

from datetime import datetime, timezone

import pytest
from helpers import Fd

from selfaudit.models import Ingredient, Post, Profile, VoiceResult
from selfaudit.recipes import evaluate
from selfaudit.rollup import roll_up

UTC = timezone.utc
NO_VOICE = VoiceResult(clean_seconds=0, band="none", enrolled=False, seconds_by_post={})


def ing(category, confidence="confirmed", posts=("p1",), band=None):
    return Ingredient(category=category, confidence=confidence, post_ids=list(posts), band=band)


def prof(private=False, name="Asha Rao"):
    old = [Post(post_id=f"p{i}", source="post", caption="", created=datetime(2026, 10, 1, tzinfo=UTC), media=[])
           for i in range(1, 10)]
    recent = Post(post_id="recent", source="post", caption="", created=datetime(2026, 11, 10, tzinfo=UTC), media=[])
    return Profile(name=name, username="asha", bio="", is_private=private, posts=[recent, *old],
                   reference_date=datetime(2026, 11, 12, tzinfo=UTC))


def level(recipe_id, ingredients, unsure=(), **prof_kw):
    for r in evaluate(list(ingredients), list(unsure), prof(**prof_kw)):
        if r.recipe_id == recipe_id:
            return (r.level, r.not_sure)
    return None


VOICE_HI = ing("VOICE", band="high"); FAM = ing("FAMILY_RELATION"); INST = ing("INSTITUTION")
FACES = ing("FACE_CLEAR", posts=("p1", "p2", "p3")); ID = ing("ID_DOCUMENT")


@pytest.mark.parametrize("ingredients,expected", [
    ([VOICE_HI, FAM, INST], ("high", False)),
    ([ing("VOICE", "likely", band="moderate"), FAM, INST], ("medium", False)),     # no enrolment
    ([VOICE_HI, FAM], ("medium", False)),                                          # one slot empty
    ([FAM, INST], ("low", False)),                                                 # core slot empty
    ([ing("VOICE", band="low"), FAM, INST], ("low", False)),                       # too little voice to count
    ([INST], ("low", False)),
    ([], None),
])
def test_r1_levels(ingredients, expected):
    assert level("R1", ingredients) == expected


@pytest.mark.parametrize("ingredients,expected", [
    ([ID], ("high", False)), ([ing("ID_DOCUMENT", "likely")], ("medium", False)), ([FACES, FAM], None)])
def test_r3_levels(ingredients, expected):
    assert level("R3", ingredients) == expected


def test_profile_copy_never_goes_above_medium_and_needs_several_faces():
    assert level("R2", [FACES, INST]) == ("medium", False)
    assert level("R2", [ing("FACE_CLEAR", posts=("p1",)), INST]) == ("low", False)
    assert level("R2", [FACES]) == ("medium", False)             # faces + name, one slot empty
    assert level("R2", []) is None                               # a name alone shows nothing


def test_private_account_lowers_everything_one_level():
    assert level("R1", [VOICE_HI, FAM, INST], private=True) == ("medium", False)
    assert level("R3", [ID], private=True) == ("medium", False)
    assert level("R1", [INST], private=True) == ("low", False)


def test_an_unsure_finding_makes_the_recipe_not_sure_without_raising_it():
    maybe_id = Fd("p9/media-0", "ID_DOCUMENT", "unsure")
    out = evaluate([], [maybe_id], prof())
    assert [(r.recipe_id, r.level, r.not_sure, r.look_at) for r in out] == [("R3", None, True, [maybe_id.finding_id])]


def test_amplifiers_are_listed_but_change_nothing():
    plain = evaluate([VOICE_HI, FAM, INST], [], prof())[0]
    away = evaluate([VOICE_HI, FAM, INST, ing("AWAY_STATUS", posts=("recent",))], [], prof())[0]
    assert plain.level == away.level == "high" and away.amplifiers == ["AWAY_STATUS"]


def test_old_away_posts_are_not_amplifiers():
    out = evaluate([VOICE_HI, FAM, INST, ing("AWAY_STATUS", posts=("p1",))], [], prof())[0]
    assert out.amplifiers == []


def test_roll_up_keeps_stories_and_unsure_findings_out():
    ingredients, unsure, past = roll_up(
        [Fd("post-0001/media-0", "FAMILY_RELATION", "confirmed"), Fd("story-0001/media-0", "ID_DOCUMENT", "confirmed"),
         Fd("post-0002/media-0", "CONTACT", "unsure")], NO_VOICE, prof())
    assert [i.category for i in ingredients] == ["FAMILY_RELATION"] and len(unsure) == 1 and len(past) == 1


def test_a_document_nobody_could_read_is_not_sure_rather_than_a_risk():
    seen_not_read = Fd("post-0003/media-0", "ID_DOCUMENT", "likely", value=None)
    ingredients, unsure, _ = roll_up([seen_not_read], NO_VOICE, prof())
    assert ingredients == [] and unsure == [seen_not_read]
    assert [(r.recipe_id, r.level, r.not_sure) for r in evaluate(ingredients, unsure, prof())] == [("R3", None, True)]


def test_voice_becomes_an_ingredient_when_there_is_some():
    v = VoiceResult(clean_seconds=40, band="high", enrolled=True, seconds_by_post={"reel-0001": 40})
    ingredients, _, _ = roll_up([], v, prof())
    assert [(i.category, i.confidence, i.band) for i in ingredients] == [("VOICE", "confirmed", "high")]
