"""Build a fake YouTube Google Takeout export, for tests and the demo.

UNCONFIRMED LAYOUT. Nobody on the team has looked inside a real YouTube
Takeout yet, and Google publishes no file names or CSV columns (its help page
points at an archive_browser.html that ships inside each download). What is
confirmed: the export's top folder is "YouTube and YouTube Music", and its
parts include "video metadata", "videos" and "channels". The file names and
column headers below are our guess, chosen to look like what such a CSV
probably holds. The reader (ingest/youtube.py) matches columns loosely
for exactly this reason. When a real export is available, correct
DEFAULT_VIDEO_HEADERS / DEFAULT_CHANNEL_HEADERS here and re-run the tests.
"""

from __future__ import annotations

import csv
import io
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from selfaudit.ingest.youtube import CHANNEL_DIR, META_DIR, VIDEOS_DIR, YT_ROOT

# Guessed headers (see module docstring). Order matters only for readability.
DEFAULT_VIDEO_HEADERS = ["Video ID", "Video Title (Original)", "Video Description (Original)",
                         "Privacy", "Video Create Timestamp"]
DEFAULT_CHANNEL_HEADERS = ["Channel ID", "Channel Title (Original)", "Channel Description (Original)"]


@dataclass
class YTVideo:
    title: str
    description: str
    created: datetime
    privacy: str = "Public"
    file: Path | None = None        # the uploaded video; None = metadata only
    video_id: str = ""


@dataclass
class YTSpec:
    channel_title: str
    channel_description: str
    videos: list[YTVideo] = field(default_factory=list)


def _csv(headers: list[str], rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    # Google's CSVs are assumed UTF-8 with a BOM (common for Takeout CSVs;
    # also unconfirmed); the reader accepts either.
    return ("﻿" + buf.getvalue()).encode("utf-8")


def build_youtube_export(spec: YTSpec, out_dir: Path, *, as_zip: bool = False, wrapper: str = "Takeout",
                         video_headers: list[str] | None = None, decoys: bool = True) -> Path:
    """Write the export as a folder (or ZIP) and return its path.

    `video_headers` lets a test rename or drop columns, to prove the reader
    does not depend on the exact guessed header text. `decoys` adds the parts
    the reader must never open (watch history, comments, subscriptions).
    """
    headers = video_headers or DEFAULT_VIDEO_HEADERS
    files: dict[str, bytes] = {}
    base = f"{wrapper}/{YT_ROOT}" if wrapper else YT_ROOT

    rows = []
    for n, v in enumerate(spec.videos, start=1):
        vid = v.video_id or f"vid{n:08d}"
        values = {"id": vid, "title": v.title, "description": v.description,
                  "privacy": v.privacy, "timestamp": v.created.isoformat()}
        rows.append([values[_role(h)] for h in headers])
        if v.file is not None:
            # Takeout is believed to name uploads after their title (guess).
            files[f"{base}/{VIDEOS_DIR}/{v.title}{v.file.suffix}"] = v.file.read_bytes()
    files[f"{base}/{META_DIR}/videos.csv"] = _csv(headers, rows)
    files[f"{base}/{CHANNEL_DIR}/channel.csv"] = _csv(
        DEFAULT_CHANNEL_HEADERS, [["UC0000000000", spec.channel_title, spec.channel_description]])

    if decoys:
        files[f"{base}/history/watch-history.json"] = b'[{"title": "SECRET-HISTORY"}]'
        files[f"{base}/comments/comments.csv"] = _csv(["Comment Text"], [["SECRET-COMMENT"]])
        files[f"{base}/subscriptions/subscriptions.csv"] = _csv(["Channel Title"], [["SECRET-SUB"]])

    out_dir = Path(out_dir)
    if as_zip:
        zpath = out_dir / "takeout-youtube.zip"
        with zipfile.ZipFile(zpath, "w") as zf:
            for name, data in files.items():
                zf.writestr(name, data)
        return zpath
    root = out_dir / "takeout-youtube"
    if root.exists():
        shutil.rmtree(root)
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def _role(header: str) -> str:
    """Which value a (possibly renamed) test header carries."""
    h = header.lower()
    for key in ("id", "title", "description", "privacy"):
        if key in h.split() or (key != "id" and key in h):
            return key
    return "timestamp"
