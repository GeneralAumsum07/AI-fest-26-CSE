"""The redaction boundary: the only thing that may ever leave the laptop (spec 7.9).

Why the payload is built from closed vocabularies instead of being scrubbed:
scrubbing free text is a promise ("we removed the names we found"), while a
type that has no field able to hold a name is a proof. Every field here is a
Literal, a bounded int, or a string with a fixed pattern. assert_no_leak is
the second lock: it checks the serialised JSON against every secret anyway.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from selfaudit import config
from selfaudit.ingest.textfix import normalise
from selfaudit.models import Profile, Report

HasToken = Literal["voice", "voice:moderate", "voice:high", "family_relation", "contact", "institution",
                   "face_clear", "name", "id_document", "financial", "away_status:recent"]
Effect = Annotated[str, Field(pattern=r"^(ends|weakens) R[123]$")]


class RecipePayload(BaseModel):
    id: Literal["R1", "R2", "R3"]
    level: Literal["high", "medium", "low", "none"]
    not_sure: bool = False
    has: list[HasToken]
    missing: list[HasToken]


class FixPayload(BaseModel):
    rank: int = Field(ge=1, le=99)
    action: Literal["remove", "archive", "crop", "edit_caption"]
    # An ordinal ("post 3" = third newest), never an id, a caption or a date.
    post_ref: str = Field(pattern=r"^post \d+( and \d+ more)?$")
    effects: list[Effect]


class WordingPayload(BaseModel):
    recipes: list[RecipePayload]
    fixes: list[FixPayload]
    language: Literal["en", "hi", "te"]
    private: bool
    couldnt_check: int = Field(ge=0)


class LeakError(Exception):
    """A secret appears in text bound for the cloud. Never carries the secret itself."""


class RecipeText(BaseModel):
    title: str
    reasons: str
    advice: str


class ReportText(BaseModel):
    summary: str
    recipes: dict[str, RecipeText]
    fixes: list[str]


_TOKEN = {"FAMILY_RELATION": "family_relation", "CONTACT": "contact", "INSTITUTION": "institution",
          "FACE_CLEAR": "face_clear", "ID_DOCUMENT": "id_document", "FINANCIAL": "financial",
          "AWAY_STATUS": "away_status:recent", "TRAVEL_DOC": "away_status:recent"}


def _token(category: str, band: str, *, with_band: bool) -> str | None:
    if category == "VOICE":
        return f"voice:{band}" if with_band and band in ("moderate", "high") else "voice"
    return _TOKEN.get(category)


def build_payload(report: Report, profile: Profile, language: str = "en") -> WordingPayload:
    band = report.voice.band
    recipes = []
    for r in report.recipes:
        has = [t for c in r.has if (t := _token(c, band, with_band=True))]
        if r.recipe_id == "R2":
            has.append("name")  # the profile-name slot is always filled; see recipes.NAME
        # Amplifiers ride in `has`: they are things the attacker has, just
        # things that make the scam easier rather than possible.
        has += [t for c in r.amplifiers if (t := _token(c, band, with_band=True))]
        missing = [t for c in r.missing if (t := _token(c, band, with_band=False))]
        recipes.append(RecipePayload(id=r.recipe_id, level=r.level or "none", not_sure=r.not_sure,
                                     has=list(dict.fromkeys(has)), missing=list(dict.fromkeys(missing))))

    order = {p.post_id: n for n, p in enumerate(profile.posts, start=1)}
    fixes = []
    for rank, f in enumerate(report.fixes, start=1):
        ords = sorted(order[p] for p in f.post_ids if p in order)
        ref = f"post {ords[0]}" + (f" and {len(ords) - 1} more" if len(ords) > 1 else "") if ords else "post 0"
        fixes.append(FixPayload(rank=rank, action=f.action, post_ref=ref,
                                effects=[f"ends {r}" for r in f.ends] + [f"weakens {r}" for r in f.weakens]))
    return WordingPayload(recipes=recipes, fixes=fixes, language=language if language in ("en", "hi", "te") else "en",
                          private=profile.is_private, couldnt_check=len(report.couldnt_check))


def leaks(text: str, secrets: set[str]) -> bool:
    """True when any secret of at least MIN_LEAK_LEN characters appears in `text`,
    compared after the same normalisation (case, spaces, dashes, colons) so
    "9876 5432" and "98765432" match."""
    hay = normalise(text)
    return any(normalise(s) and normalise(s) in hay for s in secrets if len(s) >= config.MIN_LEAK_LEN)


def assert_no_leak(payload: WordingPayload, secrets: set[str]) -> None:
    # A false alarm (a username that happens to be "remove") costs only the
    # cloud wording for that run: the safe direction to fail.
    if leaks(payload.model_dump_json(), secrets):
        raise LeakError("payload contains a secret")
