"""Audio and keyframes from a video, with PyAV only.

Why PyAV: it ships its own FFmpeg inside the wheel, so nobody running the app
has to install system ffmpeg (this machine has none, and judges' laptops may
not either). Every PyAV error is wrapped in MediaError so the caller can turn a
broken video into one "couldn't check" line.
"""

from __future__ import annotations

import io

import av
import numpy as np

from selfaudit import config


class MediaError(Exception):
    """The bytes are not a video PyAV can read. The message is a type name, never content."""


def _open(video: bytes):
    if not video:
        raise MediaError("empty")
    try:
        return av.open(io.BytesIO(video))
    except Exception as e:  # av raises its own error tree, ValueError and others
        raise MediaError(type(e).__name__) from e


def extract_audio(video: bytes) -> np.ndarray:
    """The audio track as float32 mono 16 kHz in [-1, 1]; empty when there is no audio.

    16 kHz mono is what both Silero VAD and the ECAPA speaker model expect, so
    resampling happens once, here.
    """
    container = _open(video)
    try:
        with container:
            if not container.streams.audio:
                return np.zeros(0, dtype=np.float32)
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            chunks: list[np.ndarray] = []
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray().reshape(-1))
            for out in resampler.resample(None):  # flush what the resampler buffered
                chunks.append(out.to_ndarray().reshape(-1))
    except MediaError:
        raise
    except Exception as e:
        raise MediaError(type(e).__name__) from e
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    # s16 / 32768 lands in [-1, 1); float32 halves memory against float64.
    return (np.concatenate(chunks).astype(np.float32) / 32768.0)


def _sample_times(duration: float, every_s: float, max_frames: int) -> list[float]:
    """Every `every_s` seconds from 0; if that would exceed `max_frames`, spread
    `max_frames` samples evenly over the whole video instead of only its start
    (a reel's ID card can appear in the last second as easily as the first)."""
    if duration <= 0:
        return [0.0]
    times = list(np.arange(0.0, duration, every_s))
    if len(times) > max_frames:
        times = [duration * i / max_frames for i in range(max_frames)]
    return [float(t) for t in times]


def keyframes(video: bytes, *, every_s: float = config.KEYFRAME_EVERY_S,
              max_frames: int = config.KEYFRAME_MAX) -> list[bytes]:
    """JPEG bytes of sampled frames, at most `max_frames`."""
    container = _open(video)
    out: list[bytes] = []
    try:
        with container:
            if not container.streams.video:
                return []
            stream = container.streams.video[0]
            if container.duration is not None:
                duration = container.duration / av.time_base
            elif stream.duration is not None:
                duration = float(stream.duration * stream.time_base)
            else:
                duration = 0.0
            for t in _sample_times(duration, every_s, max_frames):
                # Seek lands on the keyframe at or before t; decode forward to t.
                container.seek(int(t / stream.time_base), stream=stream, backward=True)
                for frame in container.decode(stream):
                    if frame.time is None or frame.time >= t - 1e-3:
                        buf = io.BytesIO()
                        frame.to_image().save(buf, "JPEG", quality=90)
                        out.append(buf.getvalue())
                        break
    except MediaError:
        raise
    except Exception as e:
        raise MediaError(type(e).__name__) from e
    return out
