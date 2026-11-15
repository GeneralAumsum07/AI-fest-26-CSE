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

        first = rs[0]
        out.append(Finding(
            finding_id=f"{item_id}:{category}", item_id=item_id,
            post_id=post_of.get(item_id, item_id.split("/", 1)[0]), category=category,
            what=first.what, confidence=confidence, supports=sorted(supports), value=value,
        ))
    return out
