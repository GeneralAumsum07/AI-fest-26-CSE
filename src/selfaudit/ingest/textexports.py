"""Readers for LinkedIn and Reddit data exports: flat folders of CSV files.

Neither export carries photos or videos (posts point to them by URL, and the
app never goes online to fetch them), so every "post" here is text only. The
pipeline already handles that: a post with no media becomes one caption item
for the caption reader and the number checker.

What a stranger can see is what counts as exposure, so each reader takes the
public parts only:

- LinkedIn: name, headline, summary, jobs and schools (all on the public
  profile), and the member's own posts ("Shares"). NOT read, though the same
  Profile.csv holds them: address, birth date, zip code. A stranger cannot
  see those, so reporting them would describe a risk that does not exist.
  Posts shown to connections only are still read: anyone who sends a
  connection request and is accepted sees them.
- Reddit: the member's own posts and comments, with the subreddit name
  (r/hyderabad says where someone lives). NOT read: the IP address column in
  those same files, votes, saved items, messages, chat.

The allowlist is exact file names at the export's root, so the receipt can
promise "messages.csv was never opened" and the code makes it true.

UNCONFIRMED: LinkedIn's Shares.csv headers and Reddit's comments.csv headers
(see devtools/text_persona.py). Columns are found by keyword, as the YouTube
reader does, so a renamed header still reads.
"""

from __future__ import annotations

import posixpath
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from selfaudit.ingest.errors import NotAnExport
# Shared table helpers: the YouTube reader solved CSV decoding and loose
# header matching first, and the rules there apply unchanged here.
from selfaudit.ingest.youtube import _col, parse_table  # noqa: F401  (parse_table re-exported for export.py)
from selfaudit.models import Post, Profile, Skipped

if TYPE_CHECKING:
    from selfaudit.ingest.export import ExportSource

LINKEDIN_FILES = ("Profile.csv", "Positions.csv", "Education.csv", "Shares.csv")
REDDIT_FILES = ("posts.csv", "comments.csv")

# Reddit's markers for content that is gone; such a row carries nothing to read.
_GONE = {"[deleted]", "[removed]"}
# Reddit-hosted photos and videos: the post had one, the export does not.
_REDDIT_MEDIA_HOSTS = ("i.redd.it/", "v.redd.it/", "reddit.com/gallery/", "preview.redd.it/")


def detect(names: set[str]) -> str | None:
    """'linkedin', 'reddit' or None, from the file listing alone.

    Exact, case-sensitive names: LinkedIn capitalises ("Profile.csv"), Reddit
    does not ("posts.csv"), and neither file sits at the root of an Instagram
    or YouTube export, so the checks cannot collide."""
    if any(n in names for n in LINKEDIN_FILES):
        return "linkedin"
    if any(n in names for n in REDDIT_FILES):
        return "reddit"
    return None


def index_allowed(platform: str, name: str) -> bool:
    return name in (LINKEDIN_FILES if platform == "linkedin" else REDDIT_FILES)


def _parse_dt(s: str | None) -> datetime | None:
    """ISO-ish dates as both exports write them. Reddit appends " UTC"."""
    s = (s or "").strip()
    if s.endswith(" UTC"):
        s = s[:-4]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _rows(src: "ExportSource", name: str) -> list[dict[str, str]]:
    return src.read_index(name) if src.has(name) else []


def _get(row: dict[str, str], col: str | None) -> str:
    return (row.get(col) or "").strip() if col else ""


def _finish(posts: list[Post], undated: list[Post]) -> tuple[list[Post], datetime]:
    """Date undated posts as current ("recent" is the cautious reading, as for
    YouTube) and sort newest first."""
    known = [p.created for p in posts]
    reference = max(known) if known else datetime.now(timezone.utc)
    posts = posts + [p.model_copy(update={"created": reference}) for p in undated]
    # Stable sort: equal dates keep reading order, so the profile (appended
    # first among undated) stays ahead of any undated share.
    posts.sort(key=lambda p: p.created, reverse=True)
    return posts, reference


def load_linkedin(src: "ExportSource") -> tuple[Profile, list[Post]]:
    if not src.has("Profile.csv") and not src.has("Shares.csv"):
        raise NotAnExport("missing_files")

    prof_rows = _rows(src, "Profile.csv")
    row = prof_rows[0] if prof_rows else {}
    hs = list(row)
    first, last = _get(row, _col(hs, "first")), _get(row, _col(hs, "last"))
    headline, summary = _get(row, _col(hs, "headline")), _get(row, _col(hs, "summary"))

    # The public profile as one "post": headline, summary, jobs, schools.
    # Address, birth date and zip code are in the same row and are skipped on purpose.
    lines = [x for x in (headline, summary) if x]
    pos = _rows(src, "Positions.csv")
    if pos:
        ph = list(pos[0])
        co, ti, de = _col(ph, "company"), _col(ph, "title"), _col(ph, "description")
        for p in pos:
            job = " at ".join(x for x in (_get(p, ti), _get(p, co)) if x)
            lines += [x for x in (job, _get(p, de)) if x]
    edu = _rows(src, "Education.csv")
    if edu:
        eh = list(edu[0])
        sc, dg = _col(eh, "school"), _col(eh, "degree")
        lines += [" at ".join(x for x in (_get(e, dg), _get(e, sc)) if x) for e in edu]

    dated: list[Post] = []
    undated: list[Post] = []
    if any(lines):
        undated.append(Post(post_id="profile-0001", source="post", caption="\n".join(x for x in lines if x),
                            created=datetime.now(timezone.utc), media=[]))

    couldnt: list[Skipped] = []
    shares = _rows(src, "Shares.csv")
    if shares:
        sh = list(shares[0])
        # "ShareCommentary" is the post text; match loosely in case it is renamed.
        tc = _col(sh, "commentary", "text", "content")
        dc, mc = _col(sh, "date"), _col(sh, "media")
        for n, s in enumerate(shares, start=1):
            post_id = f"post-{n:04d}"
            text = _get(s, tc)
            if _get(s, mc):
                # The share had a photo or video; the export only has its URL.
                couldnt.append(Skipped(ref=f"{post_id}/media-0", reason="media_not_in_export"))
            if not text:
                continue
            created = _parse_dt(_get(s, dc))
            p = Post(post_id=post_id, source="post", caption=text, media=[],
                     created=created or datetime.now(timezone.utc))
            (dated if created else undated).append(p)

    posts, reference = _finish(dated, undated)
    profile = Profile(name=" ".join(x for x in (first, last) if x), username="", bio=headline,
                      is_private=False, platform="linkedin", posts=[], reference_date=reference,
                      couldnt_check=couldnt)
    return profile, posts


def load_reddit(src: "ExportSource") -> tuple[Profile, list[Post]]:
    dated: list[Post] = []
    undated: list[Post] = []
    couldnt: list[Skipped] = []
    for name, kind in (("posts.csv", "post"), ("comments.csv", "comment")):
        rows = _rows(src, name)
        if not rows:
            continue
        hs = list(rows[0])
        # Only these columns are ever looked up: never "ip", "permalink" or "id".
        ti, bo, sr = _col(hs, "title"), _col(hs, "body"), _col(hs, "subreddit")
        dc, uc = _col(hs, "date"), _col(hs, "url", token=True)
        for n, r in enumerate(rows, start=1):
            post_id = f"{kind}-{n:04d}"
            parts = [x for x in (_get(r, ti), _get(r, bo)) if x and x not in _GONE]
            if any(h in _get(r, uc) for h in _REDDIT_MEDIA_HOSTS):
                couldnt.append(Skipped(ref=f"{post_id}/media-0", reason="media_not_in_export"))
            if not parts:
                continue
            sub = _get(r, sr)
            if sub:
                # Strangers see where it was posted; a city or college subreddit is itself a clue.
                parts.append(f"Posted in r/{sub}")
            created = _parse_dt(_get(r, dc))
            p = Post(post_id=post_id, source="post", caption="\n".join(parts), media=[],
                     created=created or datetime.now(timezone.utc))
            (dated if created else undated).append(p)
    posts, reference = _finish(dated, undated)
    profile = Profile(name="", username="", bio="", is_private=False, platform="reddit", posts=[],
                      reference_date=reference, couldnt_check=couldnt)
    return profile, posts
