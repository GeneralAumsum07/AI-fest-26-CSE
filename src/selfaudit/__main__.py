"""uv run python -m selfaudit [--export PATH] [--enrol PATH]

--export and --enrol start a run immediately, so a live demo does not depend
on a file picker. There is deliberately no --host option (see app.HOST).
"""

from __future__ import annotations

import argparse
import socket
import tempfile
import threading
import time
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
    # Repeatable: the demo pre-computes several personas on ONE server. Separate
    # processes would all try to bind the same port.
    p.add_argument("--export", type=Path, action="append", default=[],
                   help="an Instagram export (folder or ZIP) to audit at start; repeat for several")
    p.add_argument("--enrol", type=Path, help="a short recording of your voice, used for every --export")
    args = p.parse_args()

    from selfaudit.wording.cloud import make_call_llm
    app = create_app(real_backends, call_llm=make_call_llm())

    base = f"http://{HOST}:{PORT}/"
    enrol = None
    if args.enrol:
        from selfaudit.perceive.video import extract_audio
        enrol = extract_audio(args.enrol.read_bytes())
        enrol = enrol if len(enrol) else None
    urls = []
    for export in args.export:
        # The export is read in place, never copied; the folder only gives the
        # run something for DELETE to remove, like an uploaded run has.
        folder = Path(tempfile.mkdtemp(prefix="selfaudit-"))
        _TEMP_DIRS.add(folder)
        # Runs queue on the app's GPU lock, so they finish one after another.
        urls.append(base + f"#audit={app.state.start(export, folder, enrol)}")
    for url in urls or [base]:
        print(f"Open {url}")

    def _open_tabs() -> None:
        # Wait until the port really accepts connections. Opening the browser
        # before uvicorn binds gave a "connection refused" tab when it won the race.
        for _ in range(100):
            try:
                socket.create_connection((HOST, PORT), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        for url in urls or [base]:
            webbrowser.open_new_tab(url)

    threading.Thread(target=_open_tabs, daemon=True).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
