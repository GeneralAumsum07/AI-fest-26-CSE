"""Task 14: the loopback web app, driven through FastAPI's TestClient on fakes."""

import io
import time
import wave
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient

from selfaudit.app import HOST, create_app


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def wait_done(client: TestClient, id_: str, timeout_s: float = 120.0) -> dict:
    # Polls like the page does; the run itself is on a background thread.
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        p = client.get(f"/api/audits/{id_}/progress").json()
        if p["finished"]:
            return p
        time.sleep(0.05)
    raise AssertionError("audit did not finish")


@pytest.fixture
def client(scripted_backends):
    with TestClient(create_app(lambda: scripted_backends)) as c:
        yield c


@pytest.fixture
def high_zip(tmp_path, jpg, mp4_file):
    from pipeline_fakes import HIGH_EXPOSURE
    from selfaudit.devtools.persona import build_persona
    path = build_persona(HIGH_EXPOSURE(jpg, mp4_file), tmp_path / "zip", as_zip=True)
    return ("export.zip", path.read_bytes(), "application/zip")


@pytest.fixture
def enrol_wav():
    # Any decodable audio: SameVoice in the fakes ignores the content.
    t = np.arange(16000 * 3) / 16000
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    return ("me.wav", buf.getvalue(), "audio/wav")


@pytest.fixture
def finished_id(client, high_zip, enrol_wav):
    id_ = client.post("/api/audits", files={"export": high_zip, "enrol": enrol_wav}).json()["id"]
    assert wait_done(client, id_)["error"] is None
    return id_


def test_full_flow(client, high_zip, enrol_wav):
    id_ = client.post("/api/audits", files={"export": high_zip, "enrol": enrol_wav}).json()["id"]
    wait_done(client, id_)
    body = client.get(f"/api/audits/{id_}/report").json()
    assert {r["recipe_id"]: r["level"] for r in body["report"]["recipes"]}["R3"] == "high"
    assert body["text"]["recipes"]["R3"]["title"] == "Misuse of your ID document" and body["sent_to_cloud"] is False
    assert all("value" not in f for f in body["report"]["findings"])      # extracted numbers and names are never served


def test_report_is_409_until_finished(scripted_backends, high_zip):
    # A run that has not finished must not serve a half-built report. The
    # backends are built on the worker thread, so holding make_backends holds
    # the whole run without touching any fake's internals.
    import threading
    gate = threading.Event()
    with TestClient(create_app(lambda: (gate.wait(10), scripted_backends)[1])) as c:
        id_ = c.post("/api/audits", files={"export": high_zip}).json()["id"]
        assert c.get(f"/api/audits/{id_}/report").status_code == 409
        assert c.get(f"/api/audits/{id_}/progress").json()["finished"] is False
        gate.set()
        wait_done(c, id_)
        assert c.get(f"/api/audits/{id_}/report").status_code == 200


def test_feedback_changes_the_report(client, finished_id):
    report = client.get(f"/api/audits/{finished_id}/report").json()["report"]
    fid = next(f["finding_id"] for f in report["findings"] if f["category"] == "ID_DOCUMENT")
    after = client.post(f"/api/audits/{finished_id}/feedback", json={"kind": "wrong", "finding_id": fid}).json()
    assert "R3" not in {r["recipe_id"] for r in after["report"]["recipes"]}


def test_payload_endpoint_shows_exactly_what_would_be_sent(client, finished_id):
    payload = client.get(f"/api/audits/{finished_id}/payload").json()
    assert set(payload) == {"recipes", "fixes", "language", "private", "couldnt_check"}


def test_media_endpoint_serves_only_the_profile_s_own_posts(client, finished_id):
    assert client.get(f"/api/audits/{finished_id}/media/post-0001/0").headers["content-type"].startswith("image/")
    for bad in ("post-9999/0", "..%2F..%2Fsecret/0", "messages/0", "post-0001/x", "post-0001/7"):
        assert client.get(f"/api/audits/{finished_id}/media/{bad}").status_code == 404


def test_not_an_export_is_a_plain_message(client, tmp_path):
    id_ = client.post("/api/audits", files={"export": ("x.zip", make_zip({"readme.txt": b"hi"}))}).json()["id"]
    assert "Instagram" in wait_done(client, id_)["error"]


def test_delete_wipes_the_run(client, finished_id):
    assert client.delete(f"/api/audits/{finished_id}").status_code == 204
    assert client.get(f"/api/audits/{finished_id}/report").status_code == 404


def test_the_server_only_ever_binds_loopback():
    assert HOST == "127.0.0.1"
