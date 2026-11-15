"""Shared test fixtures. Each later task adds the helpers it first needs."""

from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def jpg(tmp_path: Path) -> Path:
    """A tiny real JPEG. Real bytes (not a stub) so the export reader and the
    vision client exercise the same decode path they use on a phone photo."""
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (64, 64), (200, 120, 40)).save(path, "JPEG")
    return path


_TINY_CAPTIONS = """
- {text: "call me on +91 98765 43210", categories: [CONTACT], values: {phone: "+91 98765 43210"}}
- {text: "mail me asha@example.com", categories: [CONTACT], values: {email: "asha@example.com"}}
- {text: "Happy birthday Amma", categories: [FAMILY_RELATION], values: {}}
- {text: "भाई के साथ", categories: [FAMILY_RELATION], values: {}}
- {text: "off to Goa till Sunday", categories: [AWAY_STATUS], values: {}}
- {text: "airport vibes, back next week", categories: [AWAY_STATUS], values: {}}
- {text: "sunset", categories: [], values: {}}
- {text: "chai time", categories: [], values: {}}
- {text: "order 123456789012 arrived", categories: [], values: {}, hard_negative: true}
- {text: "Mother's Day sale at the mall", categories: [], values: {}, hard_negative: true}
- {text: "goa vibes from 2019 lol", categories: [], values: {}, hard_negative: true}
- {text: "helpline 1930 for cyber fraud", categories: [], values: {}, hard_negative: true}
"""


@pytest.fixture
def tiny_sources(tmp_path: Path) -> Path:
    """A minimal sources folder: one photo of each kind and a small caption list.
    generate_set reuses sources as often as it needs, so one of each is enough."""
    src = tmp_path / "sources"
    for sub, color in (("backgrounds", (90, 140, 90)), ("faces", (220, 180, 160)),
                       ("institution", (150, 150, 200))):
        (src / sub).mkdir(parents=True)
        Image.new("RGB", (320, 240), color).save(src / sub / "a.jpg", "JPEG")
    (src / "captions.yaml").write_text(_TINY_CAPTIONS, encoding="utf-8")
    return src
