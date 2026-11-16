"""Check before you post: one photo or video in, advice about that item only.

Same readers and the same grounding as the audit (analyse_items), so the
held-out numbers, which are scored per item, describe this path too. What
it deliberately does NOT do, from the misuse rule in the spec:

- no voice step: voice exposure is a total across a profile, and one clip
  cannot say anything useful about it;
- no recipes, roll-up, fixes or memory: each check stands alone, so nothing
  can be stitched into a fact sheet about a person across many photos;
- no disk: the bytes live in this request and are dropped with it;
- no values: Finding.value is excluded when serialised, as in the report.

The Stop / Look / Nothing split is a presentation layer that has NOT been
evaluated; the held-out numbers only cover "was something flagged".
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, UnidentifiedImageError

from selfaudit.models import Finding, Skipped
from selfaudit.perceive.items import Backends, ItemInput, analyse_items
from selfaudit.perceive.video import MediaError, keyframes

MAX_BYTES = 50 * 1024 * 1024
Result = Literal["stop", "look", "nothing"]

# Categories that are a problem on their own, the moment they are readable:
# each is enough for a fraud or a theft without any other detail.
STOP_ALONE = {"ID_DOCUMENT", "FINANCIAL", "TRAVEL_DOC", "CONTACT"}
# Never a reason to hesitate: the spec's rule is that nobody is told to stop
# posting their own face. Voice cannot come from one item (see above).
IGNORED = {"FACE_CLEAR", "VOICE"}

HEADING = {
    "stop": "Wait before you post this.",
    "look": "Have a look at this first.",
    "nothing": "Nothing urgent was identified in this photo.",
}
NOTHING_NOTE = ("This does not mean it is safe to post. The check looks for ID and bank details, tickets, "
                "contact details, family names and travel plans.")
VIDEO_NOTE = "Speech in this video was not measured. The full audit does that."
# One line per category, telling the person what to do with this item.
# Imperative and specific; never "safe", never a score.
ADVICE = {
    "ID_DOCUMENT": "Cover or crop the ID number, then check again.",
    "FINANCIAL": "Cover or crop the card or account number, then check again.",
    "TRAVEL_DOC": "Leave out the ticket or boarding pass. Its code can be used to change your booking.",
    "CONTACT": "Remove the phone number or email, or share it in a direct message instead.",
    "FAMILY_RELATION": "Consider leaving out the family member's name. Scam callers use names to sound real.",
    "AWAY_STATUS": "Consider posting after you are back. A post saying you are away tells people when home is empty.",
    "INSTITUTION": "Your college or workplace is visible. On its own that is common; it adds up with other details.",
}


class CheckError(Exception):
    """A plain message for the person; never a file name or content."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


@dataclass
class CheckResult:
    result: Result
    findings: list[Finding]
    is_video: bool


def verdict(findings: list[Finding]) -> Result:
    """Stop / Look / Nothing for one item.

    A product judgement, not a measured rule (proposal in spec section 5;
    to be reviewed). Stop needs a CONFIRMED finding in a category that is
    harmful alone: "confirmed" means two readers agreed or a checksum
    passed, so Stop is not shown on a guess. Anything weaker, or a category
    that only matters in combination with others, is Look: the person
    decides, with the item in front of them."""
    counted = [f for f in findings if f.category not in IGNORED]
    if any(f.category in STOP_ALONE and f.confidence == "confirmed" for f in counted):
        return "stop"
    return "look" if counted else "nothing"


def _items(data: bytes, content_type: str, caption: str) -> tuple[list[ItemInput], bool]:
    if content_type.startswith("image/"):
        try:
            # verify() checks the file without decoding all of it; the vision
            # client decodes it properly later. A non-image fails here with a
            # plain message instead of a vague "couldn't check" from the model.
            Image.open(io.BytesIO(data)).verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
            raise CheckError(422, "This photo could not be read. Try a JPEG or PNG.") from None
        return [ItemInput("check", "check", data, caption)], False
    if content_type.startswith("video/"):
        try:
            frames = keyframes(data)
        except MediaError:
            frames = []
        if not frames:
            raise CheckError(422, "This video could not be read. Try an MP4.")
        # As in the audit: the caption travels with the first frame only, so a
        # caption is read once, not once per frame.
        return [ItemInput(f"check#f{n}", "check", jpeg, caption if n == 0 else "")
                for n, jpeg in enumerate(frames)], True
    raise CheckError(422, "Choose a photo or a video.")


def check_item(data: bytes, content_type: str, caption: str, backends: Backends) -> CheckResult:
    if len(data) > MAX_BYTES:
        raise CheckError(413, "This file is over 50 MB. Try a shorter video or a smaller photo.")
    items, is_video = _items(data, content_type, caption)
    findings, skipped = analyse_items(items, backends, unload=False)
    # Saying "Nothing urgent" about a photo the model never read would be a
    # false all-clear, so a total failure is an error, not a result.
    if not findings and _all_failed(items, skipped):
        raise CheckError(422, "The check could not read this file. Try again, or try another photo.")
    return CheckResult(verdict(findings), findings, is_video)


def _all_failed(items: list[ItemInput], skipped: list[Skipped]) -> bool:
    failed = {s.ref for s in skipped}
    return all(it.item_id in failed for it in items if it.image is not None)


def to_body(res: CheckResult) -> dict:
    shown = [f for f in res.findings if f.category not in IGNORED]
    cats = list(dict.fromkeys(f.category for f in shown))   # first-seen order, no repeats
    return {
        "result": res.result,
        "heading": HEADING[res.result].replace("photo", "video") if res.is_video else HEADING[res.result],
        # model_dump honours Finding.value's exclude=True: no number or name leaves.
        "findings": [f.model_dump(mode="json", include={"category", "what", "confidence"}) for f in shown],
        "advice": [ADVICE[c] for c in cats if c in ADVICE],
        "note": NOTHING_NOTE if res.result == "nothing" else None,
        "video_note": VIDEO_NOTE if res.is_video else None,
    }
