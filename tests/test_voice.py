"""Task 9: voice exposure bands, on fakes for the three models."""

import numpy as np
import pytest

from selfaudit.models import VoiceResult
from selfaudit.perceive.voice import DefaultGate, band_for, drop_posts, voice_exposure

SR = 16000


class FakeVad:
    """One segment spanning the whole clip."""
    def segments(self, wav):
        return [(0.0, len(wav) / SR)] if len(wav) else []


class FakeEmbedder:
    """The first sample's sign marks the speaker."""
    def embed(self, wav):
        return np.array([1.0, 0.0]) if wav[0] > 0 else np.array([0.0, 1.0])


class FakeGate:
    """Mean absolute value above 0.5 means music under the speech."""
    def is_clean(self, wav):
        return float(np.abs(wav).mean()) <= 0.5


def speaker(sign, seconds, noisy=False):
    return np.full(int(seconds * SR), sign * (0.9 if noisy else 0.1), dtype=np.float32)


@pytest.fixture
def voice_fakes():
    return dict(vad=FakeVad(), embedder=FakeEmbedder(), gate=FakeGate())


@pytest.mark.parametrize("s,band", [(0, "none"), (4.9, "low"), (5, "moderate"), (30, "moderate"), (30.1, "high")])
def test_bands(s, band):
    assert band_for(s) == band


def test_only_the_enrolled_speaker_is_counted(voice_fakes):
    clips = {"a": speaker(+1, 40), "b": speaker(-1, 40)}          # 40 s each, two different people
    v = voice_exposure(clips, speaker(+1, 8), **voice_fakes)
    assert (round(v.clean_seconds), v.band, v.enrolled, v.seconds_by_post) == \
        (40, "high", True, {"a": pytest.approx(40, abs=1)})


def test_without_enrolment_the_band_is_capped(voice_fakes):
    v = voice_exposure({"a": speaker(+1, 40), "b": speaker(-1, 10)}, None, **voice_fakes)
    assert (v.band, v.enrolled, list(v.seconds_by_post)) == ("moderate", False, ["a"])   # dominant speaker, capped


def test_speech_under_music_is_not_counted(voice_fakes):
    assert voice_exposure({"a": speaker(+1, 40, noisy=True)}, speaker(+1, 8), **voice_fakes).band == "none"


def test_short_scraps_are_ignored(voice_fakes):
    assert voice_exposure({"a": speaker(+1, 0.6)}, speaker(+1, 8), **voice_fakes).clean_seconds == 0


def test_dropping_posts_recomputes_the_band():
    v = VoiceResult(clean_seconds=50, band="high", enrolled=True, seconds_by_post={"a": 25, "b": 15, "c": 10})
    assert drop_posts(v, ["a"]).band == "moderate" and drop_posts(v, ["a", "b", "c"]).band == "none"


def test_default_gate_separates_gappy_speech_from_speech_over_a_bed():
    rng = np.random.default_rng(0)
    t = np.arange(2 * SR) / SR
    # Syllable-like bursts: on for 150 ms, off for 100 ms.
    bursts = ((t % 0.25) < 0.15).astype(np.float32) * np.sin(2 * np.pi * 200 * t).astype(np.float32) * 0.3
    clean = bursts + rng.normal(0, 0.001, len(t)).astype(np.float32)
    bed = bursts + 0.2 * np.sin(2 * np.pi * 330 * t).astype(np.float32)   # music never stops
    gate = DefaultGate()
    assert gate.is_clean(clean) and not gate.is_clean(bed)
