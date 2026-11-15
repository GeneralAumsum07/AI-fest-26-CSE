"""Findings -> ingredients: what an attacker could actually collect (spec 7.6).

Three piles come out:
- ingredients: one per category, the evidence recipes are built from;
- unsure: things the app saw but could not stand behind (the "Not sure" list);
- past_exposure: anything from stories. Stories expire after 24 h, so they are
  shown as "was public once" and never feed a current risk.
"""

from __future__ import annotations

from selfaudit.models import Finding, Ingredient, Profile, VoiceResult

_CONF_RANK = {"unsure": 0, "likely": 1, "confirmed": 2}
# A document seen but not read is "I couldn't read it", not a risk: the number
# is the harm, and an ID with a thumb over the number leaks nothing usable.
_NEEDS_VALUE = {"ID_DOCUMENT", "FINANCIAL"}


def _source_of(post_id: str, profile: Profile) -> str:
    for p in profile.posts:
        if p.post_id == post_id:
            return p.source
    # Ids are "<kind>-NNNN" (Task 1), so the prefix is the source when the
    # post is not in the profile (tests, or a profile trimmed by max_items).
    return post_id.split("-", 1)[0]


def roll_up(findings: list[Finding], voice: VoiceResult, profile: Profile
            ) -> tuple[list[Ingredient], list[Finding], list[Finding]]:
    by_cat: dict[str, Ingredient] = {}
    unsure: list[Finding] = []
    past: list[Finding] = []
    for f in findings:
        if _source_of(f.post_id, profile) == "story":
            past.append(f)
            continue
        if f.confidence == "unsure" or (f.category in _NEEDS_VALUE and f.value is None):
            unsure.append(f)
            continue
        ing = by_cat.get(f.category)
        if ing is None:
            by_cat[f.category] = Ingredient(category=f.category, confidence=f.confidence, post_ids=[f.post_id])
        else:
            if _CONF_RANK[f.confidence] > _CONF_RANK[ing.confidence]:
                ing.confidence = f.confidence
            if f.post_id not in ing.post_ids:
                ing.post_ids.append(f.post_id)
    ingredients = list(by_cat.values())
    if voice.band != "none":
        ingredients.append(Ingredient(category="VOICE", confidence="confirmed" if voice.enrolled else "likely",
                                      post_ids=list(voice.seconds_by_post), band=voice.band))
    return ingredients, unsure, past
