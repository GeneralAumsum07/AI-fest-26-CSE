"""Feature B: "Check before you post" - one photo or video, advice on that item only."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from selfaudit.app import create_app
from selfaudit.check import check_item, verdict
from selfaudit.models import Finding
from selfaudit.perceive.items import ItemInput, analyse_items


@pytest.fixture
def client(scripted_backends):
    with TestClient(create_app(lambda: scripted_backends)) as c:
        yield c


@pytest.fixture
def photo(jpg):
    return jpg.read_bytes()


def _check(client, data, caption="", name="photo.jpg", ctype="image/jpeg"):
    return client.post("/api/check", files={"file": (name, data, ctype)}, data={"caption": caption})


def _f(category, confidence="confirmed"):
    return Finding(finding_id="x", item_id="i", post_id="p", category=category, what="w",
                   confidence=confidence, supports=["vision"])


def test_a_readable_id_says_stop_and_never_shows_the_number(client, photo):
    from pipeline_fakes import AADHAAR
    res = _check(client, photo, "new card! #id")
    assert res.status_code == 200
    body = res.json()
    assert body["result"] == "stop" and body["heading"] == "Wait before you post this."
    assert any(f["category"] == "ID_DOCUMENT" for f in body["findings"])
    assert all("value" not in f for f in body["findings"])
    for part in (AADHAAR.replace(" ", ""), AADHAAR[:4], AADHAAR[-4:]):
        assert part not in res.text


def test_a_plain_photo_says_nothing_urgent_and_never_safe(client, photo):
    body = _check(client, photo, "lunch with the team").json()
    assert body["result"] == "nothing"
    assert body["heading"] == "Nothing urgent was identified in this photo."
    assert "does not mean it is safe" in body["note"]
    assert "safe to post" not in (body["heading"] + " ".join(body["advice"])).lower()


def test_a_family_name_in_the_caption_says_look(client, photo):
    body = _check(client, photo, "dinner with Amma").json()
    assert body["result"] == "look" and body["heading"] == "Have a look at this first."
    assert "Amma" not in str(body)          # the caption reader's sentence holds the name; never served


def test_the_check_finds_what_an_audit_finds(scripted_backends, photo):
    # Same code path as the audit, so the held-out numbers describe this too.
    caption = "Amma and me #id"
    audit, _ = analyse_items([ItemInput("a", "a", photo, caption)], scripted_backends)
    check = check_item(photo, "image/jpeg", caption, scripted_backends)
    key = lambda fs: sorted((f.category, f.confidence) for f in fs)   # noqa: E731
    assert key(check.findings) == key(audit)


def test_two_checks_share_nothing(client, photo):
    first = _check(client, photo, "dinner with Amma #id").json()
    second = _check(client, photo, "lunch").json()
    assert first["result"] == "stop" and second["result"] == "nothing" and second["findings"] == []


def test_a_video_is_checked_frame_by_frame_and_says_speech_was_not_measured(client, mp4):
    body = _check(client, mp4(2.0), "#id", name="clip.mp4", ctype="video/mp4").json()
    assert body["result"] == "stop"
    assert len([f for f in body["findings"] if f["category"] == "ID_DOCUMENT"]) == 1   # merged across frames
    assert body["video_note"] == "Speech in this video was not measured. The full audit does that."


@pytest.mark.parametrize("data,name,ctype", [
    (b"not an image at all", "x.jpg", "image/jpeg"),
    (b"not a video", "x.mp4", "video/mp4"),
    (b"%PDF-1.4", "x.pdf", "application/pdf"),
])
def test_bad_uploads_get_a_plain_message(client, data, name, ctype):
    res = _check(client, data, "", name=name, ctype=ctype)
    assert res.status_code == 422 and res.json()["detail"] and "Traceback" not in res.text


def test_an_oversize_upload_gets_a_plain_message(client, monkeypatch):
    from selfaudit import check
    monkeypatch.setattr(check, "MAX_BYTES", 1000)
    buf = io.BytesIO()
    Image.new("RGB", (400, 400), (1, 2, 3)).save(buf, "PNG")
    res = _check(client, buf.getvalue(), name="big.png", ctype="image/png")
    assert res.status_code == 413 and "50 MB" in res.json()["detail"]


def test_busy_says_whether_an_audit_holds_the_gpu(client):
    assert client.get("/api/busy").json() == {"busy": False}


@pytest.mark.parametrize("cats,expected", [
    ([], "nothing"),
    ([("FACE_CLEAR", "confirmed")], "nothing"),          # never tell someone not to post their face
    ([("ID_DOCUMENT", "confirmed")], "stop"),
    ([("FINANCIAL", "confirmed")], "stop"),
    ([("TRAVEL_DOC", "confirmed")], "stop"),
    ([("CONTACT", "confirmed")], "stop"),
    ([("ID_DOCUMENT", "likely")], "look"),
    ([("ID_DOCUMENT", "unsure")], "look"),
    ([("FAMILY_RELATION", "confirmed")], "look"),
    ([("AWAY_STATUS", "confirmed"), ("INSTITUTION", "confirmed")], "look"),
    ([("INSTITUTION", "confirmed"), ("CONTACT", "confirmed")], "stop"),
])
def test_verdict_rule(cats, expected):
    assert verdict([_f(c, conf) for c, conf in cats]) == expected
