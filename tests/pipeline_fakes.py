"""Scripted fakes and persona specs shared by the pipeline, wording and app tests.

Every model is faked except Presidio: the fakes key off the caption, so a
test states its scenario in captions ("#id", "Amma") and the pattern layer
still has to recognise the real checksum-valid number.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

import numpy as np

from selfaudit.devtools.persona import PersonaPost, PersonaSpec
from selfaudit.devtools.synthetic import valid_aadhaar
from selfaudit.perceive.captions import CaptionFinding
from selfaudit.perceive.vision import VisionFinding, VisionOutput
from selfaudit.recipes import LEVEL_RANK

UTC = timezone.utc
SR = 16000
_N = valid_aadhaar(random.Random(7))
AADHAAR = f"{_N[:4]} {_N[4:8]} {_N[8:]}"


def speaker(sign, seconds):
    return np.full(int(seconds * SR), sign * 0.1, dtype=np.float32)


class ScriptedVision:
    def describe(self, image, caption, *, max_side=1280, short_prompt=False):
        out = []
        if "#id" in caption:
            out.append(VisionFinding(category="ID_DOCUMENT", what="an identity card", extracted_text=AADHAAR,
                                     model_confidence="high", id_subtype="government"))
        if "#face" in caption:
            out.append(VisionFinding(category="FACE_CLEAR", what="a clear face", model_confidence="high"))
        return VisionOutput(findings=out)

    def unload(self):
        pass


class AlwaysRaises(ScriptedVision):
    def describe(self, *a, **k):
        raise RuntimeError("dead")


class ScriptedCaptions:
    def read(self, caption):
        out = []
        if "Amma" in caption:
            out.append(CaptionFinding(category="FAMILY_RELATION", what="names a parent", value="Amma"))
        if "Mahindra University" in caption:
            out.append(CaptionFinding(category="INSTITUTION", what="names a university", value="Mahindra University"))
        return out


class ScriptedNames:
    def names(self, text):
        return [("Mahindra University", "organization")] if "Mahindra University" in text else []


class WholeClip:
    def segments(self, wav):
        return [(0.0, len(wav) / SR)] if len(wav) else []


class SameVoice:
    def embed(self, wav):
        return np.array([1.0, 0.0])


class PassAll:
    def is_clean(self, wav):
        return True


def drops(fix, before, after):
    """Test weight: total level steps lowered across all recipes."""
    now = {r.recipe_id: r.level for r in after}
    return sum(LEVEL_RANK[r.level] - LEVEL_RANK[now.get(r.recipe_id)] for r in before)


def _d(day):
    return datetime(2026, 11, day, tzinfo=UTC)


def HIGH_EXPOSURE(jpg, mp4_file):
    return PersonaSpec(name="Asha Rao", username="asha.rao", bio="", private=False, posts=[
        PersonaPost("#id", [jpg], _d(1)),
        PersonaPost("Happy birthday Amma", [jpg], _d(2)),
        PersonaPost("First day at Mahindra University", [jpg], _d(3)),
        PersonaPost("#face one", [jpg], _d(4)),
        PersonaPost("#face two", [jpg], _d(5)),
        PersonaPost("#face three", [jpg], _d(6)),
        PersonaPost("singing", [mp4_file(20.0, name="v1.mp4")], _d(7)),
        PersonaPost("talking", [mp4_file(20.0, name="v2.mp4")], _d(8)),
    ])


def STORY_ONLY_VOICE_AND_ID(jpg, mp4_file):
    return PersonaSpec(name="Asha Rao", username="asha.rao", bio="", private=False, posts=[
        PersonaPost("#id", [jpg], _d(1), source="story"),
        PersonaPost("", [mp4_file(40.0, name="s.mp4")], _d(2), source="story"),
    ])


def ONE_VIDEO_SHOWING_AN_ID(mp4_file):
    return PersonaSpec(name="Asha Rao", username="asha.rao", bio="", private=False, posts=[
        PersonaPost("#id", [mp4_file(4.0)], _d(1)),
    ])


def LUNCH_ONLY(jpg):
    return PersonaSpec(name="Asha Rao", username="asha.rao", bio="", private=False,
                       posts=[PersonaPost("lunch", [jpg], _d(1))])
