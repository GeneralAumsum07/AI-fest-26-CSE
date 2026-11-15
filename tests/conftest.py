"""Shared test fixtures. Each later task adds the helpers it first needs."""

from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def jpg(tmp_path: Path) -> Path:
    """A tiny real JPEG. Real bytes (not a stub) so the export reader and the
    vision client exercise the same decode path they use on a phone photo."""
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (64, 64), (200, 120, 40)).save(path, "JPEG")
    return path


_TINY_CAPTIONS = """
- {text: "call me on +91 98765 43210", categories: [CONTACT], values: {phone: "+91 98765 43210"}}
- {text: "mail me asha@example.com", categories: [CONTACT], values: {email: "asha@example.com"}}
- {text: "Happy birthday Amma", categories: [FAMILY_RELATION], values: {}}
- {text: "भाई के साथ", categories: [FAMILY_RELATION], values: {}}
- {text: "off to Goa till Sunday", categories: [AWAY_STATUS], values: {}}
- {text: "airport vibes, back next week", categories: [AWAY_STATUS], values: {}}
- {text: "sunset", categories: [], values: {}}
- {text: "chai time", categories: [], values: {}}
- {text: "order 123456789012 arrived", categories: [], values: {}, hard_negative: true}
- {text: "Mother's Day sale at the mall", categories: [], values: {}, hard_negative: true}
- {text: "goa vibes from 2019 lol", categories: [], values: {}, hard_negative: true}
- {text: "helpline 1930 for cyber fraud", categories: [], values: {}, hard_negative: true}
"""


@pytest.fixture
def tiny_sources(tmp_path: Path) -> Path:
    """A minimal sources folder: one photo of each kind and a small caption list.
    generate_set reuses sources as often as it needs, so one of each is enough."""
    src = tmp_path / "sources"
    for sub, color in (("backgrounds", (90, 140, 90)), ("faces", (220, 180, 160)),
                       ("institution", (150, 150, 200))):
        (src / sub).mkdir(parents=True)
        Image.new("RGB", (320, 240), color).save(src / sub / "a.jpg", "JPEG")
    (src / "captions.yaml").write_text(_TINY_CAPTIONS, encoding="utf-8")
    return src


def _encode_mp4(seconds: float, audio: bool = True) -> bytes:
    """Solid-colour frames plus a 440 Hz tone, encoded with FFmpeg's built-in
    mpeg4 and aac encoders (always present in PyAV's wheel, unlike x264)."""
    import io

    import av
    import numpy as np

    fps, rate = 5, 16000
    buf = io.BytesIO()
    with av.open(buf, "w", format="mp4") as c:
        vs = c.add_stream("mpeg4", rate=fps)
        vs.width, vs.height, vs.pix_fmt = 64, 64, "yuv420p"
        as_ = c.add_stream("aac", rate=rate, layout="mono") if audio else None
        for i in range(int(seconds * fps)):
            # Colour changes per frame so seeking to different times gives different images.
            arr = np.full((64, 64, 3), (i * 7) % 256, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            frame.pts = i
            c.mux(vs.encode(frame))
        c.mux(vs.encode())
        if as_ is not None:
            n = int(seconds * rate)
            tone = (0.5 * np.sin(2 * np.pi * 440 * np.arange(n) / rate)).astype(np.float32)
            step = 1024  # AAC frame size
            for start in range(0, n, step):
                chunk = tone[start:start + step]
                af = av.AudioFrame.from_ndarray(chunk[None, :], format="fltp", layout="mono")
                af.sample_rate, af.pts = rate, start
                c.mux(as_.encode(af))
            c.mux(as_.encode())
    return buf.getvalue()


@pytest.fixture
def mp4():
    """Factory: mp4(seconds, *, audio=True) -> bytes."""
    def make(seconds: float, *, audio: bool = True) -> bytes:
        return _encode_mp4(seconds, audio)
    return make


@pytest.fixture
def mp4_file(tmp_path: Path):
    """Factory: the same video written to a temp path, for building personas."""
    def make(seconds: float, *, audio: bool = True, name: str = "clip.mp4") -> Path:
        p = tmp_path / name
        p.write_bytes(_encode_mp4(seconds, audio))
        return p
    return make


@pytest.fixture(scope="session")
def analyzer():
    """The real Presidio analyzer, built once per test session (spaCy load is slow)."""
    from selfaudit.perceive.patterns import build_analyzer
    return build_analyzer()


@pytest.fixture
def scripted_backends(analyzer, monkeypatch):
    from pipeline_fakes import PassAll, SameVoice, ScriptedCaptions, ScriptedNames, ScriptedVision, WholeClip, drops
    from selfaudit import fixes
    from selfaudit.pipeline import AllBackends

    # The product weight is Rachit's (Task 11). These tests are about the
    # pipeline, not the ranking, so they use the test weight.
    monkeypatch.setattr(fixes, "fix_weight", drops)
    return AllBackends(vision=ScriptedVision(), captions=ScriptedCaptions(), names=ScriptedNames(),
                       analyzer=analyzer, vad=WholeClip(), embedder=SameVoice(), gate=PassAll())


@pytest.fixture
def high_state(tmp_path, jpg, mp4_file, scripted_backends):
    from pipeline_fakes import HIGH_EXPOSURE, speaker
    from selfaudit.devtools.persona import build_persona
    from selfaudit.pipeline import run_audit
    return run_audit(build_persona(HIGH_EXPOSURE(jpg, mp4_file), tmp_path / "high"), speaker(+1, 8),
                     scripted_backends)


@pytest.fixture
def empty_state(tmp_path, jpg, scripted_backends):
    from pipeline_fakes import LUNCH_ONLY
    from selfaudit.devtools.persona import build_persona
    from selfaudit.pipeline import run_audit
    return run_audit(build_persona(LUNCH_ONLY(jpg), tmp_path / "empty"), None, scripted_backends)


@pytest.fixture
def tiny_split(tmp_path, tiny_sources) -> Path:
    """A small labelled dev-style split built from the tiny sources (Task 15)."""
    from selfaudit.devtools.synthetic import generate_set
    out = tmp_path / "split"
    generate_set(out, split="dev", seed=3, sources=tiny_sources)
    return out


@pytest.fixture
def call_log() -> list[str]:
    """Shared order-of-calls log: every fake backend appends its name here, so a
    test can assert the GPU ordering (all vision, then captions, then unload)."""
    return []


@pytest.fixture
def fake_backends(call_log):
    """Backends made of fakes that return nothing and log every call.

    analyzer is None on purpose: Presidio is the one real dependency the runner
    has, and these tests are about ordering and isolation, not pattern hits
    (tests/test_patterns.py covers those against the real analyzer).
    """
    from helpers import FakeCaptions, FakeNames, Queue
    from selfaudit.perceive.items import Backends

    return Backends(vision=Queue([], call_log), captions=FakeCaptions([], call_log),
                    names=FakeNames([], call_log), analyzer=None)
