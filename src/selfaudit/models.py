"""Shared types for every stage of the pipeline.

Why pydantic everywhere: the same objects cross the model boundary (the vision
model's JSON), the API boundary (the report) and the wording boundary (the
redacted payload). Validation at each crossing is what turns "the model said
something odd" into a clipped value instead of a crash.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal[
    "ID_DOCUMENT", "FINANCIAL", "TRAVEL_DOC", "CONTACT", "FAMILY_RELATION",
    "AWAY_STATUS", "INSTITUTION", "FACE_CLEAR", "VOICE",
]
Confidence = Literal["confirmed", "likely", "unsure"]
Level = Literal["high", "medium", "low"]
Band = Literal["none", "low", "moderate", "high"]
Reader = Literal["vision", "caption", "patterns", "lexicon", "ner", "user"]


class Skipped(BaseModel):
    """Something the app could not or did not check.

    `reason` is a short code (missing_file, outside_export, over_limit, ...),
    never content, so these lists are safe to show and to log.
    """
    ref: str
    reason: str


class MediaItem(BaseModel):
    item_id: str
    post_id: str
    kind: Literal["image", "video"]
    zip_path: str


class Post(BaseModel):
    post_id: str
    source: Literal["post", "story", "reel"]
    caption: str
    created: datetime
    media: list[MediaItem]


class Profile(BaseModel):
    name: str
    username: str
    bio: str
    is_private: bool
    posts: list[Post]  # newest first
    # "Recent" is measured from the export's newest item, not from today, so a
    # persona built last week still shows "away right now" in the demo.
    reference_date: datetime
    couldnt_check: list[Skipped] = []
    not_checked: list[Skipped] = []


class RawFinding(BaseModel):
    """One reader's claim about one item, before grounding decides how much to trust it."""
    item_id: str
    category: Category
    what: str
    extracted_text: str = ""
    value: str | None = None
    model_confidence: Literal["high", "medium", "low"] = "high"
    reader: Reader
    id_subtype: Literal["government", "institutional"] | None = None


class Finding(BaseModel):
    finding_id: str
    item_id: str
    post_id: str
    category: Category
    what: str
    confidence: Confidence
    supports: list[str]
    # Never serialised: extracted values (an ID number, a phone number) stay in
    # this process. The API, the logs and the wording payload never see them.
    value: str | None = Field(default=None, exclude=True)


class VoiceResult(BaseModel):
    clean_seconds: float
    band: Band
    enrolled: bool
    seconds_by_post: dict[str, float]


class Ingredient(BaseModel):
    category: Category
    confidence: Confidence
    post_ids: list[str]
    band: Band | None = None


class RecipeResult(BaseModel):
    recipe_id: Literal["R1", "R2", "R3"]
    level: Level | None
    not_sure: bool
    has: list[Category]
    missing: list[Category]
    amplifiers: list[Category]
    look_at: list[str]


class Fix(BaseModel):
    post_ids: list[str]
    action: Literal["remove", "archive", "crop", "edit_caption"]
    removes: list[Category]
    ends: list[str]
    weakens: list[str]


class Report(BaseModel):
    posts_read: int
    is_private: bool
    recipes: list[RecipeResult]
    fixes: list[Fix]
    findings: list[Finding]
    unsure: list[Finding]
    past_exposure: list[Finding]
    voice: VoiceResult
    couldnt_check: list[Skipped]
    not_checked: list[Skipped]
    private_would_lower: list[str]  # recipe ids going private would lower; empty when already private
