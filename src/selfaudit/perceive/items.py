"""Run every reader over a list of items, one model in GPU memory at a time.

The order is fixed because of the 8 GB budget: the vision model reads every
image, then (still loaded) every caption in text mode, then it is unloaded.
The rules layer and grounding run on the CPU afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from selfaudit.models import Finding, RawFinding, Skipped
from selfaudit.perceive.captions import CaptionBackend, NameReader, read_caption
from selfaudit.perceive.ground import ground
from selfaudit.perceive.patterns import lexicon, recognise
from selfaudit.perceive.vision import VisionBackend, perceive_image

Reader = Literal["vision", "patterns", "lexicon", "caption", "ner"]
ALL_READERS: tuple[Reader, ...] = ("vision", "patterns", "lexicon", "caption", "ner")


@dataclass
class ItemInput:
    item_id: str
    post_id: str
    image: bytes | None
    caption: str


@dataclass
class Backends:
    vision: VisionBackend | None
    captions: CaptionBackend | None
    names: NameReader | None
    analyzer: object | None  # presidio AnalyzerEngine; typed loosely to keep imports light


def analyse_items(
    items: list[ItemInput],
    backends: Backends,
    *,
    use: tuple[Reader, ...] = ALL_READERS,
    on_progress: Callable[[str, int, int], None] = lambda s, d, t: None,
) -> tuple[list[Finding], list[Skipped]]:
    """Read every item with the readers in `use`; return grounded findings and skips.

    `use` exists for the ablation (spec 9.3): the same items are run with
    subsets of readers to show what each layer adds. Every per-item call is
    wrapped, so one bad image costs one "couldn't check" line, not the run.
    """
    raws: list[RawFinding] = []
    skipped: list[Skipped] = []

    if "vision" in use and backends.vision is not None:
        with_image = [it for it in items if it.image is not None]
        for n, it in enumerate(with_image, 1):
            out = perceive_image(it.item_id, it.image, it.caption, backends.vision)
            if isinstance(out, Skipped):
                skipped.append(out)
            else:
                raws += out
            on_progress("images", n, len(with_image))

    if "caption" in use and backends.captions is not None:
        names = backends.names if "ner" in use else None
        # Carousel items share a caption; read each distinct (post, caption) once
        # and attach the findings to the post's first item.
        seen: set[str] = set()
        todo = [it for it in items if it.caption.strip() and not (it.post_id in seen or seen.add(it.post_id))]
        for n, it in enumerate(todo, 1):
            try:
                raws += read_caption(it.item_id, it.caption, backends.captions, names)
            except Exception:
                skipped.append(Skipped(ref=it.item_id, reason="caption_error"))
            on_progress("captions", n, len(todo))

    if backends.vision is not None and "vision" in use:
        backends.vision.unload()  # free the GPU before anything else may need it

    # Rules layer over caption + whatever the vision model transcribed.
    transcribed: dict[str, str] = {}
    for r in raws:
        if r.reader == "vision" and r.extracted_text:
            transcribed[r.item_id] = transcribed.get(r.item_id, "") + "\n" + r.extracted_text
    # A carousel's images all carry the post's caption. The caption's own text
    # is checked on the post's first item only, or "Amma" would be flagged once
    # per image; later items are checked on what was transcribed from them.
    firsts: set[str] = set()
    posts_seen: set[str] = set()
    for it in items:
        if it.post_id not in posts_seen:
            posts_seen.add(it.post_id)
            firsts.add(it.item_id)
    for it in items:
        caption = it.caption if it.item_id in firsts else ""
        if "patterns" in use and backends.analyzer is not None:
            try:
                raws += recognise(it.item_id, caption + transcribed.get(it.item_id, ""), backends.analyzer)
            except Exception:
                skipped.append(Skipped(ref=it.item_id, reason="pattern_error"))
        if "lexicon" in use:
            raws += lexicon(it.item_id, caption)

    captions = {it.item_id: it.caption for it in items}
    post_of = {it.item_id: it.post_id for it in items}
    return ground(raws, captions, post_of), skipped
