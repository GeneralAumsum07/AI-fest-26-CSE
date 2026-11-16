"""YouTube Takeout reader.

The export layout is a guess (see devtools/yt_persona.py), so these tests pin
the behaviour that must hold whatever the real headers turn out to be: the
allowlist, the public-only rule, loose column matching, and the Instagram path
staying untouched.
"""

from datetime import datetime, timezone

import pytest

from helpers import SPEC1
from selfaudit.devtools.persona import build_persona
from selfaudit.devtools.yt_persona import YTSpec, YTVideo, build_youtube_export
from selfaudit.ingest.export import NotAnExport, load_profile, open_export

UTC = timezone.utc


@pytest.fixture
def mp4(tmp_path):
    # Bytes are never decoded by the reader, only passed through, so a stub
    # file is enough here; the pipeline tests cover real video decoding.
    p = tmp_path / "clip.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42fake")
    return p


def _spec(mp4):
    return YTSpec("Asha Cooks", "Recipes from Pune. Call 98765 43210 for orders", [
        YTVideo("Diwali at home with Amma", "Family recipe", datetime(2026, 10, 20, tzinfo=UTC), file=mp4),
        YTVideo("Unboxing", "", datetime(2026, 11, 5, tzinfo=UTC), file=mp4),
        YTVideo("Draft cut", "phone 98765 43210", datetime(2026, 11, 6, tzinfo=UTC), privacy="Private", file=mp4),
        YTVideo("For family only", "", datetime(2026, 11, 7, tzinfo=UTC), privacy="Unlisted", file=mp4),
    ])


def test_reads_public_videos_as_posts(tmp_path, mp4):
    profile = load_profile(build_youtube_export(_spec(mp4), tmp_path))
    assert profile.platform == "youtube"
    assert (profile.name, profile.bio) == ("Asha Cooks", "Recipes from Pune. Call 98765 43210 for orders")
    # Newest first; title and description travel together as the "caption".
    assert [p.caption for p in profile.posts] == ["Unboxing", "Diwali at home with Amma\nFamily recipe"]
    assert {p.source for p in profile.posts} == {"video"}
    assert all(m.kind == "video" for p in profile.posts for m in p.media)
    assert profile.reference_date == datetime(2026, 11, 5, tzinfo=UTC)


def test_private_and_unlisted_videos_are_listed_not_read(tmp_path, mp4):
    root = build_youtube_export(_spec(mp4), tmp_path)
    with open_export(root) as src:
        profile = load_profile(root, source=src)
        assert [s.reason for s in profile.couldnt_check].count("not_public") == 2
        # A stranger cannot see a private video, so it is never opened.
        with pytest.raises(PermissionError):
            src.read_media(f"YouTube and YouTube Music/videos/Draft cut.mp4")
    assert "phone" not in " ".join(p.caption for p in profile.posts)


def test_never_opens_history_comments_or_subscriptions(tmp_path, mp4):
    root = build_youtube_export(_spec(mp4), tmp_path)
    with open_export(root) as src:
        load_profile(root, source=src)
        for item in load_profile(root, source=src).posts:
            for m in item.media:
                src.read_media(m.zip_path)
        assert all(n.split("/")[1] in ("video metadata", "channels", "videos") for n in src.opened)
        for bad in ("YouTube and YouTube Music/history/watch-history.json",
                    "YouTube and YouTube Music/comments/comments.csv",
                    "YouTube and YouTube Music/subscriptions/subscriptions.csv"):
            with pytest.raises(PermissionError):
                src.read_index(bad)


def test_columns_are_matched_loosely_and_missing_privacy_means_counted(tmp_path, mp4):
    # Different header wording, no privacy column at all: every video counts,
    # because we cannot show it is hidden.
    spec = _spec(mp4)
    root = build_youtube_export(spec, tmp_path, video_headers=["video id", "Title", "Description", "Created"])
    profile = load_profile(root)
    assert len(profile.posts) == 4
    assert not any(s.reason == "not_public" for s in profile.couldnt_check)


def test_metadata_without_the_video_file_still_reads_the_text(tmp_path, mp4):
    spec = _spec(mp4)
    spec.videos[1].file = None
    profile = load_profile(build_youtube_export(spec, tmp_path))
    unboxing = next(p for p in profile.posts if p.caption == "Unboxing")
    assert unboxing.media == []
    assert any(s.reason == "missing_file" for s in profile.couldnt_check)


def test_takeout_zip_is_detected_and_read(tmp_path, mp4):
    z = build_youtube_export(_spec(mp4), tmp_path, as_zip=True)
    assert len(load_profile(z).posts) == 2


def test_zipping_the_youtube_folder_itself_is_read(tmp_path, mp4):
    z = build_youtube_export(_spec(mp4), tmp_path, as_zip=True, wrapper="")
    assert len(load_profile(z).posts) == 2


def test_youtube_folder_with_nothing_usable_is_not_an_export(tmp_path):
    (tmp_path / "Takeout/YouTube and YouTube Music/history").mkdir(parents=True)
    (tmp_path / "Takeout/YouTube and YouTube Music/history/watch-history.json").write_text("[]")
    with pytest.raises(NotAnExport) as e:
        load_profile(tmp_path)
    assert e.value.reason == "missing_files"


def test_cap_applies_to_youtube_too(tmp_path, mp4):
    profile = load_profile(build_youtube_export(_spec(mp4), tmp_path), max_items=1)
    assert sum(len(p.media) for p in profile.posts) == 1 and len(profile.not_checked) == 1


def test_instagram_exports_still_say_instagram(tmp_path, jpg):
    assert load_profile(build_persona(SPEC1(jpg), tmp_path)).platform == "instagram"


def test_whole_audit_runs_on_a_youtube_export(tmp_path, mp4_file, scripted_backends):
    # Real encoded video this time, through the real pipeline with scripted
    # models: proves frames and titles reach the same readers as Instagram's.
    # The fakes react to "#id" (vision) and "Amma" (captions).
    from selfaudit.pipeline import run_audit
    clip = mp4_file(6.0)
    spec = YTSpec("Asha Cooks", "", [
        YTVideo("New card arrived #id", "", datetime(2026, 11, 1, tzinfo=UTC), file=clip),
        YTVideo("Cooking with Amma", "", datetime(2026, 11, 2, tzinfo=UTC), file=clip),
        YTVideo("Amma private #id", "", datetime(2026, 11, 3, tzinfo=UTC), privacy="Private", file=clip),
    ])
    state = run_audit(build_youtube_export(spec, tmp_path, as_zip=True), None, scripted_backends)
    cats = {(f.post_id, f.category) for f in state.findings}
    assert {c for _, c in cats} >= {"ID_DOCUMENT", "FAMILY_RELATION"}
    # The private video (video-0003) produced nothing: it was never read.
    assert not any(pid == "video-0003" for pid, _ in cats)
    assert state.report().posts_read == 2
