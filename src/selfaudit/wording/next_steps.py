"""Fixed text that is never reworded: next steps for an exposed ID, and the
family card's "a caller might know" lines.

Why a separate module from templates.py: the report's other text can be
rewritten by the cloud wording (Hindi, Telugu). Official steps cannot. A
reworded service name or a wrong number is worse than English, so these lines
go to the page as they are and never into the wording payload.

Every service named here was checked on its official site on 2026-11-16:
- sancharsaathi.gov.in lists "Know Mobile Connections in Your Name".
- uidai.gov.in lists "Lock/Unlock Biometrics" (website or Aadhaar app; it
  needs the mobile number registered with the Aadhaar).
- 1930 and cybercrime.gov.in were already on the safety card.
If a service is renamed, change the text here and re-check it; do not guess.
"""

from __future__ import annotations

from selfaudit.models import Finding, RecipeResult

# Shown under the "Misuse of your ID document" card. Things a person can do
# tonight, in the order that helps most: see the damage, stop more, report it.
ID_STEPS = [
    "See which mobile numbers are registered in your name: open \"Know Mobile Connections in Your Name\" "
    "on sancharsaathi.gov.in, and report any number that is not yours.",
    "If the document was your Aadhaar, lock your biometrics: \"Lock/Unlock Biometrics\" on uidai.gov.in "
    "or in the Aadhaar app. It needs the mobile number registered with your Aadhaar.",
    "If you see a loan, SIM or account you did not open, call 1930 or report it at cybercrime.gov.in.",
]
_STEPS = {"R3": ID_STEPS}

# The family card block. Categories only, never values: a printed card that is
# lost on a bus must give nothing away. It says what a caller could KNOW, never
# what a caller would SAY, which keeps it out of writing a scam script.
CALLER_LINES = {
    "FAMILY_RELATION": "A family member's name",
    "INSTITUTION": "Where they study or work",
    "AWAY_STATUS": "That they are travelling right now",
    "VOICE": "What their voice sounds like",
}


def next_steps(recipes: list[RecipeResult]) -> dict[str, list[str]]:
    """Steps for each recipe whose card the page shows (a level, or Needs review)."""
    return {r.recipe_id: _STEPS[r.recipe_id] for r in recipes
            if r.recipe_id in _STEPS and (r.level or r.not_sure)}


def caller_knows(findings: list[Finding], recipes: list[RecipeResult], voice_band: str) -> list[str]:
    """The card's lines, in CALLER_LINES order, each only if the audit found it.

    "Travelling right now" is taken from the recipes' amplifiers, not from the
    raw findings: the recipes already drop away posts older than the window,
    and a card a parent keeps for months must not say "right now" about a
    trip that ended in March. A travel document counts as being away, as it
    does in the recipes.
    """
    have = {f.category for f in findings}
    if any(a in ("AWAY_STATUS", "TRAVEL_DOC") for r in recipes for a in r.amplifiers):
        have.add("AWAY_STATUS")
    else:
        have.discard("AWAY_STATUS")
    if voice_band != "none":
        have.add("VOICE")
    return [line for cat, line in CALLER_LINES.items() if cat in have]
