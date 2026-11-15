"""The whole audit: export in, report out, and the two feedback buttons.

Order is set by the 8 GB GPU: the vision model reads every image and keyframe
(and every caption in text mode), is unloaded, and only then does the speaker
model load. Audio is decoded on the CPU while items are being built, so it
costs no GPU time.

Logging rule: counts and timings only. Never a caption, a value or a file
name, because the log is the one place the user cannot see us write.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from selfaudit import config, fixes
from selfaudit.ingest.export import load_profile, open_export
from selfaudit.models import Category, Finding, Profile, Report, Skipped, VoiceResult
from selfaudit.perceive.items import Backends, ItemInput, analyse_items
from selfaudit.perceive.video import MediaError, extract_audio, keyframes
from selfaudit.perceive.voice import CleanGate, Embedder, Vad, voice_exposure
from selfaudit.recipes import evaluate
from selfaudit.rollup import roll_up

log = logging.getLogger("selfaudit")

_NO_VOICE = VoiceResult(clean_seconds=0.0, band="none", enrolled=False, seconds_by_post={})


@dataclass
class AllBackends(Backends):
    vad: Vad | None = None
    embedder: Embedder | None = None
    gate: CleanGate | None = None


@dataclass
class AuditState:
    profile: Profile
    findings: list[Finding]
    voice: VoiceResult
    couldnt_check: list[Skipped] = field(default_factory=list)

    def report(self) -> Report:
        """Computed fresh on every call, so feedback is reflected immediately and
        there is no cached report to drift out of date."""
        ingredients, unsure, past = roll_up(self.findings, self.voice, self.profile)
        aside = {f.finding_id for f in unsure} | {f.finding_id for f in past}
        return Report(
            posts_read=len(self.profile.posts),
            is_private=self.profile.is_private,
            recipes=evaluate(ingredients, unsure, self.profile),
            fixes=fixes.rank_fixes(self.findings, self.voice, self.profile),
            findings=[f for f in self.findings if f.finding_id not in aside],
            unsure=unsure,
            past_exposure=past,
            voice=self.voice,
            couldnt_check=self.couldnt_check,
            not_checked=self.profile.not_checked,
            private_would_lower=fixes.private_would_lower(self.findings, self.voice, self.profile),
        )

    def secrets(self) -> set[str]:
        """Everything that must never reach a log, an API response or the wording model."""
        out = {f.value for f in self.findings if f.value}
        out |= {s for s in (self.profile.name, self.profile.username) if s}
        return out


def _items_and_audio(profile: Profile, src, couldnt: list[Skipped]
                     ) -> tuple[list[ItemInput], dict[str, np.ndarray]]:
    items: list[ItemInput] = []
    audio: dict[str, list[np.ndarray]] = {}
    for post in profile.posts:
        before = len(items)
        for m in post.media:
            try:
                data = src.read_media(m.zip_path)
            except Exception:
                couldnt.append(Skipped(ref=m.item_id, reason="unreadable"))
                continue
            if m.kind == "image":
                items.append(ItemInput(m.item_id, post.post_id, data, post.caption))
                continue
            try:
                frames = keyframes(data)
                # Stories expire, so their speech is not a current voice
                # exposure (spec 7.4); their frames are still read for past exposure.
                if post.source != "story":
                    wav = extract_audio(data)
                    if len(wav):
                        audio.setdefault(post.post_id, []).append(wav)
            except MediaError:
                couldnt.append(Skipped(ref=m.item_id, reason="unreadable_video"))
                continue
            for n, jpeg in enumerate(frames):
                # The caption travels with the first frame only, so the rules
                # layer does not report one caption eight times.
                items.append(ItemInput(f"{m.item_id}#f{n}", post.post_id, jpeg, post.caption if n == 0 else ""))
        if len(items) == before and post.caption.strip():
            # Every media file failed: the caption can still be read.
            items.append(ItemInput(f"{post.post_id}/caption", post.post_id, None, post.caption))
    # A post with several videos contributes one clip, joined end to end.
    return items, {p: np.concatenate(w) for p, w in audio.items()}


def run_audit(export_path: Path, enrol: np.ndarray | None, backends: AllBackends, *,
              on_progress: Callable[[str, int, int], None] = lambda s, d, t: None,
              max_items: int | None = config.MAX_ITEMS) -> AuditState:
    t0 = time.perf_counter()
    src = open_export(export_path)
    profile = load_profile(export_path, max_items=max_items, source=src)
    couldnt = list(profile.couldnt_check)

    items, clips = _items_and_audio(profile, src, couldnt)
    log.info("audit: %d posts, %d items, %d clips", len(profile.posts), len(items), len(clips))

    findings, skipped = analyse_items(items, backends, on_progress=on_progress)
    couldnt += skipped
    log.info("audit: readers done, %d findings, %d skipped, %.1f s",
             len(findings), len(skipped), time.perf_counter() - t0)

    voice = _NO_VOICE
    if clips and backends.vad and backends.embedder and backends.gate:
        on_progress("voice", 0, len(clips))
        try:
            # The vision model was unloaded at the end of analyse_items, so the
            # speaker model loads into free memory here.
            voice = voice_exposure(clips, enrol, vad=backends.vad, embedder=backends.embedder, gate=backends.gate)
        except Exception:
            couldnt += [Skipped(ref=p, reason="voice_error") for p in clips]
        on_progress("voice", len(clips), len(clips))
    log.info("audit: done in %.1f s", time.perf_counter() - t0)
    return AuditState(profile=profile, findings=findings, voice=voice, couldnt_check=couldnt)


def mark_wrong(state: AuditState, finding_id: str) -> Report:
    """"This is wrong": drop the finding and recompute everything that used it."""
    state.findings = [f for f in state.findings if f.finding_id != finding_id]
    return state.report()


def mark_missed(state: AuditState, post_id: str, category: Category) -> Report:
    """"You missed something": the user is the best reader of their own posts,
    so their report is confirmed outright."""
    # A document's number is what the recipe needs; the user's word stands in for it.
    value = "reported by you" if category in ("ID_DOCUMENT", "FINANCIAL") else None
    state.findings.append(Finding(
        finding_id=f"{post_id}:user:{category}", item_id=f"{post_id}/media-0", post_id=post_id,
        category=category, what="reported by you", confidence="confirmed", supports=["user"], value=value))
    return state.report()
