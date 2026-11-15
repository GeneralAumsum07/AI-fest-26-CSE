"""Attack recipes: which scams the collected ingredients make possible (spec 7.7).

The table is data and the level rules are one function, so both fit on a
slide and a judge can check any result by hand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from selfaudit import config
from selfaudit.models import Finding, Ingredient, Profile, RecipeResult

LEVEL_RANK = {None: 0, "low": 1, "medium": 2, "high": 3}
_LEVELS = [None, "low", "medium", "high"]
_CONF_RANK = {"unsure": 0, "likely": 1, "confirmed": 2}

# A slot option is a category; "NAME" is the profile name, which every
# account has and which is therefore not a Category or an ingredient.
NAME = "NAME"


@dataclass(frozen=True)
class Recipe:
    slots: tuple[tuple[str, ...], ...]
    core: int | None              # index of the slot without which the scam does not work
    amplifiers: tuple[str, ...] = ()
    cap: str | None = None


RECIPES: dict[str, Recipe] = {
    # R1: a phone call in your voice to your family, asking for money.
    "R1": Recipe(slots=(("VOICE",), ("FAMILY_RELATION",), ("CONTACT", "INSTITUTION")), core=0,
                 amplifiers=("AWAY_STATUS", "TRAVEL_DOC", "FACE_CLEAR")),
    # R2: a copy of your profile, messaging your friends. Capped at medium:
    # a copied profile is a nuisance and a lure, not money moved by itself.
    "R2": Recipe(slots=(("FACE_CLEAR",), (NAME,), ("INSTITUTION", "FAMILY_RELATION")), core=0, cap="medium"),
    # R3: a loan or SIM in your name from your ID or card numbers.
    "R3": Recipe(slots=(("ID_DOCUMENT", "FINANCIAL"),), core=0, amplifiers=("CONTACT",)),
}


def _qualifies(ing: Ingredient) -> bool:
    # Too little voice to clone, or a face in too few posts to build a profile
    # from, does not fill the slot.
    if ing.category == "VOICE":
        return ing.band in ("moderate", "high")
    if ing.category == "FACE_CLEAR":
        return len(ing.post_ids) >= config.SEVERAL_FACE_POSTS
    return True


def _slot_conf(slot: tuple[str, ...], have: dict[str, Ingredient], profile: Profile) -> str | None:
    """Best confidence among the options filling this slot, or None if empty."""
    best = None
    for opt in slot:
        if opt == NAME:
            conf = "confirmed" if sum(ch.isalpha() for ch in profile.name) >= 2 else None
        else:
            ing = have.get(opt)
            conf = ing.confidence if ing is not None and _qualifies(ing) else None
        if conf is not None and (best is None or _CONF_RANK[conf] > _CONF_RANK[best]):
            best = conf
    return best


def _level(recipe: Recipe, have: dict[str, Ingredient], profile: Profile) -> str | None:
    confs = [_slot_conf(s, have, profile) for s in recipe.slots]
    filled = [c is not None for c in confs]
    # Rule 1: no slot filled, not counting the profile name (everyone has one).
    if not any(f for f, s in zip(filled, recipe.slots) if s != (NAME,)):
        return None
    if all(filled):
        level = "high" if all(c == "confirmed" for c in confs) else "medium"      # rules 2, 3
    elif len(recipe.slots) == 3 and filled.count(False) == 1:
        level = "medium"                                                           # rule 4
    else:
        level = "low"                                                              # rule 5
    if recipe.core is not None and not filled[recipe.core]:
        level = "low"                                                              # rule 6
    if recipe.cap is not None and LEVEL_RANK[level] > LEVEL_RANK[recipe.cap]:
        level = recipe.cap                                                         # rule 7
    if profile.is_private:
        level = _LEVELS[max(1, LEVEL_RANK[level] - 1)]                             # rule 8
    return level


def _with_unsure(ingredients: list[Ingredient], unsure: list[Finding]) -> dict[str, Ingredient]:
    """Ingredients plus every unsure finding counted as `likely` (rule 9)."""
    have = {i.category: i.model_copy(deep=True) for i in ingredients}
    for f in unsure:
        ing = have.get(f.category)
        if ing is None:
            have[f.category] = Ingredient(category=f.category, confidence="likely", post_ids=[f.post_id])
        else:
            if _CONF_RANK[ing.confidence] < _CONF_RANK["likely"]:
                ing.confidence = "likely"
            if f.post_id not in ing.post_ids:
                ing.post_ids.append(f.post_id)
    return have


def _amplifiers(recipe: Recipe, have: dict[str, Ingredient], profile: Profile) -> list[str]:
    dates = {p.post_id: p.created for p in profile.posts}
    window = timedelta(days=config.AWAY_WINDOW_DAYS)
    out = []
    for amp in recipe.amplifiers:
        ing = have.get(amp)
        if ing is None:
            continue
        if amp in ("AWAY_STATUS", "TRAVEL_DOC"):
            # "Away" only helps a scammer while it is still true.
            recent = any(p in dates and profile.reference_date - dates[p] <= window for p in ing.post_ids)
            if not recent:
                continue
        out.append(amp)
    return out


def evaluate(ingredients: list[Ingredient], unsure: list[Finding], profile: Profile) -> list[RecipeResult]:
    have = {i.category: i for i in ingredients}
    maybe = _with_unsure(ingredients, unsure)
    results: list[RecipeResult] = []
    for rid, recipe in RECIPES.items():
        level = _level(recipe, have, profile)
        alt = _level(recipe, maybe, profile)
        not_sure = alt != level
        slot_cats = {c for s in recipe.slots for c in s}
        look_at = [f.finding_id for f in unsure if f.category in slot_cats] if not_sure else []
        if level is None and not not_sure:
            continue
        has, missing = [], []
        for s in recipe.slots:
            if s == (NAME,):
                continue
            filled = [c for c in s if c in have and _qualifies(have[c])]
            if filled:
                has += filled
            else:
                missing += list(s)
        results.append(RecipeResult(recipe_id=rid, level=level, not_sure=not_sure, has=has, missing=missing,
                                    amplifiers=_amplifiers(recipe, have, profile), look_at=look_at))
    # Rule 10: amplifiers only order results; they never change a level.
    results.sort(key=lambda r: (-LEVEL_RANK[r.level], -len(r.amplifiers)))
    return results
