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

import re
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


# A run of at least 10 digits, allowing the spaces and dashes people group
# numbers with. Ten is the length of an Indian mobile number, so any phone the
# model could have meant is at least this long; a house number or a PIN code
# (6 digits) is not, which keeps written addresses out of rule 7.
_LONG_NUMBER = re.compile(r"\d(?:[\s-]?\d){9,}")


def _public_short_number(value: str | None) -> bool:
    """A bare number too short to be anyone's own phone (rule 8).

    Debugged 2026-11-15 (dev-031): the caption reader called "181", the
    women's helpline, a contact. 100, 112, 181, 1098 are public short codes;
    a scammer learns nothing about you from them. An email or an address
    has letters in it and is never caught here.
    """
    v = (value or "").strip()
    if not v or not re.fullmatch(r"[\d\s+()-]+", v):
        return False
    return sum(ch.isdigit() for ch in v) < 10


# Words that say a name belongs to a college, school or employer. Rule 9 asks
# vision's transcription for one of them before its INSTITUTION claim counts.
_INSTITUTION_WORD = re.compile(
    r"\b(?:college|universit(?:y|ies)|institute|school|academy|polytechnic|campus|faculty|"
    r"iit|nit|iiit|student|employee|staff|ltd|limited|pvt|private|inc|llp|corp|corporation|"
    r"company|technologies|solutions|services|labs?|hospital)\b", re.IGNORECASE)


def _bare_name_institution(rs: list[RawFinding]) -> bool:
    """Rule 9: vision named a place but nothing says it is a college or employer.

    Debugged 2026-11-15 (dev-023): on a restaurant bill the model transcribed
    only "Spice Garden" and called it an institution. A shop, restaurant or
    brand is just a name; the spec's INSTITUTION is the person's college,
    school or employer. When vision is the only reader and its text carries no
    word for one, its claim is not support. Cost: an employer shown only by a
    bare brand ("Infosys" on a lanyard) becomes "Not sure" (still shown); the
    caption model, which reads "first day at Infosys" in context, is exempt.
    """
    vision = [r for r in rs if r.reader == "vision"]
    return bool(vision) and not any(_INSTITUTION_WORD.search(r.extracted_text or "") for r in vision)


def _contradicted_contact(rs: list[RawFinding], checked: bool) -> bool:
    """Rule 7: the phone checker read the number vision called a phone, and refused it.

    Debugged 2026-11-15: the vision model called a meme's 12-digit number and
    an order number "a phone number". Alone that was one support, "likely",
    and it filled a recipe slot. But the India-only phone recogniser had read
    the same transcribed digits and found no phone. Spec 264: disagreement
    lowers confidence rather than raising an alarm. Only a long digit run
    counts as a contradiction, because no recogniser here knows addresses;
    its silence on "12 MG Road" says nothing.
    """
    if not checked or any(r.reader != "vision" for r in rs):
        return False
    return any(_LONG_NUMBER.search(r.extracted_text or "") for r in rs)


def ground(raws: list[RawFinding], captions: dict[str, str], post_of: dict[str, str],
           checked: set[str] | None = None) -> list[Finding]:
    """One Finding per (item_id, category), in first-seen order; keyframes of
    one video then collapse to one Finding per (video, category).

    `checked` is the set of item_ids whose text the pattern recognisers read
    without error. It is passed in, not inferred, because the ablation runs
    without patterns, and "the checker found nothing" must not be confused
    with "the checker never looked".
    """
    checked = checked or set()
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
            if category == "CONTACT" and _public_short_number(r.value):
                continue  # rule 8: a helpline is not your contact
            supports.add(r.reader)
        if category == "CONTACT" and _contradicted_contact(rs, item_id in checked):
            supports.discard("vision")  # rule 7: two readers disagree -> unsure
        if category == "INSTITUTION" and _bare_name_institution(rs):
            supports.discard("vision")  # rule 9: a bare name is not a college or employer
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
    return _merge_frames(out)


_RANK = {"confirmed": 2, "likely": 1, "unsure": 0}


def _merge_frames(findings: list[Finding]) -> list[Finding]:
    """One finding per (video, category), not one per keyframe.

    Keyframes are separate items ("…/media-0#f3") so each is grounded against
    its own transcribed text. Grounding is done per frame on purpose. But an ID
    card on screen for four seconds is one exposure, and four identical cards
    in the report read as four problems. Keep the strongest frame's finding
    as it stands, without pooling support across frames: two frames of the
    same model saying the same thing are not two independent readers, so
    pooling would turn "likely" into "confirmed" for nothing.
    """
    best: dict[tuple[str, str], int] = {}   # (media item, category) -> index in kept
    kept: list[Finding] = []
    for f in findings:
        key = (f.item_id.split("#", 1)[0], f.category)
        if key not in best:
            best[key] = len(kept)
            kept.append(f)
            continue
        cur = kept[best[key]]
        # Stronger confidence wins; at equal confidence, a frame with a value
        # (it feeds the fix text and the checksum story) beats one without.
        if (_RANK[f.confidence], f.value is not None) > (_RANK[cur.confidence], cur.value is not None):
            kept[best[key]] = f   # same slot, so first-seen order is preserved
    return kept
