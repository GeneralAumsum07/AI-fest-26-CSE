"""Allowlist reader for an Instagram JSON export (spec 7.3).

The privacy guarantee lives in `ExportSource`: it can open the profile-info
file and the posts/stories/reels indexes by name, and media files only after
an index has referenced them. It has no way to open `messages/` or anything
else, so "we never read your DMs" is a property of the code, not a promise.
"""

from __future__ import annotations

import json
import posixpath
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from selfaudit.devtools.persona import REELS_FILE, REELS_KEY
from selfaudit.ingest import youtube
from selfaudit.ingest.errors import NotAnExport  # re-exported: callers import it from here
from selfaudit.ingest.textfix import repair
from selfaudit.models import MediaItem, Post, Profile, Skipped

# Tried in order: current layout first, then older generations (spec 7.3).
PROFILE_PATHS = [
    "personal_information/personal_information/personal_information.json",
    "personal_information/personal_information.json",
    "account_information/personal_information.json",
]
INDEX_DIRS = ["your_instagram_activity/media", "content"]
_POSTS_FILE = re.compile(r"^posts_\d+\.json$")

_IMAGE = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
_VIDEO = {".mp4", ".mov"}


class ExportSource:
    """The only object that touches export bytes. Small on purpose: it goes on a slide.

    Works on an unzipped folder or the ZIP itself, with or without a single
    wrapper folder around everything (some unzip tools add one).
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.opened: set[str] = set()
        self._allowed_media: set[str] = set()
        self._zip = zipfile.ZipFile(self.path) if self.path.suffix.lower() == ".zip" else None
        # Listing names is not opening files; we need the listing to find the
        # indexes and to tell an HTML export from a JSON one.
        if self._zip:
            raw = [n for n in self._zip.namelist() if not n.endswith("/")]
        else:
            raw = [p.relative_to(self.path).as_posix() for p in self.path.rglob("*") if p.is_file()]
        # macOS "Compress" adds __MACOSX/ and .DS_Store. They are never part of
        # an export, and left in they hide the wrapper folder from _wrapper.
        raw = [n for n in raw if not _os_junk(n)]
        self._prefix = self._wrapper(raw)
        self.names = {n[len(self._prefix):] for n in raw if n.startswith(self._prefix)}
        # Which reader applies, decided once from the listing. None = Instagram.
        # The YouTube root also decides what read_index will let through.
        self.youtube_root = youtube.youtube_root(self.names)

    @staticmethod
    def _wrapper(names: list[str]) -> str:
        """Return "folder/" when every file sits under one top folder that is not
        itself part of the export layout, else ""."""
        tops = {n.split("/", 1)[0] for n in names if "/" in n}
        known = {"personal_information", "account_information", "your_instagram_activity",
                 "content", "media", "messages",
                 # A YouTube Takeout zipped one level in keeps this folder, so
                 # the YouTube allowlist can match on its full path.
                 youtube.YT_ROOT}
        if len(tops) == 1 and not tops & known and all("/" in n for n in names):
            return tops.pop() + "/"
        return ""

    def _read(self, name: str) -> bytes:
        self.opened.add(name)
        if self._zip:
            return self._zip.read(self._prefix + name)
        return (self.path / self._prefix / name).read_bytes()

    def read_index(self, name: str):
        """Open one of the allowlisted index files. Anything else is refused."""
        if self.youtube_root is not None:
            # A YouTube export gets the YouTube allowlist only: two CSV folders.
            if not youtube.index_allowed(self.youtube_root, name):
                raise PermissionError(f"not an allowlisted index: {name}")
            return youtube.parse_table(self._read(name))
        folder, base = posixpath.split(name)
        is_index = folder in INDEX_DIRS and (
            _POSTS_FILE.match(base) or base in ("stories.json", REELS_FILE))
        if name not in PROFILE_PATHS and not is_index:
            raise PermissionError(f"not an allowlisted index: {name}")
        return json.loads(self._read(name).decode("utf-8"))

    def allow_media(self, uri: str) -> None:
        """Called by the loader for every media path an index references."""
        self._allowed_media.add(uri)

    def has(self, name: str) -> bool:
        return name in self.names

    def read_media(self, zip_path: str) -> bytes:
        """Read a media file, but only one an index has referenced."""
        if zip_path not in self._allowed_media:
            raise PermissionError(f"not referenced by an index: {zip_path}")
        return self._read(zip_path)

    def close(self) -> None:
        # Windows locks an open file: until this runs, "Forget" cannot delete
        # the uploaded ZIP (which holds the user's ID photos).
        if self._zip:
            self._zip.close()

    def __enter__(self) -> "ExportSource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _os_junk(name: str) -> bool:
    parts = name.split("/")
    return parts[0] == "__MACOSX" or parts[-1].startswith(".")


def open_export(path: Path) -> ExportSource:
    return ExportSource(path)


def _outside(uri: str) -> bool:
    """True for an index entry that points outside the export or into a part we
    never read. Such entries are listed as "couldn't check" and never opened."""
    u = uri.replace("\\", "/")
    return (
        u.startswith("/")
        or re.match(r"^[A-Za-z]:", u) is not None
        or ".." in u.split("/")
        # Messages at any depth: newer exports keep DMs under
        # your_instagram_activity/messages/, and a DM photo is never ours to open.
        or "messages" in u.split("/")
    )


def _ts(entry: dict, fallback: int | None = None) -> int:
    ts = entry.get("creation_timestamp")
    if ts is None and entry.get("media"):
        ts = entry["media"][0].get("creation_timestamp")
    return int(ts if ts is not None else (fallback or 0))


def _caption(entry: dict) -> str:
    # Carousels carry the caption on the post; single photos on the media entry.
    title = entry.get("title") or ""
    if not title and entry.get("media"):
        title = entry["media"][0].get("title") or ""
    return repair(title)


def _profile_fields(data: dict) -> dict[str, str]:
    smd = data["profile_user"][0]["string_map_data"]
    return {k: repair(v.get("value", "")) for k, v in smd.items()}


def load_profile(
    path: Path,
    *,
    max_items: int | None = None,
    source: ExportSource | None = None,
) -> Profile:
    """Read the profile and every post, story and reel, newest first.

    `source` lets the caller keep the same allowlisted source for reading media
    later; by default a fresh one is opened.
    """
    src = source or open_export(path)

    if src.youtube_root is not None:
        profile, posts = youtube.load_youtube(src, src.youtube_root)
        posts, not_checked = _cap(posts, max_items)
        return profile.model_copy(update={"posts": posts, "not_checked": not_checked})

    profile_path = next((p for p in PROFILE_PATHS if src.has(p)), None)
    if profile_path is None:
        # Check for HTML before giving up so the message can say "request JSON".
        if any(n.endswith(".html") and posixpath.dirname(n) in INDEX_DIRS for n in src.names):
            raise NotAnExport("html_export")
        raise NotAnExport("missing_files")
    fields = _profile_fields(src.read_index(profile_path))

    # Collect raw entries as (source, entry) in index order, per source type.
    raw: dict[str, list[dict]] = {"post": [], "story": [], "reel": []}
    for folder in INDEX_DIRS:
        for name in sorted(n for n in src.names if posixpath.dirname(n) == folder):
            base = posixpath.basename(name)
            if _POSTS_FILE.match(base):
                raw["post"] += src.read_index(name)
            elif base == "stories.json":
                raw["story"] += src.read_index(name).get("ig_stories", [])
            elif base == REELS_FILE:
                data = src.read_index(name)
                # Key unconfirmed (spec 7.3 TBD): accept the guessed key, else
                # the first list value in the file.
                reels = data.get(REELS_KEY) if isinstance(data, dict) else data
                if reels is None and isinstance(data, dict):
                    reels = next((v for v in data.values() if isinstance(v, list)), [])
                raw["reel"] += reels or []

    posts: list[Post] = []
    couldnt: list[Skipped] = []
    referenced = missing = 0
    for kind, entries in raw.items():
        for n, entry in enumerate(entries, start=1):
            post_id = f"{kind}-{n:04d}"
            # A story entry is itself one media item.
            media_entries = [entry] if kind == "story" else entry.get("media", [])
            items: list[MediaItem] = []
            for k, m in enumerate(media_entries):
                item_id = f"{post_id}/media-{k}"
                uri = repair(m.get("uri", ""))
                if _outside(uri):
                    couldnt.append(Skipped(ref=item_id, reason="outside_export"))
                    continue
                referenced += 1
                if not src.has(uri):
                    missing += 1
                    couldnt.append(Skipped(ref=item_id, reason="missing_file"))
                    continue
                ext = posixpath.splitext(uri)[1].lower()
                if ext not in _IMAGE | _VIDEO:
                    couldnt.append(Skipped(ref=item_id, reason="unsupported_type"))
                    continue
                src.allow_media(uri)
                items.append(MediaItem(item_id=item_id, post_id=post_id,
                                       kind="image" if ext in _IMAGE else "video", zip_path=uri))
            posts.append(Post(
                post_id=post_id, source=kind, caption=_caption(entry), media=items,
                created=datetime.fromtimestamp(_ts(entry), tz=timezone.utc),
            ))

    # More than half the media gone is not "a few files missing": the export
    # arrived in parts. A half-read report would understate the risk, so stop.
    if referenced and missing * 2 > referenced:
        raise NotAnExport("multi_part")

    # Newest first; stable so carousels and same-second items keep index order.
    posts.sort(key=lambda p: p.created, reverse=True)
    reference = posts[0].created if posts else datetime.now(timezone.utc)

    posts, not_checked = _cap(posts, max_items)

    return Profile(
        name=fields.get("Name", ""), username=fields.get("Username", ""),
        bio=fields.get("Bio", ""),
        is_private=fields.get("Private Account", "").strip().lower() in ("true", "yes", "1"),
        posts=posts, reference_date=reference, couldnt_check=couldnt, not_checked=not_checked,
    )


def _cap(posts: list[Post], max_items: int | None) -> tuple[list[Post], list[Skipped]]:
    """Keep the newest `max_items` media items; list the rest as "not checked".

    Shared by both readers so the ~5 minute wait holds whatever the platform.
    """
    not_checked: list[Skipped] = []
    if max_items is None:
        return posts, not_checked
    kept: list[Post] = []
    budget = max_items
    for p in posts:
        keep, rest = p.media[:max(budget, 0)], p.media[max(budget, 0):]
        budget -= len(keep)
        not_checked += [Skipped(ref=m.item_id, reason="over_limit") for m in rest]
        if keep or not p.media:
            kept.append(p.model_copy(update={"media": keep}))
    return kept, not_checked
