"""How much clean speech in the user's own voice is public (spec 7.4).

The question a voice-cloning attacker asks is "how many seconds of clean,
single-speaker audio of this person can I collect?". So the pipeline is:
speech segments (VAD) -> drop scraps -> drop noisy segments (gate) ->
keep only the user's voice (speaker match against an enrolment clip, or the
dominant speaker when there is none) -> total seconds -> a band.

The three models sit behind Protocols so the tests run on fakes and the real
models load lazily, once.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from selfaudit import config
from selfaudit.models import Band, VoiceResult

SR = 16000
_BAND_RANK = {"none": 0, "low": 1, "moderate": 2, "high": 3}


def band_for(seconds: float) -> Band:
    # Edges from spec 7.4: a few seconds already clones badly; half a minute clones well.
    if seconds <= 0:
        return "none"
    if seconds < 5:
        return "low"
    if seconds <= 30:
        return "moderate"
    return "high"


def _cap(band: Band, enrolled: bool) -> Band:
    # Without enrolment the "dominant speaker" may be someone else (a friend
    # who talks more), so the app never claims more than moderate (spec 7.4).
    if not enrolled and _BAND_RANK[band] > _BAND_RANK["moderate"]:
        return "moderate"
    return band


class Vad(Protocol):
    def segments(self, wav: np.ndarray) -> list[tuple[float, float]]: ...  # seconds


class Embedder(Protocol):
    def embed(self, wav: np.ndarray) -> np.ndarray: ...  # unit vector


class CleanGate(Protocol):
    def is_clean(self, wav: np.ndarray) -> bool: ...


class SileroVad:
    def __init__(self):
        self._model = None

    def segments(self, wav: np.ndarray) -> list[tuple[float, float]]:
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad

        if self._model is None:
            self._model = load_silero_vad()
        if len(wav) == 0:
            return []
        ts = get_speech_timestamps(torch.from_numpy(wav), self._model, sampling_rate=SR, return_seconds=True)
        return [(float(t["start"]), float(t["end"])) for t in ts]


class EcapaEmbedder:
    def __init__(self):
        self._model = None

    def embed(self, wav: np.ndarray) -> np.ndarray:
        import torch

        if self._model is None:
            from speechbrain.inference.speaker import EncoderClassifier
            from speechbrain.utils.fetching import LocalStrategy

            # COPY, not the default symlink: Windows without developer mode
            # cannot create the symlinks SpeechBrain's cache uses.
            self._model = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb", savedir="pretrained_models/ecapa",
                local_strategy=LocalStrategy.COPY, run_opts={"device": "cpu"})
        with torch.no_grad():
            e = self._model.encode_batch(torch.from_numpy(wav)[None]).reshape(-1).cpu().numpy()
        return e / (np.linalg.norm(e) + 1e-9)


class DefaultGate:
    """Signal-to-noise estimated inside the segment itself.

    Why this works without a separate noise model: speech has gaps between
    syllables and words. With clean speech those 20 ms frames drop to near
    silence; under music or a crowd they stay loud. So the ratio of the loud
    frames (90th percentile energy) to the quiet ones (10th percentile) is a
    cheap SNR estimate. Chosen as the always-works fallback from spec 8.
    """

    def __init__(self, min_snr_db: float = config.CLEAN_SNR_DB):
        self.min_snr_db = min_snr_db

    def is_clean(self, wav: np.ndarray) -> bool:
        frame = SR // 50  # 20 ms
        n = len(wav) // frame
        if n < 10:
            return False  # too short to judge, treat as not clean
        energy = (wav[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-10
        snr = 10 * np.log10(np.percentile(energy, 90) / np.percentile(energy, 10))
        return bool(snr >= self.min_snr_db)


def _dominant_cluster(embs: np.ndarray, durs: np.ndarray) -> np.ndarray:
    """Average-linkage agglomerative clustering at cosine distance 1 - SIM_THRESHOLD;
    return a boolean mask of the cluster with the most seconds.

    Hand-written to save a scipy/sklearn dependency for one function.

    Why the Lance-Williams update: the average similarity between a merged
    cluster and any other is the size-weighted mean of the two old rows, so the
    cluster-to-cluster matrix is updated in place instead of re-averaging every
    pair of members each round. Same merges, same result as the pairwise loop
    (pinned by test_fast_clustering_matches_the_original), but a reel-heavy
    profile of ~1,000 segments takes about a second instead of many minutes.
    """
    n = len(embs)
    clusters: list[list[int] | None] = [[i] for i in range(n)]
    size = np.ones(n)
    sim = (embs @ embs.T).astype(float)
    # Only pairs a < b among live clusters compete; everything else is -inf.
    # Row-major argmax over the upper triangle picks the same first-best pair
    # as the original nested a < b loops.
    live = np.triu(np.ones((n, n), dtype=bool), k=1)
    limit = config.SIM_THRESHOLD
    while live.any():
        flat = int(np.argmax(np.where(live, sim, -np.inf)))
        a, b = divmod(flat, n)
        if sim[a, b] < limit:  # closest pair is further apart than the distance cut
            break
        merged = (size[a] * sim[a] + size[b] * sim[b]) / (size[a] + size[b])
        sim[a, :], sim[:, a] = merged, merged
        size[a] += size[b]
        clusters[a] += clusters[b]
        clusters[b] = None
        live[b, :] = False
        live[:, b] = False
    # Surviving clusters in original index order, as the list-popping loop left them.
    remaining = [c for c in clusters if c is not None]
    top = max(remaining, key=lambda c: durs[c].sum())
    mask = np.zeros(n, dtype=bool)
    mask[top] = True
    return mask


def voice_exposure(clips: dict[str, np.ndarray], enrol: np.ndarray | None, *, vad: Vad,
                   embedder: Embedder, gate: CleanGate) -> VoiceResult:
    """Seconds of clean speech in the user's voice across `clips` (keyed by post_id).

    The caller has already left stories out and joined a post's videos into one clip.
    """
    posts: list[str] = []
    durs: list[float] = []
    embs: list[np.ndarray] = []
    for post_id, wav in clips.items():
        for start, end in vad.segments(wav):
            if end - start < config.MIN_SEGMENT_S:
                continue
            seg = wav[int(start * SR): int(end * SR)]
            if not gate.is_clean(seg):
                continue
            posts.append(post_id)
            durs.append(end - start)
            embs.append(embedder.embed(seg))

    enrolled = enrol is not None
    if not embs:
        return VoiceResult(clean_seconds=0.0, band="none", enrolled=enrolled, seconds_by_post={})

    e = np.stack(embs)
    d = np.asarray(durs)
    if enrolled:
        mine = e @ embedder.embed(enrol) >= config.SIM_THRESHOLD
    else:
        mine = _dominant_cluster(e, d)

    by_post: dict[str, float] = {}
    for p, dur, keep in zip(posts, durs, mine):
        if keep:
            by_post[p] = by_post.get(p, 0.0) + float(dur)
    total = sum(by_post.values())
    return VoiceResult(clean_seconds=total, band=_cap(band_for(total), enrolled),
                       enrolled=enrolled, seconds_by_post=by_post)


def drop_posts(voice: VoiceResult, post_ids: list[str]) -> VoiceResult:
    """What is left after archiving `post_ids`: the fix ranking needs this to say
    "archiving these two reels takes your voice from high to low"."""
    left = {p: s for p, s in voice.seconds_by_post.items() if p not in set(post_ids)}
    total = sum(left.values())
    return VoiceResult(clean_seconds=total, band=_cap(band_for(total), voice.enrolled),
                       enrolled=voice.enrolled, seconds_by_post=left)
