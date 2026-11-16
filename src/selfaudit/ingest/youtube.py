"""Reader for a YouTube Google Takeout export.

UNCONFIRMED LAYOUT. Confirmed from Google's Takeout screens: the export's
folder is "YouTube and YouTube Music", and its parts include "video
metadata", "videos" (the original uploads) and "channels". Not confirmed: the
file names inside those folders and the CSV column headers. So this reader:

- finds files by folder, not by exact file name;
- finds columns by loose keywords ("title", "privacy", ...), not exact headers;
- treats a video it cannot show is hidden as public (over-reporting is the
  safe failure for a self-audit; under-reporting is not).

What stays strict, because it is the privacy promise: only CSVs directly in
"video metadata/" and "channels/" can be read, and only video files the
metadata (or the uploads folder itself) points to. Watch and search history,
comments, live chat, subscriptions and playlists are never opened.

Takeout folder names may be translated for accounts set to another language;
only the English names are handled.
"""

from __future__ import annotations

import csv
import io
import posixpath
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from selfaudit.ingest.errors import NotAnExport
from selfaudit.ingest.textfix import normalise
from selfaudit.models import MediaItem, Post, Profile, Skipped

if TYPE_CHECKING:   # only for the type hint; export.py imports this module
    from selfaudit.ingest.export import ExportSource

YT_ROOT = "YouTube and YouTube Music"
META_DIR = "video metadata"
VIDEOS_DIR = "videos"
CHANNEL_DIR = "channels"

_VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
# Privacy values that mean a stranger cannot find the video. "Unlisted" is
# reachable by link, but not by browsing the channel, which is how a scammer
# doing reconnaissance finds things.
_HIDDEN = {"private", "unlisted"}


def youtube_root(names: set[str]) -> str | None:
    """The folder prefix the YouTube parts sit under, or None if this is not
    a YouTube export. "" means the user zipped the YouTube folder itself."""
    if any(n.startswith(YT_ROOT + "/") for n in names):
        return YT_ROOT + "/"
    # Instagram exports never have these as top-level folders.
    if any(n.split("/", 1)[0] in (META_DIR, CHANNEL_DIR, VIDEOS_DIR) for n in names if "/" in n):
        return ""
    return None


def index_allowed(root: str, name: str) -> bool:
    """The allowlist: a CSV sitting directly in "video metadata/" or "channels/"."""
    folder = posixpath.dirname(name)
    return name.lower().endswith(".csv") and folder in (root + META_DIR, root + CHANNEL_DIR)


def parse_table(data: bytes) -> list[dict[str, str]]:
    # utf-8-sig strips a BOM if there is one and is plain UTF-8 otherwise.
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def _col(headers: list[str], *keys: str, token: bool = False) -> str | None:
    """First header that contains one of `keys` (as a whole word if `token`)."""
    for h in headers:
        low = h.lower()
        words = re.findall(r"[a-z]+", low)
        if any((k in words) if token else (k in low) for k in keys):
            return h
    return None


def _parse_dt(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _file_key(path: str) -> str:
    # Duplicate titles are assumed to get " (1)", " (2)" suffixes (a common
    # Takeout pattern, unconfirmed for YouTube); strip them before matching.
    stem = posixpath.splitext(posixpath.basename(path))[0]
    return normalise(re.sub(r"\s*\(\d+\)$", "", stem))


def load_youtube(src: "ExportSource", root: str) -> tuple[Profile, list[Post]]:
    """Read channel info and every video. Returns the profile (posts empty)
    and the posts, newest first; the caller applies the item cap."""
    names = src.names
    tables = sorted(n for n in names if index_allowed(root, n))
    files = sorted(n for n in names if posixpath.dirname(n) == root + VIDEOS_DIR
                   and posixpath.splitext(n)[1].lower() in _VIDEO_EXT)

    # Channel name and description play the part of Instagram's name and bio.
    name = bio = ""
    for t in (t for t in tables if posixpath.dirname(t) == root + CHANNEL_DIR):
        rows = src.read_index(t)
        if rows:
            hs = list(rows[0])
            tc, dc = _col(hs, "title", "name"), _col(hs, "description")
            name = rows[0].get(tc, "") if tc else ""
            bio = rows[0].get(dc, "") if dc else ""
            break

    rows: list[dict[str, str]] = []
    for t in (t for t in tables if posixpath.dirname(t) == root + META_DIR):
        rows += src.read_index(t)
    if not rows and not files:
        raise NotAnExport("missing_files")

    hs = list(rows[0]) if rows else []
    id_c = _col(hs, "id", token=True)
    title_c = _col(hs, "title")
    desc_c = _col(hs, "description")
    priv_c = _col(hs, "privacy", "visibility")
    time_c = _col(hs, "create", "publish", "timestamp", "date")

    by_key: dict[str, list[str]] = {}
    for f in files:
        by_key.setdefault(_file_key(f), []).append(f)
    used: set[str] = set()

    def match(row: dict[str, str]) -> str | None:
        vid = (row.get(id_c) or "").strip() if id_c else ""
        if vid:
            hit = next((f for f in files if f not in used and vid in posixpath.basename(f)), None)
            if hit:
                return hit
        title = (row.get(title_c) or "") if title_c else ""
        return next((f for f in by_key.get(normalise(title), []) if f not in used), None)

    couldnt: list[Skipped] = []
    drafts: list[tuple[str, str, datetime | None, str | None]] = []   # id, caption, created, file
    for n, row in enumerate(rows, start=1):
        post_id = f"video-{n:04d}"
        f = match(row)
        if f:
            used.add(f)   # also for hidden videos, so their file is never audited below
        if priv_c and (row.get(priv_c) or "").strip().lower() in _HIDDEN:
            couldnt.append(Skipped(ref=post_id, reason="not_public"))
            continue
        title = (row.get(title_c) or "").strip() if title_c else ""
        desc = (row.get(desc_c) or "").strip() if desc_c else ""
        caption = "\n".join(x for x in (title, desc) if x)
        if f is None:
            couldnt.append(Skipped(ref=f"{post_id}/media-0", reason="missing_file"))
        drafts.append((post_id, caption, _parse_dt(row.get(time_c, "")) if time_c else None, f))

    # Uploads with no metadata row: still the user's own videos, so audit
    # them (no caption, privacy unknown, so counted as public).
    for k, f in enumerate((f for f in files if f not in used), start=len(rows) + 1):
        drafts.append((f"video-{k:04d}", "", None, f))

    known = [d[2] for d in drafts if d[2] is not None]
    reference = max(known) if known else datetime.now(timezone.utc)
    posts: list[Post] = []
    for post_id, caption, created, f in drafts:
        media = []
        if f is not None:
            src.allow_media(f)
            media = [MediaItem(item_id=f"{post_id}/media-0", post_id=post_id, kind="video", zip_path=f)]
        # An undated video is treated as current: "recent" is the cautious reading.
        posts.append(Post(post_id=post_id, source="video", caption=caption,
                          created=created or reference, media=media))
    posts.sort(key=lambda p: p.created, reverse=True)

    profile = Profile(name=name, username="", bio=bio, is_private=False, platform="youtube",
                      posts=[], reference_date=reference, couldnt_check=couldnt)
    return profile, posts
