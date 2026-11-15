"""Freeze a labelled set with a SHA-256 manifest.

Why: the held-out numbers are only honest if the set was fixed before any
tuning. Committing the manifest (not the images) gives a dated, checkable
record that the set evaluated in Task 15 is the set frozen in Task 2.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

MANIFEST = "MANIFEST.sha256"


def _manifest_text(dir: Path) -> str:
    lines = []
    for f in sorted(p for p in Path(dir).rglob("*") if p.is_file() and p.name != MANIFEST):
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        lines.append(f"{digest}  {f.relative_to(dir).as_posix()}")
    return "\n".join(lines) + "\n"


def freeze(dir: Path) -> Path:
    """Write MANIFEST.sha256 (sha256sum format) and return its path."""
    path = Path(dir) / MANIFEST
    path.write_text(_manifest_text(dir), encoding="utf-8")
    return path


def verify(dir: Path) -> bool:
    """True only if no file was changed, added or removed since freeze()."""
    path = Path(dir) / MANIFEST
    return path.exists() and path.read_text(encoding="utf-8") == _manifest_text(dir)
