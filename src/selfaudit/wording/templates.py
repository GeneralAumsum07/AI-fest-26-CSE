"""Offline wording: the report must read well with the network off.

Rules from the spec, enforced by tests: never say "safe" (absence of a finding
is not safety), never show a percentage or score, and name a next action.
English only for now; Hindi and Telugu come from the cloud wording, because
untested hand translations of risk advice are worse than English.
"""

from __future__ import annotations

from selfaudit.models import VoiceResult
from selfaudit.wording.payload import RecipeText, ReportText, WordingPayload

TITLES = {
    "R1": "A phone call to your family in your voice",
    "R2": "A copy of your profile",
    "R3": "Misuse of your ID document",
}
EMPTY_SUMMARY = "I found nothing urgent in what I could read."
NO_ENROL_LINE = "Speech found in {n} reels. It is probably you; record a sentence and I can be sure."
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
    "R3": "Take down the post that shows the number. Anyone who saw it may have kept a copy, so watch for "
          "loans or SIM cards you did not ask for.",
}
_VERB = {"remove": "Delete", "archive": "Archive", "crop": "Crop the detail out of", "edit_caption":
         "Edit the caption of"}


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


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
        recipes[r.id] = RecipeText(title=TITLES[r.id], reasons=reasons, advice=_ADVICE[r.id])

    fixes = []
    for f in payload.fixes:
        effects = []
        for e in f.effects:
            kind, rid = e.split(" ")
            effects.append(("ends" if kind == "ends" else "lowers") + ": " + TITLES[rid].lower())
        fixes.append(f"{f.rank}. {_VERB[f.action]} {f.post_ref}" + (f" ({'; '.join(effects)})" if effects else "") + ".")

    shown = [r for r in payload.recipes if r.level != "none"]
    if shown:
        summary = (f"I found {len(shown)} way{'s' if len(shown) > 1 else ''} someone could misuse what you have "
                   f"posted. Start with the first fix below.")
    else:
        summary = EMPTY_SUMMARY
        if any(r.not_sure for r in payload.recipes):
            summary += " Some posts need a second look; they are listed below."
    if payload.couldnt_check:
        summary += f" I couldn't check {payload.couldnt_check} item{'s' if payload.couldnt_check > 1 else ''}; " \
                   f"they are listed below."
    if payload.private:
        summary = PRIVATE_BANNER + " " + summary
    return ReportText(summary=summary, recipes=recipes, fixes=fixes)


def voice_note(voice: VoiceResult) -> str | None:
    """The no-enrolment line. Rendered from the local report, not the payload:
    the payload's shape is fixed and carries no enrolment flag or reel count."""
    if voice.enrolled or voice.band == "none":
        return None
    return NO_ENROL_LINE.format(n=len(voice.seconds_by_post))
