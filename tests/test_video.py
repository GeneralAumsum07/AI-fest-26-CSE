"""Task 8: audio extraction and keyframes."""

import numpy as np
import pytest

from selfaudit.perceive.video import MediaError, extract_audio, keyframes


def test_audio_comes_out_as_16k_mono(mp4):
    wav = extract_audio(mp4(4.0))
    assert wav.dtype == np.float32 and wav.ndim == 1 and abs(len(wav) - 64_000) < 3_200 and np.abs(wav).max() <= 1.0


def test_a_silent_video_gives_empty_audio(mp4):
    assert len(extract_audio(mp4(2.0, audio=False))) == 0


def test_frames_are_sampled_and_capped(mp4):
    assert len(keyframes(mp4(4.0))) == 2            # at 0 s and 3 s
    assert len(keyframes(mp4(60.0))) == 8           # capped, however long the video is
    assert keyframes(mp4(4.0))[0][:2] == b"\xff\xd8"


@pytest.mark.parametrize("bad", [b"", b"not a video at all"])
def test_corrupt_video_raises_media_error(bad):
    with pytest.raises(MediaError):
        extract_audio(bad)
    with pytest.raises(MediaError):
        keyframes(bad)
