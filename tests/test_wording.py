"""Task 13: the redacted payload, the leak check, and offline templates."""

import json
import re

import pytest
from pydantic import ValidationError

from selfaudit.ingest.textfix import normalise
from selfaudit.models import VoiceResult
from selfaudit.wording.cloud import word_report
from selfaudit.wording.payload import (FixPayload, LeakError, RecipePayload, WordingPayload, assert_no_leak,
                                       build_payload)
from selfaudit.wording.templates import render_local, voice_note

LEAKY_PAYLOAD = WordingPayload(recipes=[], fixes=[FixPayload(rank=1, action="remove", post_ref="post 9876",
                                                             effects=["ends R3"])],
                               language="en", private=False, couldnt_check=0)


def test_payload_matches_the_spec_shape(high_state):
    p = build_payload(high_state.report(), high_state.profile)
    r1 = next(r for r in p.recipes if r.id == "R1")
    assert r1.level == "high" and {"voice:high", "family_relation"} <= set(r1.has) and r1.missing == []
    assert re.fullmatch(r"post \d+( and \d+ more)?", p.fixes[0].post_ref) and p.fixes[0].rank == 1


def test_the_payload_type_cannot_hold_free_text():
    with pytest.raises(ValidationError):
        RecipePayload(id="R1", level="high", has=["Amma"], missing=[])
    with pytest.raises(ValidationError):
        FixPayload(rank=1, action="remove", post_ref="the Goa photo", effects=["ends R3"])


def test_nothing_extracted_is_in_the_real_payload(high_state):
    payload = build_payload(high_state.report(), high_state.profile)
    assert_no_leak(payload, high_state.secrets())                 # does not raise
    text = payload.model_dump_json().casefold()
    assert all(normalise(s) not in normalise(text) for s in high_state.secrets() if len(s) >= 4)


def test_the_leak_check_itself_works():
    with pytest.raises(LeakError):
        assert_no_leak(LEAKY_PAYLOAD, {"9876"})


def test_a_leak_means_nothing_is_sent():
    sent = []
    text, was_sent = word_report(LEAKY_PAYLOAD, {"9876"}, call_llm=lambda prompt: sent.append(prompt) or "{}")
    assert sent == [] and was_sent is False and text.recipes is not None


@pytest.mark.parametrize("call_llm", [None, lambda p: (_ for _ in ()).throw(TimeoutError()), lambda p: "not json",
                                      lambda p: json.dumps({"summary": "x" * 5000, "recipes": {}, "fixes": []})])
def test_any_cloud_failure_falls_back_to_templates(high_state, call_llm):
    payload = build_payload(high_state.report(), high_state.profile)
    text, _ = word_report(payload, high_state.secrets(), call_llm=call_llm)
    assert text == render_local(payload)


def test_a_cloud_answer_that_echoes_a_secret_is_rejected(high_state):
    payload = build_payload(high_state.report(), high_state.profile)
    secret = next(s for s in high_state.secrets() if len(s) >= 4)
    good = render_local(payload).model_copy(update={"summary": f"About {secret}."})
    text, was_sent = word_report(payload, high_state.secrets(), call_llm=lambda p: good.model_dump_json())
    assert text == render_local(payload) and was_sent is True


def test_template_wording_rules(high_state, empty_state):
    text = render_local(build_payload(high_state.report(), high_state.profile))
    assert text.recipes["R1"].title == "A phone call to your family in your voice"
    assert text.recipes["R3"].title == "Misuse of your ID document"
    assert text.recipes["R2"].title == "A copy of your profile"
    everything = " ".join([text.summary, *text.fixes, *(t.reasons + t.advice for t in text.recipes.values())])
    assert not re.search(r"\bsafe\b", everything, re.I) and not re.search(r"\d+\s*%", everything)
    assert any("misuse of your ID document" in f for f in text.fixes)    # "ID" keeps its capitals
    empty = render_local(build_payload(empty_state.report(), empty_state.profile))
    assert "urgent" in empty.summary.lower()
    # Report copy describes the product's result, rather than impersonating a
    # person conducting the audit. Exercise both populated and empty reports.
    assert not re.search(r"\b(?:I|we)\b", everything + " " + empty.summary, re.I)


def test_no_enrolment_line():
    v = VoiceResult(clean_seconds=20, band="moderate", enrolled=False, seconds_by_post={"a": 12, "b": 8})
    note = voice_note(v)
    assert "2 videos" in note and "voice reference" in note
    # Speaker matching is approximate; recording a sentence cannot guarantee
    # certainty. The wording must work for YouTube uploads as well as reels.
    assert not re.search(r"\b(?:I|we|sure|certain)\b", note, re.I)
    assert voice_note(v.model_copy(update={"enrolled": True})) is None


def _fix_payload(platform):
    fixes = [FixPayload(rank=1, action="archive", post_ref="post 3", effects=["ends R3"]),
             FixPayload(rank=2, action="crop", post_ref="post 2", effects=[]),
             FixPayload(rank=3, action="edit_caption", post_ref="post 1", effects=[])]
    return WordingPayload(recipes=[], fixes=fixes, language="en", private=False, couldnt_check=0,
                          platform=platform)


def test_youtube_fixes_use_youtube_actions_and_say_video():
    # YouTube has no archive and a published video cannot be cropped.
    fixes = render_local(_fix_payload("youtube")).fixes
    assert fixes[0].startswith("1. Set video 3 to Private")
    assert fixes[1] == "2. Blur the detail in video 2."
    assert fixes[2] == "3. Edit the title or description of video 1."
    assert not any("Archive" in f or "post" in f for f in fixes)


def _recipe_payload(platform):
    recipes = [RecipePayload(id="R1", level="high", not_sure=True, has=["family_relation", "away_status:recent"],
                             missing=[]),
               RecipePayload(id="R3", level="high", has=["id_document"], missing=[])]
    return WordingPayload(recipes=recipes, fixes=[], language="en", private=False, couldnt_check=0,
                          platform=platform)


def test_youtube_recipe_text_says_video_not_post():
    # The recipe reasons and advice sit on the same screen as "Set video 1 to Private".
    text = render_local(_recipe_payload("youtube"))
    words = " ".join(f for r in text.recipes.values() for f in (r.reasons, r.advice))
    assert "Your videos show videos that name your family" in words
    assert "Take down the video that shows the number" in words
    assert not re.search(r"\bposts?\b", words)


def test_instagram_recipe_text_still_says_post():
    words = " ".join(r.reasons + r.advice for r in render_local(_recipe_payload("instagram")).recipes.values())
    assert "Your posts show posts that name your family" in words and "Take down the post" in words


def test_instagram_fixes_are_unchanged():
    fixes = render_local(_fix_payload("instagram")).fixes
    assert fixes[0].startswith("1. Archive post 3") and fixes[1] == "2. Crop the detail out of post 2."


def test_platform_reaches_the_report_and_the_payload(high_state):
    from selfaudit.pipeline import AuditState
    yt = AuditState(profile=high_state.profile.model_copy(update={"platform": "youtube"}),
                    findings=high_state.findings, voice=high_state.voice)
    assert yt.report().platform == "youtube" and high_state.report().platform == "instagram"
    assert build_payload(yt.report(), yt.profile).platform == "youtube"
