"""uv run python -m selfaudit [--export PATH] [--enrol PATH]

--export and --enrol start a run immediately, so a live demo does not depend
on a file picker. There is deliberately no --host option (see app.HOST).
"""

from __future__ import annotations

import argparse
import shutil
import tempfile
import webbrowser
from pathlib import Path

import uvicorn

from selfaudit.app import HOST, PORT, _TEMP_DIRS, create_app


def real_backends():
    from selfaudit.devtools.devrun import real_backends as items_backends
    from selfaudit.perceive.voice import DefaultGate, EcapaEmbedder, SileroVad
    from selfaudit.pipeline import AllBackends

    b = items_backends()
    return AllBackends(vision=b.vision, captions=b.captions, names=b.names, analyzer=b.analyzer,
                       vad=SileroVad(), embedder=EcapaEmbedder(), gate=DefaultGate())


def main() -> None:
    p = argparse.ArgumentParser(prog="selfaudit")
    p.add_argument("--export", type=Path, help="an Instagram export (folder or ZIP) to audit at start")
    p.add_argument("--enrol", type=Path, help="a short recording of your voice")
    args = p.parse_args()

    from selfaudit.wording.cloud import make_call_llm
    app = create_app(real_backends, call_llm=make_call_llm())

    url = f"http://{HOST}:{PORT}/"
    if args.export:
        from selfaudit.perceive.video import extract_audio
        enrol = extract_audio(args.enrol.read_bytes()) if args.enrol else None
        folder = Path(tempfile.mkdtemp(prefix="selfaudit-"))
        _TEMP_DIRS.add(folder)
        # Read in place: a folder export is not copied, so nothing extra is written.
        id_ = app.state.start(args.export, folder, enrol if enrol is not None and len(enrol) else None)
        url += f"#audit={id_}"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir()
    print(f"Open {url}")
    webbrowser.open(url)
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
