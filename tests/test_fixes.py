"""Task 11: fix bundles and greedy ranking.

Every ranking test injects `drops`, a test-local weight, so these hold
whatever the real fix_weight turns out to be.
"""

from datetime import datetime, timezone

import pytest
from helpers import Fd

from selfaudit.fixes import candidate_fixes, private_would_lower, rank_fixes
from selfaudit.models import Post, Profile, VoiceResult
from selfaudit.perceive.voice import band_for
from selfaudit.recipes import LEVEL_RANK

UTC = timezone.utc


def drops(fix, before, after):
    """Total level steps lowered across all recipes."""
    now = {r.recipe_id: r.level for r in after}
    return sum(LEVEL_RANK[r.level] - LEVEL_RANK[now.get(r.recipe_id)] for r in before)


@pytest.fixture
def scenario():
    def make(id_posts=(), family_posts=(), institution_posts=(), face_posts=(), reels=None, private=False):
        findings = [Fd(f"{p}/media-0", "ID_DOCUMENT", "confirmed", value="234123412346") for p in id_posts]
        findings += [Fd(f"{p}/media-0", "FAMILY_RELATION", "confirmed", supports=["caption"]) for p in family_posts]
        findings += [Fd(f"{p}/media-0", "INSTITUTION", "confirmed", supports=["caption"]) for p in institution_posts]
        findings += [Fd(f"{p}/media-0", "FACE_CLEAR", "confirmed") for p in face_posts]
        reels = reels or {}
        total = sum(reels.values())
        voice = VoiceResult(clean_seconds=total, band=band_for(total), enrolled=True, seconds_by_post=dict(reels))
        ids = [*id_posts, *family_posts, *institution_posts, *face_posts]
        posts = [Post(post_id=p, source="post", caption="", created=datetime(2026, 11, 1, tzinfo=UTC), media=[])
                 for p in dict.fromkeys(ids)]
        posts += [Post(post_id=r, source="reel", caption="", created=datetime(2026, 11, 1, tzinfo=UTC), media=[])
                  for r in reels]
        profile = Profile(name="Asha Rao", username="asha", bio="", is_private=private, posts=posts,
                          reference_date=datetime(2026, 11, 12, tzinfo=UTC))
        return findings, voice, profile
    return make


def test_removing_the_id_post_ends_the_document_risk(scenario):
    fixes = rank_fixes(*scenario(id_posts=["p1"], family_posts=["p2", "p3"], reels={"r1": 25, "r2": 15, "r3": 10}),
                       weight=drops)
    first = fixes[0]
    assert (first.post_ids, first.action, first.ends) == (["p1"], "remove", ["R3"])


def test_an_ingredient_in_several_posts_needs_all_of_them(scenario):
    # Ruling (ledger): asserted on candidate_fixes, not rank_fixes. Under the
    # plan's greedy, once the voice fix is taken, dropping family alone leaves
    # institution in the same R1 slot and changes no level, so it is (rightly)
    # never ranked. The bundling property is a property of the candidates.
    fixes = candidate_fixes(*scenario(family_posts=["p2", "p3"], reels={"r1": 40}, institution_posts=["p4"]))
    assert any(sorted(f.post_ids) == ["p2", "p3"] and f.action == "edit_caption" for f in fixes)


def test_voice_fix_is_the_fewest_reels_that_empty_the_voice_slot(scenario):
    fixes = rank_fixes(*scenario(family_posts=["p2"], institution_posts=["p4"], reels={"r1": 25, "r2": 15, "r3": 3}),
                       weight=drops)
    voice_fix = next(f for f in fixes if f.action == "archive")
    assert voice_fix.post_ids == ["r1", "r2"] and voice_fix.weakens == ["R1"]    # 43 s -> 3 s; r3 can stay


def test_going_private_is_offered_separately(scenario):
    assert private_would_lower(*scenario(id_posts=["p1"])) == ["R3"]
    assert private_would_lower(*scenario(id_posts=["p1"], private=True)) == []


def test_nothing_useless_and_no_face_posts_are_suggested(scenario):
    fixes = rank_fixes(*scenario(face_posts=["f1", "f2", "f3"], institution_posts=["p4"]), weight=drops)
    assert all("f1" not in f.post_ids for f in fixes) and all(f.ends or f.weakens for f in fixes)


def test_at_most_five(scenario):
    assert len(rank_fixes(*scenario(id_posts=[f"p{i}" for i in range(9)]), weight=drops)) <= 5


def test_a_photographed_detail_is_cropped_not_captioned(scenario):
    findings, voice, profile = scenario(institution_posts=["p4"])
    findings = [f.model_copy(update={"supports": ["vision"]}) for f in findings]
    assert [f.action for f in candidate_fixes(findings, voice, profile)] == ["crop"]
