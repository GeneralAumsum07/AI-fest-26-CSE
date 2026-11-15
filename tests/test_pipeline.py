"""Task 12: the whole pipeline on built exports, with every model faked except Presidio.

Fakes and persona specs live in pipeline_fakes.py; the scripted_backends,
high_state and empty_state fixtures in conftest.py.
"""

from datetime import datetime, timezone

from helpers import SPEC3
from pipeline_fakes import (AlwaysRaises, HIGH_EXPOSURE, ONE_VIDEO_SHOWING_AN_ID, STORY_ONLY_VOICE_AND_ID,
                            speaker)

from selfaudit.devtools.persona import PersonaPost, PersonaSpec, build_persona
from selfaudit.pipeline import mark_missed, mark_wrong, run_audit


def test_end_to_end_on_a_fake_export(tmp_path, jpg, mp4_file, scripted_backends):
    state = run_audit(build_persona(HIGH_EXPOSURE(jpg, mp4_file), tmp_path), speaker(+1, 8), scripted_backends)
    levels = {r.recipe_id: r.level for r in state.report().recipes}
    assert levels == {"R1": "high", "R3": "high", "R2": "medium"}
    assert state.report().fixes and state.report().posts_read == len(state.profile.posts)


def test_a_dead_vision_model_still_gives_a_report(tmp_path, jpg, scripted_backends):
    scripted_backends.vision = AlwaysRaises()
    report = run_audit(build_persona(SPEC3(jpg), tmp_path), None, scripted_backends).report()
    assert len(report.couldnt_check) == 4 and report.recipes is not None


def test_stories_are_past_exposure_and_their_speech_is_not_counted(tmp_path, jpg, mp4_file, scripted_backends):
    report = run_audit(build_persona(STORY_ONLY_VOICE_AND_ID(jpg, mp4_file), tmp_path), speaker(+1, 8),
                       scripted_backends).report()
    assert report.recipes == [] and report.past_exposure and report.voice.band == "none"


def test_video_frames_feed_the_same_readers(tmp_path, mp4_file, scripted_backends):
    state = run_audit(build_persona(ONE_VIDEO_SHOWING_AN_ID(mp4_file), tmp_path), None, scripted_backends)
    assert any(f.category == "ID_DOCUMENT" for f in state.findings)


def test_this_is_wrong_removes_the_finding_and_recomputes(high_state):
    id_finding = next(f for f in high_state.findings if f.category == "ID_DOCUMENT")
    assert "R3" not in {r.recipe_id for r in mark_wrong(high_state, id_finding.finding_id).recipes}


def test_you_missed_something_adds_a_confirmed_finding(empty_state):
    report = mark_missed(empty_state, empty_state.profile.posts[0].post_id, "ID_DOCUMENT")
    assert any(f.supports == ["user"] and f.confidence == "confirmed" for f in report.findings)


def test_an_empty_profile_gives_an_empty_report(tmp_path, scripted_backends):
    report = run_audit(build_persona(PersonaSpec("A", "a", "", False, []), tmp_path), None,
                       scripted_backends).report()
    assert (report.posts_read, report.recipes, report.fixes) == (0, [], [])


def test_nothing_personal_is_logged(tmp_path, jpg, mp4_file, scripted_backends, caplog):
    caplog.set_level("DEBUG")
    state = run_audit(build_persona(HIGH_EXPOSURE(jpg, mp4_file), tmp_path), None, scripted_backends)
    assert not any(secret in caplog.text for secret in state.secrets() if len(secret) >= 4)


def test_a_bad_audio_track_keeps_the_video_frames(tmp_path, mp4_file, scripted_backends, monkeypatch):
    # Spec: a stage failing must not lose the others' results. The frames that
    # show the ID card were decoded; only the audio is lost.
    from selfaudit import pipeline
    from selfaudit.perceive.video import MediaError

    def broken_audio(data):
        raise MediaError("bad audio")

    monkeypatch.setattr(pipeline, "extract_audio", broken_audio)
    state = run_audit(build_persona(ONE_VIDEO_SHOWING_AN_ID(mp4_file), tmp_path), None, scripted_backends)
    assert any(f.category == "ID_DOCUMENT" for f in state.findings)
    assert [s.reason for s in state.couldnt_check] == ["unreadable_audio"]


def test_a_video_with_no_frames_is_listed(tmp_path, mp4_file, scripted_backends, monkeypatch):
    # keyframes can return [] without raising; the video must not vanish silently.
    from selfaudit import pipeline
    monkeypatch.setattr(pipeline, "keyframes", lambda data, **k: [])
    state = run_audit(build_persona(ONE_VIDEO_SHOWING_AN_ID(mp4_file), tmp_path), None, scripted_backends)
    assert "unreadable_video" in [s.reason for s in state.couldnt_check]


def test_a_broken_video_is_one_couldnt_check_line(tmp_path, jpg, scripted_backends):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video at all")
    spec = PersonaSpec(name="Asha Rao", username="asha.rao", bio="", private=False, posts=[
        PersonaPost("hi", [bad], datetime(2026, 11, 1, tzinfo=timezone.utc)),
        PersonaPost("lunch", [jpg], datetime(2026, 11, 2, tzinfo=timezone.utc))])
    report = run_audit(build_persona(spec, tmp_path / "out"), None, scripted_backends).report()
    assert [s.reason for s in report.couldnt_check] == ["unreadable_video"]
