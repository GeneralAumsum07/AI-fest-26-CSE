"""Feature C: the privacy receipt - how much of the export was opened, in counts and fixed labels."""

import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from selfaudit.app import create_app
from selfaudit.ingest.access import EVERYTHING_ELSE, LABELS, summarise

# A message folder named after a person, as Instagram names them. It must never be served.
PERSON_FOLDER = "your_instagram_activity/messages/inbox/priyasharma_123456/message_1.json"


def test_counts_add_up_and_labels_come_from_the_table():
    names = {"personal_information/personal_information/personal_information.json",
             "your_instagram_activity/media/posts_1.json", "media/posts/202601/a.jpg",
             PERSON_FOLDER, "your_instagram_activity/messages/inbox/x_1/message_1.json",
             "ads_information/ads_and_topics/ads_viewed.json",
             "logged_information/recent_searches/word_or_phrase_searches.json"}
    opened = {"personal_information/personal_information/personal_information.json",
              "your_instagram_activity/media/posts_1.json", "media/posts/202601/a.jpg"}
    a = summarise(names, opened)
    assert a.total == 7 and a.opened == 3
    assert a.total == a.opened + sum(g.count for g in a.never_opened)
    groups = {g.label: g.count for g in a.never_opened}
    assert groups == {"Messages": 2, "Ads and businesses": 1, "Search and watch history": 1}
    assert all(g.label in set(LABELS.values()) | {EVERYTHING_ELSE} for g in a.never_opened)


def test_an_unknown_folder_is_everything_else_and_comes_last():
    a = summarise({"some_new_folder/x.json", "your_instagram_activity/messages/a/b.json"}, set())
    assert [g.label for g in a.never_opened] == ["Messages", EVERYTHING_ELSE]


def test_opened_never_counts_a_file_outside_the_export():
    # opened is a set the reader fills; a name not in the listing must not inflate the count.
    assert summarise({"a.json"}, {"a.json", "ghost.json"}).opened == 1


def test_youtube_folders_get_plain_labels():
    root = "Takeout/YouTube and YouTube Music/"
    a = summarise({root + "history/watch-history.json", root + "comments/comments.csv",
                   root + "live chats/live chats.csv", root + "subscriptions/subscriptions.csv",
                   root + "video metadata/videos.csv"}, {root + "video metadata/videos.csv"})
    assert {g.label for g in a.never_opened} == {"Search and watch history", "Comments", "Live chat",
                                                 "Subscriptions"}


@pytest.fixture
def client(scripted_backends):
    with TestClient(create_app(lambda: scripted_backends)) as c:
        yield c


def test_the_report_carries_the_receipt_and_no_folder_name(client, tmp_path, jpg, mp4_file):
    from pipeline_fakes import HIGH_EXPOSURE
    from selfaudit.devtools.persona import add_decoys, build_persona
    path = build_persona(HIGH_EXPOSURE(jpg, mp4_file), tmp_path / "zip", as_zip=True)
    with zipfile.ZipFile(path, "a") as z:
        z.writestr(PERSON_FOLDER, "{}")
    id_ = client.post("/api/audits", files={"export": ("e.zip", path.read_bytes(), "application/zip")}).json()["id"]
    for _ in range(400):
        if client.get(f"/api/audits/{id_}/progress").json()["finished"]:
            break
        time.sleep(0.05)
    res = client.get(f"/api/audits/{id_}/report")
    access = res.json()["report"]["access"]
    assert access["opened"] < access["total"]
    assert {"label": "Messages", "count": 1} in access["never_opened"]
    assert "priyasharma" not in res.text and "inbox" not in res.text
    assert add_decoys  # the demo personas use the same decoy writer


def test_decoys_are_synthetic_and_refused_by_the_reader(tmp_path):
    from selfaudit.devtools.persona import add_decoys
    from selfaudit.ingest.export import open_export
    add_decoys(tmp_path)
    (tmp_path / "personal_information/personal_information").mkdir(parents=True)
    (tmp_path / "personal_information/personal_information/personal_information.json").write_text("{}")
    src = open_export(tmp_path)
    with pytest.raises(PermissionError):
        src.read_index(next(n for n in src.names if "/messages/" in n))
    groups = {g.label for g in summarise(src.names, src.opened).never_opened}
    assert {"Messages", "Ads and businesses", "Search and watch history"} <= groups
