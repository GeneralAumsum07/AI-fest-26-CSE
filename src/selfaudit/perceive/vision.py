"""The vision reader: one local model looks at each image (spec 7.5).

The model sits behind `VisionBackend` so every rule around it (retries,
clipping, error handling) is tested with a fake and no GPU. The real backend
talks to Ollama on the loopback address with a JSON schema, so the answer is
structured even when the model is small.
"""

from __future__ import annotations

import io
from typing import Literal, Protocol

from pydantic import BaseModel

from selfaudit import config
from selfaudit.models import RawFinding, Skipped

# Caps applied after validation. A small model can loop and emit thousands of
# findings or a page of "transcription"; we keep the head and never reject.
MAX_FINDINGS = 12
MAX_WHAT = 200
MAX_TEXT = 2000

VisionCategory = Literal["ID_DOCUMENT", "FINANCIAL", "TRAVEL_DOC", "CONTACT", "FAMILY_RELATION",
                         "AWAY_STATUS", "INSTITUTION", "FACE_CLEAR"]


class VisionFinding(BaseModel):
    category: VisionCategory
    what: str
    extracted_text: str = ""
    model_confidence: Literal["high", "medium", "low"]
    id_subtype: Literal["government", "institutional"] | None = None


class VisionOutput(BaseModel):
    findings: list[VisionFinding]
    unreadable: bool = False


def _answer_schema() -> dict:
    """The JSON schema Ollama constrains the model to.

    Same as VisionOutput's, except extracted_text is required. Constrained
    decoding lets a model skip any optional field, and qwen3.5:4b did: on a
    legible mock Aadhaar it named the ID but left extracted_text out, so the
    number never reached the checksum check and the ID came back "Not sure".
    Required, it transcribed the whole card (and stopped padding the answer
    with guessed categories). The Python default stays "" so parsing and the
    test fakes are unchanged; only what the model must emit changes.
    """
    schema = VisionOutput.model_json_schema()
    required = schema["$defs"]["VisionFinding"]["required"]
    # id_subtype too, for the same reason: on a college ID the model said
    # "student identity card" yet skipped the field, and grounding only turns
    # an *institutional* ID into INSTITUTION. Required, the field may still be
    # null (the schema allows it), but the model has to decide.
    for field in ("extracted_text", "id_subtype"):
        if field not in required:
            required.append(field)
    return schema


class VisionBackend(Protocol):
    def describe(self, image: bytes, caption: str, *, max_side: int = 1280,
                 short_prompt: bool = False) -> VisionOutput: ...

    def unload(self) -> None: ...


PROMPT = """You check one photo from a person's own Instagram account for details a scammer could use to impersonate them. List only what is actually visible.

Categories:
- ID_DOCUMENT: a government ID (Aadhaar, PAN, passport, voter ID, driving licence) or an institutional ID card. Set id_subtype to "government" or "institutional".
- FINANCIAL: a bank card, cheque, bank statement or UPI/payment screen.
- TRAVEL_DOC: a boarding pass, ticket or itinerary showing a name, PNR or travel date.
- CONTACT: a phone number, email address or home address written out.
- FAMILY_RELATION: text that names a family member or relationship (for example a birthday banner for "Amma").
- AWAY_STATUS: something that shows the person is travelling or away from home right now, for a day or more (a trip, a journey, a holiday). A ticket to a concert, film or match is an evening out, not away.
- INSTITUTION: the name of the person's own college, school or employer (signboard, ID card, uniform, letterhead). A college or company ID card counts. A shop, restaurant or brand on a bill or receipt, or the government department on an official ID, is not their institution.
- FACE_CLEAR: a clear, frontal, well-lit photo of exactly one person's face, good enough to reuse as a profile picture.

Rules:
- Transcribe text on documents, cards, tickets and signs exactly into extracted_text, and write ? for any character you cannot read; never guess a digit.
- Do not identify anyone and do not guess who a person is.
- A concert, film or match ticket with no name, PNR or travel date is not a finding: it is neither TRAVEL_DOC nor AWAY_STATUS.
- Set model_confidence to how sure you are.
- If you cannot make out the image at all, set unreadable to true.
- An ordinary photo has no findings, and that is the usual answer: return an empty list.

The post's caption, for context only: {caption}"""

SHORT_PROMPT = """List details in this photo in these categories only: ID_DOCUMENT, FINANCIAL, TRAVEL_DOC, CONTACT, FAMILY_RELATION, AWAY_STATUS, INSTITUTION, FACE_CLEAR. Transcribe text exactly into extracted_text; write ? for any character you cannot read; never guess a digit. An empty list is a normal answer."""


def _resize_jpeg(image: bytes, max_side: int) -> bytes:
    """Downsize so the longer side is at most max_side and re-encode as JPEG.

    Smaller images cost fewer vision tokens and less VRAM; on an out-of-memory
    reply the caller retries at a lower max_side.
    """
    from PIL import Image

    img = Image.open(io.BytesIO(image)).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


class OllamaVision:
    def __init__(self, model: str = config.VISION_MODEL, host: str = config.OLLAMA_HOST):
        import ollama

        self.model = model
        # A timeout raises inside describe(); perceive_image turns that into a
        # "couldn't check" line for this one image instead of a stalled audit.
        self._client = ollama.Client(host=host, timeout=config.MODEL_TIMEOUT_S)

    def _chat(self, **kwargs):
        if config.VISION_THINK is not None:
            kwargs["think"] = config.VISION_THINK
        return self._client.chat(model=self.model, **kwargs)

    def describe(self, image: bytes, caption: str, *, max_side: int = 1280,
                 short_prompt: bool = False) -> VisionOutput:
        import ollama

        prompt = SHORT_PROMPT if short_prompt else PROMPT.format(caption=caption or "(none)")
        try:
            reply = self._chat(
                messages=[{"role": "user", "content": prompt, "images": [_resize_jpeg(image, max_side)]}],
                format=_answer_schema(),
                # Temperature 0 so the same image gives the same findings, which
                # keeps development-split numbers reproducible.
                options={"temperature": 0, "num_predict": config.MODEL_MAX_TOKENS},
            )
        except ollama.ResponseError as exc:
            if "memory" in str(exc).lower():
                raise MemoryError(str(exc)) from exc
            raise RuntimeError(str(exc)) from exc
        except (OSError, ollama.RequestError) as exc:
            raise RuntimeError(str(exc)) from exc
        # A pydantic ValidationError is a ValueError, which is what the caller
        # treats as "output did not parse, retry with the short prompt".
        return VisionOutput.model_validate_json(reply.message.content)

    def unload(self) -> None:
        """Free the GPU for the next stage: an empty request with keep_alive=0."""
        try:
            self._client.chat(model=self.model, messages=[], keep_alive=0)
        except Exception:
            pass  # unloading is best effort; Ollama evicts idle models anyway


def _clip(out: VisionOutput, item_id: str) -> list[RawFinding]:
    return [
        RawFinding(
            item_id=item_id, category=f.category, what=f.what[:MAX_WHAT],
            extracted_text=f.extracted_text[:MAX_TEXT], model_confidence=f.model_confidence,
            reader="vision", id_subtype=f.id_subtype,
        )
        for f in out.findings[:MAX_FINDINGS]
    ]


def perceive_image(item_id: str, image: bytes, caption: str,
                   backend: VisionBackend) -> list[RawFinding] | Skipped:
    """Run the vision model on one image with bounded retries.

    Each failure kind gets at most one retry, chosen to fix that failure:
    unparseable output -> the short prompt; out of memory -> a smaller image.
    Anything else is "couldn't check", never a crash.
    """
    max_side, short = 1280, False
    retried_parse = retried_memory = False
    while True:
        try:
            out = backend.describe(image, caption, max_side=max_side, short_prompt=short)
        except MemoryError:
            if retried_memory:
                return Skipped(ref=item_id, reason="out_of_memory")
            retried_memory, max_side = True, 768
            continue
        except ValueError:
            if retried_parse:
                return Skipped(ref=item_id, reason="model_output")
            retried_parse, short = True, True
            continue
        except Exception:
            return Skipped(ref=item_id, reason="model_error")
        if out.unreadable:
            return Skipped(ref=item_id, reason="unreadable")
        return _clip(out, item_id)
