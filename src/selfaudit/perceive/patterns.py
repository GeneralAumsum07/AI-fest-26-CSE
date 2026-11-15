"""The rules layer: India-specific pattern recognisers and small word lists.

Why a rules layer next to the AI readers: patterns with checksums (Aadhaar's
Verhoeff, a card's Luhn) are almost never wrong when they fire, so they are
the strongest second support a model finding can get (spec 7.6). On their own
they are also the no-AI baseline the evaluation compares against.

Names and places are deliberately not detected here: that is the job of the
caption reader and the name cross-check, and a rules layer that guessed names
would muddy the ablation.
"""

from __future__ import annotations

import re
from functools import lru_cache

from selfaudit import config
from selfaudit.models import RawFinding

# Presidio entity -> (our category, id_subtype). Everything else is ignored.
_ENTITY_MAP = {
    "IN_AADHAAR": ("ID_DOCUMENT", "government"),
    "IN_PAN": ("ID_DOCUMENT", "government"),
    "IN_PASSPORT": ("ID_DOCUMENT", "government"),
    "IN_VOTER": ("ID_DOCUMENT", "government"),
    "CREDIT_CARD": ("FINANCIAL", None),
    "PHONE_NUMBER": ("CONTACT", None),
    "EMAIL_ADDRESS": ("CONTACT", None),
}
_WHAT = {
    "IN_AADHAAR": "an Aadhaar-format number", "IN_PAN": "a PAN-format number",
    "IN_PASSPORT": "a passport-format number", "IN_VOTER": "a voter-ID-format number",
    "CREDIT_CARD": "a card number", "PHONE_NUMBER": "a phone number",
    "EMAIL_ADDRESS": "an email address",
}


def build_analyzer():
    """A Presidio analyzer with India recognisers and no NER.

    Built once and reused: loading spaCy is the slow part.
    """
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_analyzer.predefined_recognizers import PhoneRecognizer

    registry = RecognizerRegistry()
    # presidio-analyzer 2.2.362 has no country filter here (only languages),
    # and ships the India recognisers disabled; _ensure_india adds them below.
    registry.load_predefined_recognizers(languages=["en"])
    # Keep this layer pure rules: spaCy's NER would add PERSON/LOCATION guesses.
    registry.remove_recognizer("SpacyRecognizer")
    # Only Indian formats: with the default regions a 12-digit order number
    # can validate as some other country's phone number.
    registry.remove_recognizer("PhoneRecognizer")
    registry.add_recognizer(PhoneRecognizer(supported_regions=["IN"]))
    _ensure_india(registry)

    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        # The small model is enough: only tokens and lemmas for context words are used.
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }).create_engine()
    return AnalyzerEngine(registry=registry, nlp_engine=nlp, supported_languages=["en"])


def _ensure_india(registry) -> None:
    """Some Presidio versions ship the India recognisers disabled by default;
    add any that the country filter did not load."""
    from presidio_analyzer import predefined_recognizers as pr

    have = {e for r in registry.recognizers for e in r.supported_entities}
    for cls_name, entity in (("InAadhaarRecognizer", "IN_AADHAAR"), ("InPanRecognizer", "IN_PAN"),
                             ("InPassportRecognizer", "IN_PASSPORT"), ("InVoterRecognizer", "IN_VOTER")):
        cls = getattr(pr, cls_name, None)
        if cls is not None and entity not in have:
            registry.add_recognizer(cls())


def recognise(item_id: str, text: str, analyzer) -> list[RawFinding]:
    """Run the pattern recognisers over text (a caption, or text read off an image)."""
    if not text.strip():
        return []
    results = analyzer.analyze(text, language="en", score_threshold=config.SCORE_THRESHOLD)
    out: list[RawFinding] = []
    seen: set[tuple[str, str]] = set()
    for r in results:
        if r.entity_type not in _ENTITY_MAP:
            continue
        category, subtype = _ENTITY_MAP[r.entity_type]
        value = text[r.start:r.end]
        if (category, value) in seen:  # two recognisers on the same span count once
            continue
        seen.add((category, value))
        out.append(RawFinding(
            item_id=item_id, category=category, what=_WHAT[r.entity_type],
            extracted_text=value, value=value, reader="patterns", id_subtype=subtype,
        ))
    return out


# --- Word lists --------------------------------------------------------------

# English and Hinglish words that name a family member, matched as whole words.
_FAMILY_LATIN = [
    "mom", "mum", "mummy", "mommy", "mother", "dad", "daddy", "papa", "father",
    "amma", "nanna", "appa", "ammi", "abbu", "maa", "bhai", "bhaiya", "didi",
    "akka", "anna", "thambi", "chelli", "sister", "brother", "nani", "dadi",
    "grandma", "grandpa", "granny", "uncle", "aunty", "aunt", "chacha", "mama", "mausi",
]
# Devanagari and Telugu words: matched as substrings, because Python's word
# boundaries split these scripts at vowel signs.
_FAMILY_OTHER = [
    "माँ", "मां", "मम्मी", "पापा", "भाई", "भैया", "दीदी", "बहन", "पिताजी", "दादी", "नानी",
    "అమ్మ", "నాన్న", "అన్న", "అక్క", "తమ్ముడు", "చెల్లి",
]
_AWAY_LATIN = [
    r"off to", r"travel+ing", r"vacation", r"holiday", r"trip", r"airport", r"boarding",
    r"flying (?:to|out)", r"see you next week", r"back next week", r"out of town",
    r"till (?:mon|tues|wednes|thurs|fri|satur|sun)day", r"until (?:mon|tues|wednes|thurs|fri|satur|sun)day",
    # In transit right now (dev-011, "on the train to Chennai"). A named vehicle
    # is required: "on the way to college" is a commute, not being away.
    r"on (?:the|a|my) (?:train|flight|plane|bus|ferry|cab) to",
]
_AWAY_OTHER = ["✈", "छुट्टी", "यात्रा", "सफर", "ప్రయాణం", "సెలవు"]


# Phrases removed from a caption before the family list sees it. "Father's
# Day offers" (dev-032) names a holiday, not a relative; a caption that also
# says "papa" is still caught by "papa".
_NOT_FAMILY = re.compile(r"\b(?:father|mother|grandparents?)'?s?\s+day\b", re.IGNORECASE)
# A caption that says the trip is in the past. Spec 314 asks for travel that
# is recent; "throwback to the Ooty trip in 2021" (dev-030) says it is over.
_PAST_TRIP = re.compile(r"(?<![\w])(?:throwback|tbt|flashback|missing (?:this|that) trip)(?![\w])", re.IGNORECASE)


@lru_cache(maxsize=None)
def _latin(words: tuple[str, ...]) -> re.Pattern:
    return re.compile(r"(?<![\w])(?:" + "|".join(words) + r")(?![\w])", re.IGNORECASE)


def _hit(caption: str, latin: list[str], other: list[str]) -> str | None:
    m = _latin(tuple(latin)).search(caption)
    if m:
        return m.group(0)
    return next((w for w in other if w in caption), None)


def lexicon(item_id: str, caption: str) -> list[RawFinding]:
    """Family and away words in a caption.

    These are the second support for caption findings (spec 7.6): a caption
    model saying "mentions their mother" plus the word "Amma" is confirmed.
    """
    out: list[RawFinding] = []
    word = _hit(_NOT_FAMILY.sub(" ", caption), _FAMILY_LATIN, _FAMILY_OTHER)
    if word:
        out.append(RawFinding(item_id=item_id, category="FAMILY_RELATION",
                              what="a family word in the caption", extracted_text=word, reader="lexicon"))
    word = None if _PAST_TRIP.search(caption) else _hit(caption, _AWAY_LATIN, _AWAY_OTHER)
    if word:
        out.append(RawFinding(item_id=item_id, category="AWAY_STATUS",
                              what="a travel or away phrase in the caption", extracted_text=word, reader="lexicon"))
    return out
