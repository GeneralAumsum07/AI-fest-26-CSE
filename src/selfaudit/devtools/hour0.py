"""Hour-0 environment checks (plan Task 0).

Run once at the start of the clock so a broken model or decoder costs minutes,
not the whole build:

    uv run python -m selfaudit.devtools.hour0 --image photo.jpg --video clip.mp4

Check 2: the vision model answers a JSON-schema request about one photo.
Check 3: PyAV can decode a video's audio track (there is no system ffmpeg).
Check 1 (PyTorch sees the GPU) is a one-liner in the plan and lives outside.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from selfaudit import config

# Deliberately tiny: two fields are enough to prove the model honours a schema
# (structured output is what the real reader relies on) without testing quality.
_SCHEMA = {
    "type": "object",
    "properties": {
        "has_person": {"type": "boolean"},
        "what": {"type": "string"},
    },
    "required": ["has_person", "what"],
}


def check_vision(image: Path) -> bool:
    """Check 2: ask the vision model about one photo and parse its JSON answer."""
    import ollama  # imported here so check 3 still runs if ollama is missing

    try:
        client = ollama.Client(host=config.OLLAMA_HOST)
        reply = client.chat(
            model=config.VISION_MODEL,
            messages=[{
                "role": "user",
                "content": "Describe this photo in one short sentence. Is there a person?",
                "images": [image.read_bytes()],
            }],
            format=_SCHEMA,
            # Temperature 0: the same photo should give the same reading, which
            # is what makes the development-split metrics reproducible.
            options={"temperature": 0},
            # Same think setting as the real reader, so this check times and
            # parses the model the way the audit will actually call it.
            **({} if config.VISION_THINK is None else {"think": config.VISION_THINK}),
        )
        parsed = json.loads(reply.message.content)
        ok = isinstance(parsed.get("has_person"), bool) and isinstance(parsed.get("what"), str)
        print(f"check 2 {'PASS' if ok else 'FAIL'}: {config.VISION_MODEL} -> {parsed}")
    except Exception as exc:  # any failure here means "try the next fallback"
        print(f"check 2 FAIL: {config.VISION_MODEL}: {type(exc).__name__}: {exc}")
        return False
    # Memory is read while the model is still loaded, so this is the real peak
    # the other stages must fit beside (they run after it unloads).
    try:
        used = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        print(f"        GPU memory in use: {used}")
    except (OSError, subprocess.CalledProcessError):
        print("        GPU memory: nvidia-smi unavailable")
    return ok


def check_audio(video: Path) -> bool:
    """Check 3: PyAV opens the video and decodes its audio stream."""
    import av

    try:
        with av.open(str(video)) as container:
            if not container.streams.audio:
                print("check 3 FAIL: video has no audio track")
                return False
            stream = container.streams.audio[0]
            samples = 0
            rate = stream.rate or stream.codec_context.sample_rate
            for frame in container.decode(stream):
                samples += frame.samples
        print(f"check 3 PASS: decoded {samples / rate:.1f} s of audio at {rate} Hz")
        return True
    except Exception as exc:
        print(f"check 3 FAIL: {type(exc).__name__}: {exc}")
        return False


def main(image: Path, video: Path) -> int:
    """Return a process exit code: 0 only when both checks pass."""
    results = [check_vision(image), check_audio(video)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(main(args.image, args.video))
