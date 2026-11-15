"""Caption reading plus an independent name cross-check (spec 7.6).

The caption reader is the vision model in text mode. On its own it is one
support, so its findings are only "likely". A second, unrelated model (GLiNER,
a small named-entity model) can back a finding when it finds the same name
with a fitting label; two independent readers agreeing is what "confirmed"
means. GLiNER runs on the CPU so the GPU stays with the vision model.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel

from selfaudit import config
from selfaudit.ingest.textfix import normalise
from selfaudit.models import RawFinding

CaptionCategory = Literal["FAMILY_RELATION", "AWAY_STATUS", "INSTITUTION", "CONTACT"]

# Which name label can back which caption category. Locations back nothing:
# a place name alone does not say the person is away right now.
_BACKS = {"person": "FAMILY_RELATION", "organization": "INSTITUTION"}


class CaptionFinding(BaseModel):
    category: CaptionCategory
    what: str
    value: str  # must be copied from the caption; grounding drops it otherwise


class CaptionOutput(BaseModel):
    findings: list[CaptionFinding]


class CaptionBackend(Protocol):
    def read(self, caption: str) -> list[CaptionFinding]: ...


class NameReader(Protocol):
    def names(self, text: str) -> list[tuple[str, str]]: ...


CAPTION_PROMPT = """You read one Instagram caption written by the account owner. List only these, if present:
- FAMILY_RELATION: a named or implied family member or relationship (mother, Amma, my brother Ravi).
- AWAY_STATUS: a statement that the writer is away, travelling or not at home now.
- INSTITUTION: a named college, school or employer.
- CONTACT: a phone number, email address or address written out.
Copy the exact words from the caption into value; do not paraphrase or translate. Most captions have nothing; an empty list is the usual answer.

Caption: {caption}"""


class OllamaCaptions:
    """The vision model again, text only, so no second model needs GPU memory."""

    def __init__(self, model: str = config.VISION_MODEL, host: str = config.OLLAMA_HOST):
        import ollama

        self.model = model
        # Same bounds as the vision reader (config.MODEL_*): a timeout raises,
        # and analyse_items turns it into a caption_error line.
        self._client = ollama.Client(host=host, timeout=config.MODEL_TIMEOUT_S)

    def read(self, caption: str) -> list[CaptionFinding]:
        kwargs = {} if config.VISION_THINK is None else {"think": config.VISION_THINK}
        reply = self._client.chat(
            model=self.model,
            messages=[{"role": "user", "content": CAPTION_PROMPT.format(caption=caption)}],
            format=CaptionOutput.model_json_schema(),
            options={"temperature": 0, "num_predict": config.MODEL_MAX_TOKENS}, **kwargs,
        )
        return CaptionOutput.model_validate_json(reply.message.content).findings


class GlinerNames:
    """GLiNER on the CPU; loaded on first use because loading takes seconds."""

    def __init__(self, model_name: str = "urchade/gliner_multi_pii-v1"):
        self.model_name = model_name
        self._model = None

    def names(self, text: str) -> list[tuple[str, str]]:
        if self._model is None:
            from gliner import GLiNER

            self._model = GLiNER.from_pretrained(self.model_name, map_location="cpu")
        ents = self._model.predict_entities(text, ["person", "organization", "location"], threshold=0.5)
        return [(e["text"], e["label"]) for e in ents]


def is_latin(text: str) -> bool:
    """True when most letters are Latin script (GLiNER's languages do not
    include Hindi or Telugu, so it is skipped for those captions)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    latin = sum(1 for c in letters if ord(c) < 0x250)
    return latin * 2 > len(letters)


def _overlap(a: str, b: str) -> bool:
    na, nb = normalise(a), normalise(b)
    return bool(na and nb) and (na in nb or nb in na)


def read_caption(item_id: str, caption: str, backend: CaptionBackend,
                 names: NameReader | None) -> list[RawFinding]:
    """Caption findings, each followed by a "ner" finding when a name backs it."""
    if not caption.strip():
        return []
    found = backend.read(caption)
    out: list[RawFinding] = []
    try:
        ents = names.names(caption) if (names is not None and found and is_latin(caption)) else []
    except Exception:
        # The name reader only ever adds a second support. If it fails, keep
        # the caption model's findings at one support ("likely") instead of
        # letting the exception discard them and mark the caption unchecked.
        ents = []
    for f in found:
        out.append(RawFinding(item_id=item_id, category=f.category, what=f.what,
                              extracted_text=f.value, value=f.value, reader="caption"))
        backer = next((t for t, label in ents if _BACKS.get(label) == f.category and _overlap(t, f.value)), None)
        if backer is not None:
            out.append(RawFinding(item_id=item_id, category=f.category, what=f.what,
                                  extracted_text=backer, value=backer, reader="ner"))
    return out
