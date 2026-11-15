"""Build a fake Instagram export in the real on-disk layout.

Why fake exports: the track rules allow only synthetic, public or consented
data, and the demo personas must look exactly like a real export to the
reader. So the builder writes the same paths, the same JSON shapes and the
same Latin-1 mis-encoding Instagram uses; the reader never knows the difference.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

Layout = Literal["2025", "pre2025", "2021"]

# Paths per layout generation (spec 7.3). The "pre2025" and "2021" pairings are
# our reading of the importer's older paths; the reader tries all of them anyway.
_PROFILE = {
    "2025": "personal_information/personal_information/personal_information.json",
    "pre2025": "personal_information/personal_information.json",
    "2021": "account_information/personal_information.json",
}
_INDEX_DIR = {"2025": "your_instagram_activity/media", "pre2025": "content", "2021": "content"}

# Unconfirmed guess (spec 7.3 TBD): reels index path and key. The reader accepts
# it if present; replace both once a real export has been checked.
REELS_FILE = "reels.json"
REELS_KEY = "ig_reels_media"


@dataclass
class PersonaPost:
    caption: str
    # A Path is copied into the export; a str is written into the index verbatim
    # and no file is copied (used to test hostile or missing entries).
    media: list[Path | str]
    created: datetime
    source: Literal["post", "story", "reel"] = "post"


@dataclass
class PersonaSpec:
    name: str
    username: str
    bio: str
    private: bool
    posts: list[PersonaPost] = field(default_factory=list)


def _mojibake(obj):
    """Encode text the way Instagram does: UTF-8 bytes shown as Latin-1 characters."""
    if isinstance(obj, str):
        return obj.encode("utf-8").decode("latin-1")
    if isinstance(obj, list):
        return [_mojibake(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _mojibake(v) for k, v in obj.items()}
    return obj


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=True reproduces Instagram's à-style escapes exactly.
    path.write_text(json.dumps(_mojibake(obj), ensure_ascii=True), encoding="ascii")


def build_persona(
    spec: PersonaSpec,
    out_dir: Path,
    *,
    layout: Layout = "2025",
    as_zip: bool = False,
    wrapper: str | None = None,
) -> Path:
    """Write the export and return its path (a folder, or a .zip when as_zip).

    The export goes into its own subfolder of out_dir so that source photos
    sitting in out_dir are never mistaken for export contents.
    """
    top = Path(out_dir) / f"instagram-{spec.username}"
    root = top / wrapper if wrapper else top
    root.mkdir(parents=True, exist_ok=True)

    _write_json(root / _PROFILE[layout], {"profile_user": [{"string_map_data": {
        "Name": {"value": spec.name, "timestamp": 0},
        "Username": {"value": spec.username, "timestamp": 0},
        "Bio": {"value": spec.bio, "timestamp": 0},
        "Private Account": {"value": "True" if spec.private else "False", "timestamp": 0},
    }}]})

    posts, stories, reels = [], [], []
    counters = {"post": 0, "story": 0, "reel": 0}
    for p in spec.posts:
        counters[p.source] += 1
        ts = int(p.created.timestamp())
        uris = []
        for k, m in enumerate(p.media):
            if isinstance(m, str):
                uris.append(m)
                continue
            uri = f"media/{p.source}s/{p.created:%Y%m}/{p.source}{counters[p.source]}_{k}{m.suffix.lower()}"
            (root / uri).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(m, root / uri)
            uris.append(uri)
        if p.source == "story":
            # One story entry per media file; the caption is the story's title.
            stories += [{"uri": u, "creation_timestamp": ts, "title": p.caption} for u in uris]
            continue
        media = [{"uri": u, "creation_timestamp": ts, "title": ""} for u in uris]
        if len(media) == 1:
            # Real single-photo posts carry the caption on the media entry.
            media[0]["title"] = p.caption
            entry = {"media": media}
        else:
            entry = {"media": media, "title": p.caption, "creation_timestamp": ts}
        (reels if p.source == "reel" else posts).append(entry)

    index = root / _INDEX_DIR[layout]
    _write_json(index / "posts_1.json", posts)
    _write_json(index / "stories.json", {"ig_stories": stories})
    if reels:
        _write_json(index / REELS_FILE, {REELS_KEY: reels})

    if not as_zip:
        return top
    zpath = Path(out_dir) / f"instagram-{spec.username}.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        for f in top.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(top).as_posix())
    shutil.rmtree(top)
    return zpath
