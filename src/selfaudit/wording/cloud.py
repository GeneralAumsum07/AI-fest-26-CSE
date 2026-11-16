"""Optional cloud wording, behind the redaction boundary.

Every failure path ends in the offline templates, so the cloud can only make
the wording nicer, never make the report worse or late.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from selfaudit.wording.payload import LeakError, ReportText, WordingPayload, assert_no_leak, leaks
from selfaudit.wording.templates import render_local

MAX_FIELD = 400

INSTRUCTIONS = """You write the text of a privacy report for a college student in India.
The JSON below lists attack recipes (R1 = a phone call to their family in their voice,
R2 = a copy of their profile, R3 = misuse of their ID document) with what an attacker
has and still needs, and ranked fixes. Explain each risk and each fix in plain words,
in the language given by "language" (en, hi or te). Describe only. Never write a message,
script or dialogue a scammer could use. Never say the user is "safe" and never use
percentages. Every field must be under 400 characters.
Use neutral product wording. Do not describe the application as "I" or "we".
Return only JSON of this shape:
{"summary": str, "recipes": {"R1": {"title": str, "reasons": str, "advice": str}, ...}, "fixes": [str, ...]}
"""


def make_call_llm() -> Callable[[str], str] | None:
    """Which provider to call is the owner's open question (spec 17, question 1).

    TBD: returns None (offline templates) until Rachit names a provider. If it
    is the Anthropic API, read the claude-api skill before writing the call.
    """
    return None


def _acceptable(text: ReportText, payload: WordingPayload, secrets: set[str]) -> bool:
    fields = [text.summary, *text.fixes]
    for r in text.recipes.values():
        fields += [r.title, r.reasons, r.advice]
    if any(len(f) > MAX_FIELD for f in fields):
        return False
    # Every recipe the page will draw must have text.
    if not {r.id for r in payload.recipes} <= set(text.recipes):
        return False
    return not leaks(text.model_dump_json(), secrets)


def word_report(payload: WordingPayload, secrets: set[str], *, call_llm: Callable[[str], str] | None,
                timeout_s: float = 8.0) -> tuple[ReportText, bool]:
    """(text, was_sent). was_sent is True whenever the payload left the laptop,
    even if the answer was then rejected: the "What left this laptop?" view
    must be honest about the sending, not about the success."""
    local = render_local(payload)
    try:
        assert_no_leak(payload, secrets)
    except LeakError:
        return local, False
    if call_llm is None:
        return local, False

    prompt = INSTRUCTIONS + "\n" + payload.model_dump_json()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        answer = pool.submit(call_llm, prompt).result(timeout=timeout_s)
        text = ReportText.model_validate(json.loads(answer))
    except Exception:
        return local, True
    finally:
        # Do not wait for a hung call; the thread finishes or dies with the process.
        pool.shutdown(wait=False)
    return (text, True) if _acceptable(text, payload, secrets) else (local, True)
