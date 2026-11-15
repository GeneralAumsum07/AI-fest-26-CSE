"""Task 4: the vision reader's retries, error handling and clipping (fake backend)."""

import pytest

from helpers import F, Queue
from selfaudit.models import Skipped
from selfaudit.perceive.vision import MAX_FINDINGS, MAX_TEXT, MAX_WHAT, VisionOutput, perceive_image


def test_bad_output_is_retried_once_with_the_short_prompt_then_given_up():
    b = Queue([ValueError(), ValueError()])
    out = perceive_image("p/media-0", b"img", "cap", b)
    assert isinstance(out, Skipped) and out.reason == "model_output"
    assert b.short_prompts == [False, True]


def test_out_of_memory_retries_at_lower_resolution():
    b = Queue([MemoryError(), VisionOutput(findings=[F()])])
    assert len(perceive_image("p/media-0", b"img", "", b)) == 1 and b.max_sides == [1280, 768]


def test_any_other_error_is_couldnt_check_not_a_crash():
    assert perceive_image("p/media-0", b"img", "", Queue([RuntimeError()])).reason == "model_error"


def test_unreadable_images_are_reported():
    assert perceive_image("p/media-0", b"img", "", Queue([VisionOutput(findings=[], unreadable=True)])).reason == "unreadable"


def test_oversized_output_is_clipped():
    huge = VisionOutput(findings=[F(extracted_text="9" * 50_000) for _ in range(200)])
    huge.findings[0].what = "x" * 5000
    out = perceive_image("p/media-0", b"img", "", Queue([huge]))
    assert len(out) == MAX_FINDINGS and len(out[0].what) == MAX_WHAT and len(out[0].extracted_text) == MAX_TEXT
    assert all(f.reader == "vision" and f.item_id == "p/media-0" for f in out)


def test_model_calls_are_bounded_in_length_and_time(monkeypatch, jpg):
    # A model stuck in a loop must stop at a token cap, and a hung server must
    # time out; otherwise one image stalls the whole audit while holding the GPU.
    import ollama

    from selfaudit import config
    from selfaudit.perceive.captions import OllamaCaptions
    from selfaudit.perceive.vision import OllamaVision

    made, calls = [], []

    class Reply:
        message = type("M", (), {"content": '{"findings": []}'})()

    class FakeClient:
        def __init__(self, **kw):
            made.append(kw)

        def chat(self, **kw):
            calls.append(kw)
            return Reply()

    monkeypatch.setattr(ollama, "Client", FakeClient)
    OllamaVision().describe(jpg.read_bytes(), "")
    OllamaCaptions().read("hello")
    assert all(kw.get("timeout") == config.MODEL_TIMEOUT_S for kw in made) and len(made) == 2
    assert all(c["options"]["num_predict"] == config.MODEL_MAX_TOKENS for c in calls) and len(calls) == 2


def test_the_model_must_fill_extracted_text(monkeypatch, jpg):
    # Ollama's constrained decoding lets a model skip any field the schema
    # does not require. qwen3.5:4b skipped extracted_text on a legible mock
    # Aadhaar, so the number never reached the checksum check and the ID was
    # "Not sure" (debugged 2026-11-15). The schema sent must require it.
    import ollama

    from selfaudit.perceive.vision import OllamaVision

    calls = []

    class Reply:
        message = type("M", (), {"content": '{"findings": []}'})()

    class FakeClient:
        def __init__(self, **kw):
            pass

        def chat(self, **kw):
            calls.append(kw)
            return Reply()

    monkeypatch.setattr(ollama, "Client", FakeClient)
    OllamaVision().describe(jpg.read_bytes(), "")
    schema = calls[0]["format"]
    assert "extracted_text" in schema["$defs"]["VisionFinding"]["required"]
    # Same failure, second field (debugged 2026-11-15, dev-012): the model
    # called a card "a mock student identity card" but skipped id_subtype, so
    # the college ID never became INSTITUTION. Required (still nullable), it
    # answered "institutional" for the student card and "government" for PAN.
    assert "id_subtype" in schema["$defs"]["VisionFinding"]["required"]


def test_schema_rejects_an_invented_category():
    with pytest.raises(ValueError):
        VisionOutput.model_validate_json('{"findings": [{"category": "SSN", "what": "x", "model_confidence": "high"}]}')


@pytest.mark.gpu
def test_real_model_answers_in_schema(jpg):
    from selfaudit.perceive.vision import OllamaVision

    out = perceive_image("p/media-0", jpg.read_bytes(), "", OllamaVision())
    assert isinstance(out, list)
