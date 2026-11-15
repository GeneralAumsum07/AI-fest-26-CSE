"""Named test helpers shared across test files (plan: "Shared test helpers").

Plain functions rather than fixtures where a test needs to modify the result
(for example appending a bad media entry to a persona post).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from selfaudit.devtools.persona import PersonaPost, PersonaSpec

UTC = timezone.utc


def SPEC3(jpg: Path) -> PersonaSpec:
    """Asha Rao, public: a birthday post, a two-photo Hindi-caption carousel and a story.

    The captions are chosen to exercise text repair (emoji and Devanagari) and
    the dates to pin the reference date to the story, the newest item.
    """
    return PersonaSpec(
        name="Asha Rao", username="asha.rao", bio="", private=False,
        posts=[
            PersonaPost("Happy birthday Amma ❤️", [jpg], datetime(2026, 11, 1, tzinfo=UTC)),
            PersonaPost("गोवा", [jpg, jpg], datetime(2026, 11, 10, tzinfo=UTC)),
            PersonaPost("story", [jpg], datetime(2026, 11, 12, tzinfo=UTC), source="story"),
        ],
    )


def SPEC1(jpg: Path) -> PersonaSpec:
    """SPEC3's first post only: the smallest export with one real media file."""
    spec = SPEC3(jpg)
    spec.posts = spec.posts[:1]
    return spec


# --- Task 4: vision fakes ------------------------------------------------------

def F(**k):
    """A VisionFinding with sensible defaults; override any field."""
    from selfaudit.perceive.vision import VisionFinding

    base = dict(category="CONTACT", what="phone on a poster", model_confidence="high")
    base.update(k)
    return VisionFinding(**base)


class Queue:
    """Fake VisionBackend: each describe() pops the next queued item and raises
    it if it is an exception. Empty queue -> no findings."""

    def __init__(self, items, log: list | None = None):
        self.items = list(items)
        self.calls = 0
        self.max_sides: list[int] = []
        self.short_prompts: list[bool] = []
        self.log = log

    def describe(self, image, caption, *, max_side=1280, short_prompt=False):
        from selfaudit.perceive.vision import VisionOutput

        self.calls += 1
        self.max_sides.append(max_side)
        self.short_prompts.append(short_prompt)
        if self.log is not None:
            self.log.append("vision")
        item = self.items.pop(0) if self.items else VisionOutput(findings=[])
        if isinstance(item, BaseException) or (isinstance(item, type) and issubclass(item, BaseException)):
            raise item
        return item

    def unload(self):
        if self.log is not None:
            self.log.append("unload")


# --- Task 5: caption fakes ----------------------------------------------------

class FakeCaptions:
    def __init__(self, findings, log: list | None = None):
        self.findings, self.calls, self.log = findings, 0, log

    def read(self, caption):
        self.calls += 1
        if self.log is not None:
            self.log.append("caption")
        return list(self.findings)


class FakeNames:
    def __init__(self, pairs, log: list | None = None):
        self.pairs, self.calls, self.log = pairs, 0, log

    def names(self, text):
        self.calls += 1
        if self.log is not None:
            self.log.append("ner")
        return list(self.pairs)


# --- Tasks 6 and 7: findings ----------------------------------------------------

def R(reader, category, **k):
    """A RawFinding for item "p/media-0"."""
    from selfaudit.models import RawFinding

    base = dict(item_id="p/media-0", category=category, what="w", reader=reader)
    base.update(k)
    return RawFinding(**base)


def Fd(item_id, category, confidence, value="v", **k):
    """A Finding with supports=["vision"]; post_id is item_id before the first "/"."""
    from selfaudit.models import Finding

    base = dict(finding_id=f"{item_id}:{category}", item_id=item_id, post_id=item_id.split("/", 1)[0],
                category=category, what="w", confidence=confidence, supports=["vision"], value=value)
    base.update(k)
    return Finding(**base)
