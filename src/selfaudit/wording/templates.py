"""Offline wording: the report must read well with the network off.

Rules from the spec, enforced by tests: never say "safe" (absence of a finding
is not safety), never show a percentage or score, and name a next action.
English only for now; Hindi and Telugu come from the cloud wording, because
untested hand translations of risk advice are worse than English.
"""

from __future__ import annotations

import re

from selfaudit.models import VoiceResult
from selfaudit.wording.payload import RecipeText, ReportText, WordingPayload

TITLES = {
    "R1": "A phone call to your family in your voice",
    "R2": "A copy of your profile",
    "R3": "Misuse of your ID document",
}
EMPTY_SUMMARY = "No urgent exposure was identified in the content that could be analysed."
NO_ENROL_LINE = "Speech detected in {n} videos. Add a voice reference to improve speaker matching."
PRIVATE_BANNER = "Only followers see these. The risks apply to followers and to anyone who screenshots."

_PHRASE = {
    "voice": "clear speech in your voice",
    "voice:moderate": "enough clear speech in your voice to copy it",
    "voice:high": "a lot of clear speech in your voice",
    "family_relation": "posts that name your family",
    "contact": "a phone number or email address",
    "institution": "your college or workplace",
    "face_clear": "clear photos of your face",
    "name": "your name on your profile",
    "id_document": "a readable ID number",
    "financial": "a readable card or account number",
    "away_status:recent": "a recent post showing you are away from home",
}
_ADVICE = {
    "R1": "Agree a family code word in person, never type it into any app, and ask for it on any call "
          "asking for money.",
    "R2": "Tell close friends you will never ask for money or codes in a message, and to call you if "
          "\"you\" ever do.",
    # The concrete steps (Sanchar Saathi, UIDAI, 1930) are fixed text from
    # wording/next_steps.py, shown under this line; this line can be reworded.
    "R3": "Take down the post that shows the number. Anyone who saw it may have kept a copy, so take "
          "these steps tonight:",
}
# "{ref}" is "post 3" (Instagram) or "video 3" (YouTube). Templates rather than
# verbs because YouTube's private setting reads "Set video 3 to Private".
_ACTION = {
    "instagram": {"remove": "Delete {ref}", "archive": "Archive {ref}", "crop": "Crop the detail out of {ref}",
                  "edit_caption": "Edit the caption of {ref}"},
    # YouTube has no archive; Private (not Unlisted, which anyone with the link
    # can still watch) is its "take it out of view but keep it" action. A
    # published video cannot be cropped, but YouTube Studio can blur part of it.
    "youtube": {"remove": "Delete {ref}", "archive": "Set {ref} to Private", "crop": "Blur the detail in {ref}",
                "edit_caption": "Edit the title or description of {ref}"},
}
# What the user calls one item: the page labels use the same word (app.py).
ITEM_WORD = {"instagram": "post", "youtube": "video"}


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _item_words(text: str, platform: str) -> str:
    """Say "video(s)" for "post(s)" on YouTube.

    One swap at render time instead of a second copy of _PHRASE and _ADVICE:
    every "post" in those strings means "one item on the profile", so the
    swap is safe, and a new phrase added later is covered without anyone
    remembering a YouTube copy. Whole words only, so "posted" is left alone."""
    if platform != "youtube":
        return text
    return re.sub(r"\b([Pp])ost(s?)\b", lambda m: ("V" if m[1] == "P" else "v") + "ideo" + m[2], text)


def render_local(payload: WordingPayload) -> ReportText:
    recipes: dict[str, RecipeText] = {}
    for r in payload.recipes:
        reasons = ""
        if r.has:
            reasons = "Your posts show " + _join([_PHRASE[t] for t in r.has]) + "."
        if r.missing:
            reasons += (" " if reasons else "") + "Someone would still need " + _join(
                [_PHRASE[t] for t in r.missing]) + "."
        if r.not_sure:
            reasons += (" " if reasons else "") + "Some posts may add to this; look at them below."
        recipes[r.id] = RecipeText(title=TITLES[r.id], reasons=_item_words(reasons, payload.platform),
                                   advice=_item_words(_ADVICE[r.id], payload.platform))

    fixes = []
    for f in payload.fixes:
        effects = []
        for e in f.effects:
            kind, rid = e.split(" ")
            # Lower only the first letter: .lower() turned "ID" into "id".
            title = TITLES[rid][0].lower() + TITLES[rid][1:]
            effects.append(("ends" if kind == "ends" else "lowers") + ": " + title)
        # post_ref is always "post N" in the payload (its pattern is the leak
        # guard); only the words shown here change per platform.
        ref = f.post_ref.replace("post", ITEM_WORD[payload.platform], 1)
        action = _ACTION[payload.platform][f.action].format(ref=ref)
        fixes.append(f"{f.rank}. {action}" + (f" ({'; '.join(effects)})" if effects else "") + ".")

    shown = [r for r in payload.recipes if r.level != "none"]
    if shown:
        summary = (f"{len(shown)} potential misuse scenario{'s were' if len(shown) > 1 else ' was'} identified. "
                   "Start with the recommended actions below.")
    else:
        summary = EMPTY_SUMMARY
        if any(r.not_sure for r in payload.recipes):
            summary += " Some posts need a second look; they are listed below."
    if payload.couldnt_check:
        summary += f" {payload.couldnt_check} item{'s were' if payload.couldnt_check > 1 else ' was'} not analysed; " \
                   "review the exclusions below."
    if payload.private:
        summary = PRIVATE_BANNER + " " + summary
    return ReportText(summary=summary, recipes=recipes, fixes=fixes)


def voice_note(voice: VoiceResult) -> str | None:
    """The no-enrolment line. Rendered from the local report, not the payload:
    the payload's shape is fixed and carries no enrolment flag or reel count."""
    if voice.enrolled or voice.band == "none":
        return None
    return NO_ENROL_LINE.format(n=len(voice.seconds_by_post))
