"""Task 1: text repair and the allowlist export reader."""

from datetime import datetime, timezone

import pytest

from helpers import SPEC1, SPEC3
from selfaudit.devtools.persona import PersonaSpec, build_persona
from selfaudit.ingest.export import NotAnExport, load_profile, open_export
from selfaudit.ingest.textfix import normalise, repair


def test_repair_fixes_instagram_text_and_leaves_good_text_alone():
    good = "जन्मदिन मुबारक अम्मा 🎂"
    assert repair(good.encode("utf-8").decode("latin-1")) == good
    assert repair(good) == good
    assert repair("café") == "café"


def test_normalise_drops_case_spaces_dashes_and_colons():
    assert normalise("ABCD 1234-56:78") == "abcd12345678"


@pytest.mark.parametrize("layout", ["2025", "pre2025", "2021"])
def test_reads_all_three_layouts(tmp_path, jpg, layout):
    profile = load_profile(build_persona(SPEC3(jpg), tmp_path, layout=layout))
    assert (profile.name, profile.is_private) == ("Asha Rao", False)
    assert [p.caption for p in profile.posts] == ["story", "गोवा", "Happy birthday Amma ❤️"]
    assert profile.posts[1].media[1].item_id == profile.posts[1].post_id + "/media-1"
    assert profile.reference_date == datetime(2026, 11, 12, tzinfo=timezone.utc)
    assert profile.posts[0].source == "story"


def test_never_opens_anything_outside_the_allowlist(tmp_path, jpg):
    root = build_persona(SPEC1(jpg), tmp_path)
    (root / "messages/inbox").mkdir(parents=True)
    (root / "messages/inbox/chat.json").write_text("{}")
    src = open_export(root)
    profile = load_profile(root)
    assert profile.posts and not any(n.startswith("messages/") for n in src.opened)
    with pytest.raises(PermissionError):
        src.read_media("messages/inbox/chat.json")


@pytest.mark.parametrize("uri", ["../outside.jpg", "/etc/passwd", "C:/Windows/win.ini", "messages/inbox/p.jpg",
                                 "your_instagram_activity/messages/inbox/a/photos/1.jpg"])
def test_index_entries_pointing_outside_are_listed_not_opened(tmp_path, jpg, uri):
    spec = SPEC1(jpg)
    spec.posts[0].media.append(uri)
    profile = load_profile(build_persona(spec, tmp_path))
    assert any(s.reason == "outside_export" for s in profile.couldnt_check)


def test_html_export_gets_its_own_reason(tmp_path):
    (tmp_path / "your_instagram_activity/media").mkdir(parents=True)
    (tmp_path / "your_instagram_activity/media/posts_1.html").write_text("<html>")
    with pytest.raises(NotAnExport) as e:
        load_profile(tmp_path)
    assert e.value.reason == "html_export"


def test_a_folder_that_is_not_an_export_is_named(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    with pytest.raises(NotAnExport) as e:
        load_profile(tmp_path)
    assert e.value.reason == "missing_files"


def test_zip_with_a_wrapper_folder_is_read(tmp_path, jpg):
    z = build_persona(SPEC1(jpg), tmp_path, as_zip=True, wrapper="instagram-asha-2026-11-12")
    assert len(load_profile(z).posts) == 1


def test_a_zip_made_on_a_mac_is_read(tmp_path, jpg):
    # macOS "Compress" adds __MACOSX/ and .DS_Store beside the wrapper folder.
    # Our own "export came in parts" advice tells users to re-zip, so this
    # exact ZIP must open.
    import zipfile
    z = build_persona(SPEC1(jpg), tmp_path, as_zip=True, wrapper="instagram-asha")
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr("__MACOSX/instagram-asha/._personal_information", b"x")
        zf.writestr(".DS_Store", b"x")
    assert len(load_profile(z).posts) == 1


def test_the_source_releases_the_zip_when_closed(tmp_path, jpg):
    # On Windows an open ZipFile locks the file, so "Forget" could not delete
    # an export a reader still held.
    z = build_persona(SPEC1(jpg), tmp_path, as_zip=True)
    with open_export(z) as src:
        load_profile(z, source=src)
    z.unlink()
    assert not z.exists()


def test_export_in_parts_is_named_not_half_read(tmp_path, jpg):
    root = build_persona(SPEC3(jpg), tmp_path)
    for f in list(root.rglob("*.jpg"))[1:]:
        f.unlink()  # 3 of 4 media files live in "another part"
    with pytest.raises(NotAnExport) as e:
        load_profile(root)
    assert e.value.reason == "multi_part"


def test_one_missing_file_is_listed_not_fatal(tmp_path, jpg):
    root = build_persona(SPEC3(jpg), tmp_path)
    next(iter(root.rglob("*.jpg"))).unlink()
    profile = load_profile(root)
    assert [s.reason for s in profile.couldnt_check] == ["missing_file"]


def test_cap_keeps_the_newest_and_lists_the_rest(tmp_path, jpg):
    profile = load_profile(build_persona(SPEC3(jpg), tmp_path), max_items=2)
    assert sum(len(p.media) for p in profile.posts) == 2 and len(profile.not_checked) == 2


def test_a_profile_with_no_posts_loads(tmp_path):
    assert load_profile(build_persona(PersonaSpec("A", "a", "", False, []), tmp_path)).posts == []


def test_media_bytes_come_back_through_the_source(tmp_path, jpg):
    root = build_persona(SPEC1(jpg), tmp_path)
    src = open_export(root)
    profile = load_profile(root, source=src)
    item = profile.posts[0].media[0]
    assert src.read_media(item.zip_path) == jpg.read_bytes()
