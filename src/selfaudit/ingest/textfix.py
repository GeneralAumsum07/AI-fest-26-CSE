"""Text repair for Instagram's JSON, and the normal form used for matching.

Instagram writes UTF-8 bytes as if each byte were a Latin-1 character, so
"अम्मा" arrives as a run of accented Latin letters. Every model downstream
would read that as garbage, so repair runs on every string before anything
else sees it.
"""

from __future__ import annotations

import re

_STRIP = re.compile(r"[\s\-:]+")


def repair(s: str) -> str:
    """Undo Instagram's Latin-1 mis-encoding; return good text unchanged.

    The trick is reversible: re-encode as Latin-1 to recover the original bytes,
    then decode them as UTF-8. Good text fails one of the two steps (a character
    above U+00FF cannot be Latin-1; a lone "é" is not valid UTF-8), and that
    failure is exactly how we know to leave it alone.
    """
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def normalise(s: str) -> str:
    """The form values are compared in: an ID read as "1234 5678-9012" by the
    vision model and "123456789012" by the pattern reader must match."""
    return _STRIP.sub("", s.casefold())
