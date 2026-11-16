"""Which posts to change first (spec 7.8).

A fix is a bundle of posts, not one post: an ingredient supplied by three
posts survives the removal of any one of them, so the only fix that changes
anything is the set of every post supplying it.

Ranking is greedy: score every candidate by how the recipes change without
it, take the best, apply it, repeat. Greedy is not optimal in general, but
with five fixes and three recipes it is easy to explain on a slide and the
order it gives is the order a person would act in.
"""

from __future__ import annotations

from typing import Callable

from selfaudit.models import Finding, Fix, Profile, RecipeResult, VoiceResult
from selfaudit.perceive.voice import drop_posts
from selfaudit.recipes import LEVEL_RANK, evaluate
from selfaudit.rollup import roll_up

_WHOLE_POST = {"ID_DOCUMENT": "remove", "FINANCIAL": "remove", "TRAVEL_DOC": "remove"}
# Under 5 s is the "low" voice band: anything above still fills the voice slot
# at moderate, so archiving fewer reels would change no recipe.
_VOICE_TARGET_S = 5.0


def _recipes(findings: list[Finding], voice: VoiceResult, profile: Profile) -> list[RecipeResult]:
    ingredients, unsure, _ = roll_up(findings, voice, profile)
    return evaluate(ingredients, unsure, profile)


def candidate_fixes(findings: list[Finding], voice: VoiceResult, profile: Profile) -> list[Fix]:
    ingredients, _, _ = roll_up(findings, voice, profile)
    out: list[Fix] = []
    for ing in ingredients:
        cat = ing.category
        if cat == "FACE_CLEAR":
            continue  # spec 7.7: nobody should be told to stop posting their face
        if cat == "VOICE":
            remaining, posts = voice.clean_seconds, []
            for post, secs in sorted(voice.seconds_by_post.items(), key=lambda kv: -kv[1]):
                if remaining < _VOICE_TARGET_S:
                    break
                posts.append(post)
                remaining -= secs
            out.append(Fix(post_ids=posts, action="archive", removes=["VOICE"], ends=[], weakens=[]))
            continue
        action = _WHOLE_POST.get(cat)
        if action is None:
            # A caption edit cannot remove something the camera saw.
            seen = any("vision" in f.supports for f in findings if f.category == cat and f.post_id in ing.post_ids)
            action = "crop" if seen else "edit_caption"
        out.append(Fix(post_ids=list(ing.post_ids), action=action, removes=[cat], ends=[], weakens=[]))
    return out


def _apply(fix: Fix, findings: list[Finding], voice: VoiceResult) -> tuple[list[Finding], VoiceResult]:
    posts = set(fix.post_ids)
    if fix.action in ("remove", "archive"):
        # The whole post goes, so everything in it goes with it.
        return [f for f in findings if f.post_id not in posts], drop_posts(voice, fix.post_ids)
    targets = set(fix.removes)
    return [f for f in findings if not (f.post_id in posts and f.category in targets)], voice


def preview(findings: list[Finding], voice: VoiceResult, profile: Profile, chosen: list[Fix]) -> list[RecipeResult]:
    """The recipes as they would be after the user makes every chosen fix.

    "Try a fix" on the page. It reuses _apply and _recipes, the same two calls
    rank_fixes scores with, so a ticked fix shows exactly the "after" the
    ranker promised; a second "what if" model could quietly disagree with it.
    Fixes are applied one after another because the ranked list is itself
    cumulative (fix 2 was scored on the world after fix 1). Works on copies:
    _apply returns new lists, so the audit itself is never changed."""
    for fix in chosen:
        findings, voice = _apply(fix, findings, voice)
    return _recipes(findings, voice, profile)


def _diff(before: list[RecipeResult], after: list[RecipeResult]) -> tuple[list[str], list[str]]:
    now = {r.recipe_id: r.level for r in after}
    ends, weakens = [], []
    for r in before:
        if r.level is None:
            continue
        lvl = now.get(r.recipe_id)
        if lvl is None:
            ends.append(r.recipe_id)
        elif LEVEL_RANK[lvl] < LEVEL_RANK[r.level]:
            weakens.append(r.recipe_id)
    return ends, weakens


def private_would_lower(findings: list[Finding], voice: VoiceResult, profile: Profile) -> list[str]:
    """Recipe ids whose level drops if the account goes private (shown apart from the
    ranked fixes: it is one switch, not a post to change)."""
    if profile.is_private:
        return []
    before = _recipes(findings, voice, profile)
    after = _recipes(findings, voice, profile.model_copy(update={"is_private": True}))
    ends, weakens = _diff(before, after)
    return ends + weakens


# How much effort each action asks of the person, relative to a caption edit.
# A caption edit keeps the post and takes seconds. A crop means re-editing an
# image. Archiving hides the post but can be undone from the app, so it costs
# less than a removal, which loses the post and its likes for good.
_ACTION_EFFORT = {"edit_caption": 1.0, "crop": 1.5, "archive": 1.5, "remove": 2.0}
# Each extra post in the same fix costs half as much as the first: once the
# person knows what to do, repeating it on the next post is quicker.
_EXTRA_POST_EFFORT = 0.5
# A recipe that disappears from the report entirely is a finished job the
# person can see; a recipe that only drops a level still sits on the screen.
_END_BONUS = 1.0


def _harm_lowered(before_level: str | None, after_level: str | None) -> float:
    """Severity removed, counting each step down by the level it leaves.

    high -> medium is worth 3, medium -> low 2, low -> gone 1. So lowering a
    High risk one step (3) beats ending a Low one (1 + bonus), and ending a
    High risk outright (3 + 2 + 1 = 6) beats everything a weakening can do.
    """
    hi, lo = LEVEL_RANK[before_level], LEVEL_RANK[after_level]
    return float(sum(range(lo + 1, hi + 1)))


def fix_weight(fix: Fix, before: list[RecipeResult], after: list[RecipeResult]) -> float:
    """How much this fix is worth recommending. Zero or less means never suggest it.

    Score = harm removed / effort asked. Harm uses `before`/`after` levels
    directly (not just the ends/weakens lists) so a High -> Low drop counts
    both steps. Effort is the action's cost, with each extra post at half price.

    Deliberately left out (open decisions, see the PR notes):
    - Sentimental posts: the function sees categories, not captions, and the
      cheapest action for FAMILY_RELATION is already a caption edit, which
      keeps the post. No extra penalty.
    - Amplifier-only fixes: `rank_fixes` drops any fix that changes no level
      before this is called, so scoring amplifiers here would do nothing.
    """
    now = {r.recipe_id: r.level for r in after}
    harm = 0.0
    for r in before:
        if r.level is None:
            continue
        harm += _harm_lowered(r.level, now.get(r.recipe_id))
    harm += _END_BONUS * len(fix.ends)
    if harm <= 0:
        return 0.0  # changes nothing the person can see: never suggest it
    effort = _ACTION_EFFORT[fix.action] * (1 + _EXTRA_POST_EFFORT * max(len(fix.post_ids) - 1, 0))
    return harm / effort


def rank_fixes(findings: list[Finding], voice: VoiceResult, profile: Profile, *, top_n: int = 5,
               weight: Callable[[Fix, list[RecipeResult], list[RecipeResult]], float] | None = None) -> list[Fix]:
    # Looked up at call time (not bound as a default) so the weight Rachit
    # writes is the one used, and tests can swap it without rebinding.
    weight = weight or fix_weight
    chosen: list[Fix] = []
    before = _recipes(findings, voice, profile)
    while len(chosen) < top_n:
        best: tuple[float, Fix, list[Finding], VoiceResult, list[RecipeResult]] | None = None
        for fix in candidate_fixes(findings, voice, profile):
            f2, v2 = _apply(fix, findings, voice)
            after = _recipes(f2, v2, profile)
            ends, weakens = _diff(before, after)
            if not (ends or weakens):
                continue  # changes no recipe: never worth the user's effort
            fix = fix.model_copy(update={"ends": ends, "weakens": weakens})
            score = weight(fix, before, after)
            if score > 0 and (best is None or score > best[0]):
                best = (score, fix, f2, v2, after)
        if best is None:
            break
        _, fix, findings, voice, before = best
        chosen.append(fix)
    return chosen
