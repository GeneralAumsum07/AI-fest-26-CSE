"""Grounding and confidence (spec 7.5, 7.6).

This is where a model's claim becomes a finding the report may rely on.
Two ideas carry it:
- A value is only kept if it is actually in the item's text. A name or a
  number the model invented is dropped, and the reader that invented it stops
  counting as support.
- Confidence counts independent readers, not model self-confidence: two
  readers agreeing is "confirmed", one is "likely", none is "unsure".
"""

from __future__ import annotations

from collections import defaultdict

from selfaudit.ingest.textfix import normalise
from selfaudit.models import Finding, RawFinding

_FACE_LEVEL = {"high": "confirmed", "medium": "likely", "low": "unsure"}
# Readers whose support depends on the value they claimed being grounded.
_VALUE_READERS = {"caption", "ner"}
# Readers whose `what` is a phrase we wrote (patterns._WHAT, the word lists,
# "reported by you"). Every other reader is a model, and a model's sentence can
# hold the very name or number being flagged ("Aadhaar card of Priya, 2345...").
# Finding.value is excluded from serialisation to keep those values on the
# laptop; serving the model's sentence as `what` would undo that, so model
# findings are described by category instead.
_FIXED_TEXT_READERS = {"patterns", "lexicon", "user"}
_CATEGORY_WHAT = {
    "ID_DOCUMENT": "an ID document", "FINANCIAL": "a bank card or account detail",
    "TRAVEL_DOC": "a ticket or boarding pass", "CONTACT": "a phone number or email",
    "FAMILY_RELATION": "a family member's name", "AWAY_STATUS": "a sign you are away",
    "INSTITUTION": "your college or workplace", "FACE_CLEAR": "a clear face", "VOICE": "your voice",
}


def _grounded(value: str | None, text: str) -> bool:
    nv = normalise(value or "")
    return bool(nv) and nv in text


def ground(raws: list[RawFinding], captions: dict[str, str], post_of: dict[str, str]) -> list[Finding]:
    """One Finding per (item_id, category), in first-seen order."""
    # Item text = caption + everything the vision model transcribed from the image.
    text: dict[str, str] = defaultdict(str)
    for item_id, cap in captions.items():
        text[item_id] += normalise(cap)
    for r in raws:
        if r.reader == "vision" and r.extracted_text:
            text[r.item_id] += normalise(r.extracted_text)

    groups: dict[tuple[str, str], list[RawFinding]] = {}
    for r in raws:
        category = r.category
        # Rule 1: a college or company ID is evidence of the institution, not a
        # government document that could be misused.
        if category == "ID_DOCUMENT" and r.id_subtype == "institutional":
            category = "INSTITUTION"
        groups.setdefault((r.item_id, category), []).append(r)

    out: list[Finding] = []
    for (item_id, category), rs in groups.items():
        supports: set[str] = set()
        value: str | None = None
        for r in rs:
            ok = _grounded(r.value, text[item_id])
            # Rule 3: low-confidence vision is not support; ungrounded caption
            # or name values are not support (rule 2).
            if r.reader == "vision" and r.model_confidence == "low":
                continue
            if r.reader in _VALUE_READERS and not ok:
                continue
            supports.add(r.reader)
        # Rule 6: prefer the checksum-backed value, then the caption's.
        for reader in ("patterns", "caption"):
            v = next((r.value for r in rs if r.reader == reader and _grounded(r.value, text[item_id])), None)
            if v is not None:
                value = v
                break

        if category == "FACE_CLEAR":
            # Rule 5: only the vision model can see a face; its own confidence decides.
            best = max((r.model_confidence for r in rs if r.reader == "vision"),
                       key=["low", "medium", "high"].index, default="low")
            confidence = _FACE_LEVEL[best]
        elif "user" in supports or len(supports) >= 2:
            confidence = "confirmed"  # rule 4: a user's own report needs no second reader
        elif len(supports) == 1:
            confidence = "likely"
        else:
            confidence = "unsure"

        # Prefer our own phrase when a fixed-text reader saw it; else the category's.
        what = next((r.what for r in rs if r.reader in _FIXED_TEXT_READERS), _CATEGORY_WHAT[category])
        out.append(Finding(
            finding_id=f"{item_id}:{category}", item_id=item_id,
            post_id=post_of.get(item_id, item_id.split("/", 1)[0]), category=category,
            what=what, confidence=confidence, supports=sorted(supports), value=value,
        ))
    return out
