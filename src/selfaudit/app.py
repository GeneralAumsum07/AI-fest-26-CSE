"""The loopback web app: one page, a JSON API, nothing leaves the laptop by default.

Why a local web server instead of a desktop UI: the browser gives a file
picker, a microphone and a print view for free, and binding to 127.0.0.1 only
means nothing on the network (the hostel Wi-Fi included) can reach it.
"""

from __future__ import annotations

import atexit
import io
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from selfaudit.ingest.export import NotAnExport, open_export
from selfaudit.models import Category, Report
from selfaudit.perceive.video import MediaError, extract_audio, keyframes
from selfaudit.pipeline import AllBackends, AuditState, mark_missed, mark_wrong, run_audit
from selfaudit.wording.cloud import word_report
from selfaudit.wording.payload import build_payload, post_ordinals
from selfaudit.wording.templates import voice_note

# Loopback only, and deliberately not configurable: there is no flag that
# could put a user's ID photos on the network.
HOST = "127.0.0.1"
PORT = 8765
THUMB_SIDE = 480
STATIC = Path(__file__).parent / "static"

ERRORS = {
    "html_export": "This looks like an Instagram export in HTML. Request it again and choose JSON.",
    "multi_part": "This export came in several files. Unzip them all into one folder, zip that folder, and pick it.",
    "missing_files": "I can't find Instagram's files in this ZIP.",
}
GENERIC_ERROR = "Something went wrong while reading this export. Nothing was sent anywhere."

_TEMP_DIRS: set[Path] = set()


@atexit.register
def _cleanup() -> None:
    # Uploaded exports hold ID photos; never leave them in %TEMP% after exit.
    for d in list(_TEMP_DIRS):
        shutil.rmtree(d, ignore_errors=True)


@dataclass
class Run:
    folder: Path
    export: Path
    stage: str = "starting"
    done: int = 0
    total: int = 0
    finished: bool = False
    error: str | None = None
    state: AuditState | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class Feedback(BaseModel):
    kind: Literal["wrong", "missed"]
    finding_id: str | None = None
    post_id: str | None = None
    category: Category | None = None


def create_app(make_backends: Callable[[], AllBackends], call_llm: Callable[[str], str] | None = None) -> FastAPI:
    app = FastAPI(title="Exposure self-audit", docs_url=None, redoc_url=None, openapi_url=None)
    runs: dict[str, Run] = {}
    backends: list[AllBackends] = []          # built once, on the first run: models load slowly
    gpu = threading.Lock()                     # one audit at a time: one 8 GB GPU

    def _backends() -> AllBackends:
        if not backends:
            backends.append(make_backends())
        return backends[0]

    def _get(id_: str) -> Run:
        run = runs.get(id_)
        if run is None:
            raise HTTPException(404)
        return run

    def _finished(id_: str) -> Run:
        run = _get(id_)
        if not run.finished or run.state is None:
            raise HTTPException(409, run.error or "not finished")
        return run

    def _report_body(run: Run, report: Report) -> dict:
        state = run.state
        payload = build_payload(report, state.profile)
        text, sent = word_report(payload, state.secrets(), call_llm=call_llm)
        # model_dump honours Finding.value's exclude=True: extracted numbers
        # and names are never served, even to the page on this laptop.
        # The page labels posts exactly as the fix text does ("post 8"), so the
        # same post never carries two different numbers on one screen.
        labels = {pid: f"post {n}" for pid, n in post_ordinals(state.profile).items()}
        return {"report": report.model_dump(mode="json"), "text": text.model_dump(), "sent_to_cloud": sent,
                "voice_note": voice_note(report.voice), "post_labels": labels}

    def start(export_path: Path, folder: Path, enrol) -> str:
        id_ = uuid.uuid4().hex
        run = Run(folder=folder, export=export_path)
        runs[id_] = run

        def progress(stage: str, done: int, total: int) -> None:
            run.stage, run.done, run.total = stage, done, total

        def work() -> None:
            try:
                with gpu:
                    run.state = run_audit(export_path, enrol, _backends(), on_progress=progress)
            except NotAnExport as e:
                run.error = ERRORS.get(e.reason, GENERIC_ERROR)
            except Exception:
                run.error = GENERIC_ERROR
            finally:
                run.finished = True

        threading.Thread(target=work, daemon=True).start()
        return id_

    app.state.start = start  # used by __main__ to start a run from the command line

    @app.post("/api/audits")
    async def create(export: UploadFile = File(...), enrol: UploadFile | None = File(None)) -> dict:
        folder = Path(tempfile.mkdtemp(prefix="selfaudit-"))
        _TEMP_DIRS.add(folder)
        path = folder / "export.zip"
        with path.open("wb") as out:
            while chunk := await export.read(1 << 20):   # streamed: exports can be gigabytes
                out.write(chunk)
        wav = None
        if enrol is not None:
            try:
                # Held in memory only; PyAV reads a WAV and a browser recording alike.
                wav = extract_audio(await enrol.read())
            except MediaError:
                wav = None
            if wav is not None and len(wav) == 0:
                wav = None
        return {"id": start(path, folder, wav)}

    @app.get("/api/audits/{id_}/progress")
    def progress(id_: str) -> dict:
        r = _get(id_)
        return {"stage": r.stage, "done": r.done, "total": r.total, "finished": r.finished, "error": r.error}

    @app.get("/api/audits/{id_}/report")
    def report(id_: str) -> dict:
        run = _finished(id_)
        with run.lock:
            return _report_body(run, run.state.report())

    @app.post("/api/audits/{id_}/feedback")
    def feedback(id_: str, fb: Feedback) -> dict:
        run = _finished(id_)
        with run.lock:
            if fb.kind == "wrong" and fb.finding_id:
                rep = mark_wrong(run.state, fb.finding_id)
            elif fb.kind == "missed" and fb.post_id and fb.category:
                if fb.post_id not in {p.post_id for p in run.state.profile.posts}:
                    raise HTTPException(404)
                rep = mark_missed(run.state, fb.post_id, fb.category)
            else:
                raise HTTPException(422)
            return _report_body(run, rep)

    @app.get("/api/audits/{id_}/payload")
    def payload(id_: str) -> dict:
        run = _finished(id_)
        with run.lock:
            return build_payload(run.state.report(), run.state.profile).model_dump(mode="json")

    @app.get("/api/audits/{id_}/media/{post_id}/{k}")
    def media(id_: str, post_id: str, k: str) -> Response:
        run = _finished(id_)
        # Only media the profile itself lists is servable; the export reader's
        # allowlist refuses anything else even if a lookup here were wrong.
        post = next((p for p in run.state.profile.posts if p.post_id == post_id), None)
        if post is None or not k.isdigit() or int(k) >= len(post.media):
            raise HTTPException(404)
        item = post.media[int(k)]
        try:
            # A fresh reader starts with an empty media allowlist. Grant exactly
            # the one path the loaded profile lists for this post, nothing else:
            # the profile was built from the indexes, so this is the same rule
            # the loader applied, not a wider one.
            src = open_export(run.export)
            src.allow_media(item.zip_path)
            data = src.read_media(item.zip_path)
            if item.kind == "video":
                frames = keyframes(data, max_frames=1)
                if not frames:
                    raise HTTPException(404)
                data = frames[0]
            from PIL import Image
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.thumbnail((THUMB_SIDE, THUMB_SIDE))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=80)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(404)
        return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.delete("/api/audits/{id_}", status_code=204)
    def delete(id_: str) -> Response:
        run = runs.pop(id_, None)
        if run is None:
            raise HTTPException(404)
        shutil.rmtree(run.folder, ignore_errors=True)
        _TEMP_DIRS.discard(run.folder)
        return Response(status_code=204)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
