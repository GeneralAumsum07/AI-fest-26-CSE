"""LinkedIn and Reddit readers: text-only exports of flat CSV files.

These pin what must hold whatever the real headers turn out to be: which
files may be opened (the privacy promise), what becomes a "post", that
fields a stranger cannot see (address, birth date, IP) never reach the
readers, and that photos referenced by a post but missing from the export
are listed rather than silently dropped.
"""

from datetime import datetime, timezone

import pytest

from pipeline_fakes import AADHAAR
from selfaudit.devtools.text_persona import build_linkedin_export, build_reddit_export
from selfaudit.ingest.access import summarise
from selfaudit.ingest.export import NotAnExport, load_profile, open_export
from selfaudit.pipeline import run_audit
from selfaudit.wording.payload import FixPayload, WordingPayload, build_payload, post_ordinals
from selfaudit.wording.templates import render_local

UTC = timezone.utc

LI_PROFILE = {"First Name": "Asha", "Last Name": "Rao", "Address": "12 Secret Lane, Pune",
              "Birth Date": "Jan 5, 2004", "Zip Code": "411001",
              "Headline": "CSE student at Mahindra University",
              "Summary": "Reach me on 98765 43210 for internships."}
LI_POSITIONS = [{"Company Name": "Infosys", "Title": "Intern", "Description": "Built dashboards",
                 "Started On": "May 2026", "Finished On": ""}]
LI_EDUCATION = [{"School Name": "Mahindra University", "Degree Name": "B.Tech"}]
LI_SHARES = [
    {"Date": "2026-10-01 09:00:00", "ShareCommentary": "Proud to share my first hackathon win with Amma watching",
     "Visibility": "MEMBER_NETWORK"},
    {"Date": "2026-11-10 18:30:00", "ShareCommentary": "Off to Goa for a week, back on the 20th",
     "MediaUrl": "https://media.licdn.com/dms/image/abc", "Visibility": "PUBLIC"},
]


def _linkedin(tmp_path, **kw):
    return build_linkedin_export(tmp_path / "li", profile=LI_PROFILE, positions=LI_POSITIONS,
                                 education=LI_EDUCATION, shares=LI_SHARES, **kw)


RD_POSTS = [
    {"id": "p1", "permalink": "/r/hyderabad/comments/p1/", "date": "2026-11-12 10:00:00 UTC", "ip": "203.0.113.7",
     "subreddit": "hyderabad", "title": "Moving to Gachibowli next month", "body": "Any PG near the campus?",
     "url": "https://www.reddit.com/r/hyderabad/comments/p1/"},
    {"id": "p2", "permalink": "/r/pics/comments/p2/", "date": "2026-10-02 08:00:00 UTC", "ip": "203.0.113.7",
     "subreddit": "pics", "title": "My new college ID lol", "body": "", "url": "https://i.redd.it/abcd1234.jpg"},
    {"id": "p3", "permalink": "/r/x/comments/p3/", "date": "2026-09-01 08:00:00 UTC", "ip": "203.0.113.7",
     "subreddit": "x", "title": "[deleted]", "body": "[removed]", "url": ""},
]
RD_COMMENTS = [
    {"id": "c1", "permalink": "/r/india/comments/x/c1/", "date": "2026-11-14 21:00:00 UTC", "ip": "203.0.113.7",
     "subreddit": "india", "body": "My Amma keeps getting these scam calls", "link": "", "parent": ""},
    {"id": "c2", "permalink": "/r/india/comments/x/c2/", "date": "2026-11-01 21:00:00 UTC", "ip": "203.0.113.7",
     "subreddit": "india", "body": "[deleted]", "link": "", "parent": ""},
]


def _reddit(tmp_path, **kw):
    return build_reddit_export(tmp_path / "rd", posts=RD_POSTS, comments=RD_COMMENTS, **kw)


# --------------------------------------------------------------------- LinkedIn

def test_linkedin_profile_and_shares_become_posts(tmp_path):
    profile = load_profile(_linkedin(tmp_path))
    assert profile.platform == "linkedin"
    assert profile.name == "Asha Rao" and profile.bio == "CSE student at Mahindra University"
    assert not profile.is_private
    captions = [p.caption for p in profile.posts]
    # Newest first: the Goa share, the profile itself (dated as current), then the older share.
    assert captions[0].startswith("Off to Goa")
    prof = next(p for p in profile.posts if p.post_id == "profile-0001")
    for public in ("CSE student at Mahindra University", "98765 43210", "Intern at Infosys",
                   "Built dashboards", "Mahindra University"):
        assert public in prof.caption
    assert all(not p.media for p in profile.posts)   # LinkedIn exports carry no photos


def test_linkedin_fields_a_stranger_cannot_see_are_never_read(tmp_path):
    text = " ".join(p.caption for p in load_profile(_linkedin(tmp_path)).posts)
    for private in ("Secret Lane", "Jan 5, 2004", "411001", "PRIVATE-"):
        assert private not in text


def test_linkedin_photo_in_a_share_is_listed_as_not_in_the_export(tmp_path):
    profile = load_profile(_linkedin(tmp_path))
    goa = profile.posts[0]
    assert [(s.ref, s.reason) for s in profile.couldnt_check] == [(f"{goa.post_id}/media-0", "media_not_in_export")]


def test_linkedin_allowlist_refuses_messages_contacts_and_account_email(tmp_path):
    root = _linkedin(tmp_path)
    with open_export(root) as src:
        load_profile(root, source=src)
        for name in ("messages.csv", "Connections.csv", "Email Addresses.csv", "PhoneNumbers.csv"):
            with pytest.raises(PermissionError):
                src.read_index(name)
        assert src.opened == {"Profile.csv", "Positions.csv", "Education.csv", "Shares.csv"}


def test_linkedin_zip_with_a_wrapper_folder_reads_the_same(tmp_path):
    # Unzip tools often add one folder around everything; the reader looks through it.
    profile = load_profile(build_linkedin_export(tmp_path / "li.zip", profile=LI_PROFILE, shares=LI_SHARES,
                                                 as_zip=True, wrapper="Basic_LinkedInDataExport_11-16-2026"))
    assert profile.platform == "linkedin" and len(profile.posts) == 3


# ----------------------------------------------------------------------- Reddit

def test_reddit_posts_and_comments_become_posts(tmp_path):
    profile = load_profile(_reddit(tmp_path))
    assert profile.platform == "reddit"
    # Reddit is pseudonymous: the export holds no display name to report.
    assert profile.name == "" and not profile.is_private
    captions = [p.caption for p in profile.posts]
    # Newest first; "[deleted]"/"[removed]" items carry nothing and are dropped.
    assert captions == [
        "My Amma keeps getting these scam calls\nPosted in r/india",
        "Moving to Gachibowli next month\nAny PG near the campus?\nPosted in r/hyderabad",
        "My new college ID lol\nPosted in r/pics",
    ]
    assert profile.reference_date == datetime(2026, 11, 14, 21, 0, tzinfo=UTC)


def test_reddit_ip_addresses_never_reach_the_readers(tmp_path):
    text = " ".join(p.caption for p in load_profile(_reddit(tmp_path)).posts)
    assert "203.0.113.7" not in text and "PRIVATE-" not in text


def test_reddit_image_post_is_listed_as_not_in_the_export(tmp_path):
    profile = load_profile(_reddit(tmp_path))
    pic = next(p for p in profile.posts if p.caption.startswith("My new college ID"))
    assert [(s.ref, s.reason) for s in profile.couldnt_check] == [(f"{pic.post_id}/media-0", "media_not_in_export")]


def test_reddit_allowlist_refuses_messages_votes_and_ip_logs(tmp_path):
    root = _reddit(tmp_path)
    with open_export(root) as src:
        load_profile(root, source=src)
        for name in ("messages.csv", "chat_history.csv", "ip_logs.csv", "post_votes.csv", "saved_posts.csv"):
            with pytest.raises(PermissionError):
                src.read_index(name)
        assert src.opened == {"posts.csv", "comments.csv"}


def test_the_receipt_names_what_was_never_opened(tmp_path):
    root = _reddit(tmp_path)
    with open_export(root) as src:
        load_profile(root, source=src)
        access = summarise(src.names, src.opened)
    groups = {g.label: g.count for g in access.never_opened}
    assert access.opened == 2
    assert groups["Messages"] == 2                      # messages.csv, chat_history.csv
    assert groups["Sign-in and IP logs"] == 1
    assert groups["Votes, saves and subscriptions"] == 3


def test_an_empty_folder_is_still_not_an_export(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "notes.csv").write_text("a,b\n1,2\n")
    with pytest.raises(NotAnExport):
        load_profile(tmp_path / "x")


# ------------------------------------------------------------ through the audit

def test_a_reddit_export_runs_through_the_audit(tmp_path, scripted_backends):
    """Text-only posts still reach the caption reader and the number checker."""
    root = build_reddit_export(tmp_path / "rd", posts=[
        {"id": "p1", "date": "2026-11-12 10:00:00 UTC", "subreddit": "pune",
         "title": "Lost my Aadhaar", "body": f"Number is {AADHAAR}, please DM if found", "url": ""}],
        comments=[{"id": "c1", "date": "2026-11-13 10:00:00 UTC", "subreddit": "pune",
                   "body": "Amma says hi"}])
    report = run_audit(root, None, scripted_backends).report()
    cats = {f.category for f in report.findings}
    assert {"ID_DOCUMENT", "FAMILY_RELATION"} <= cats
    assert report.platform == "reddit"


# -------------------------------------------------------------------- wording

def _fixes(platform, profile_post=0):
    fixes = [FixPayload(rank=1, action="remove", post_ref="post 3", effects=["ends R3"]),
             FixPayload(rank=2, action="edit_caption", post_ref="post 2", effects=[]),
             FixPayload(rank=3, action="edit_caption", post_ref="post 1", effects=[])]
    return render_local(WordingPayload(recipes=[], fixes=fixes, language="en", private=False, couldnt_check=0,
                                       platform=platform, profile_post=profile_post)).fixes


def test_linkedin_fix_on_the_profile_says_profile_not_post():
    fixes = _fixes("linkedin", profile_post=2)
    assert fixes[0].startswith("1. Delete post 3")
    assert fixes[1] == "2. Take the detail out of your profile (headline, about or experience)."
    assert fixes[2] == "3. Edit post 1 to take the detail out."


def test_reddit_fix_wording_knows_titles_cannot_be_edited():
    fixes = _fixes("reddit")
    assert fixes[0].startswith("1. Delete post 3")
    assert fixes[1] == "2. Edit post 2, or delete it if the detail is in the title (titles cannot be edited)."


def test_the_payload_marks_the_linkedin_profile_by_its_number_only(tmp_path, scripted_backends):
    state = run_audit(_linkedin(tmp_path), None, scripted_backends)
    payload = build_payload(state.report(), state.profile)
    assert payload.platform == "linkedin"
    assert payload.profile_post == post_ordinals(state.profile)["profile-0001"]


def test_linkedin_posts_are_numbered_without_a_gap_for_the_profile(tmp_path):
    # Found live: the profile took "post 2", so the shares read "post 1, post 3"
    # and a person counting down their LinkedIn activity hit the wrong one.
    profile = load_profile(_linkedin(tmp_path))
    order = post_ordinals(profile)
    shares = sorted(n for pid, n in order.items() if pid != "profile-0001")
    assert shares == [1, 2]
    assert order["profile-0001"] == 3       # after every post, shown as "your profile"


def test_reddit_wording_never_claims_a_name_the_export_does_not_have(tmp_path, scripted_backends):
    # Found live: R2's reason said "your name on your profile" for a Reddit
    # account, whose export holds no name at all.
    root = build_reddit_export(tmp_path / "rd", comments=[
        {"id": "c1", "date": "2026-11-13 10:00:00 UTC", "subreddit": "pune", "body": "Amma says hi"}])
    state = run_audit(root, None, scripted_backends)
    payload = build_payload(state.report(), state.profile)
    assert all("name" not in r.has for r in payload.recipes)
