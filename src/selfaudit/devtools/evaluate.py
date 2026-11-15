"""Held-out evaluation and the reader ablation (spec section 10).

    uv run python -m selfaudit.devtools.evaluate --split data/heldout --out results/

Runs once, after tuning is finished. Writes one JSON and one Markdown table per
system. The ablation runs the same items through subsets of readers so the
slide can show what each layer adds over a rules-only baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from selfaudit.devtools.freeze import MANIFEST, verify
from selfaudit.devtools.metrics import Metrics, item_metrics, wilson
from selfaudit.devtools.synthetic import load_labels
from selfaudit.perceive.items import ALL_READERS, Backends, ItemInput, Reader, analyse_items

__all__ = ["SYSTEMS", "run_system", "audio_metrics", "persona_check", "main", "wilson"]

SYSTEMS: dict[str, tuple[Reader, ...]] = {
    "B0": ("patterns", "lexicon"),                     # rules only; captions only, no model sees a pixel
    "B1": ("vision",),                                 # vision model, no corroboration
    "B2": ("caption", "ner", "patterns", "lexicon"),   # text only, images ignored
    "Full": ALL_READERS,
}

# The committed copy of the held-out manifest (Task 2). The split folder itself
# is git-ignored, so this file is the dated record of what was frozen.
COMMITTED_MANIFEST = Path("eval") / f"heldout.{MANIFEST}"


def _items(split_dir: Path, *, with_images: bool) -> tuple[list, list[ItemInput]]:
    labels = load_labels(split_dir)
    items = [ItemInput(item_id=f"{l.item_id}/media-0", post_id=l.item_id,
                       image=(split_dir / l.file).read_bytes() if with_images else None,
                       caption=l.caption) for l in labels]
    return labels, items


def run_system(name: str, split_dir: Path, backends: Backends) -> Metrics:
    use = SYSTEMS[name]
    # B0 gets no image bytes at all, not just an unused vision reader: the
    # baseline must be visibly incapable of looking at a pixel.
    labels, items = _items(Path(split_dir), with_images=name != "B0")
    findings, _ = analyse_items(items, backends, use=use)
    return item_metrics(labels, findings)


def audio_metrics(audio_dir: Path, enrol: Path, *, vad, embedder, gate) -> dict:
    """Score the voice stage on the clips held back from tuning.

    labels.json: [{"file": str, "seconds": float, "split": "tune" | "test"}],
    where seconds is the true amount of the enrolled person's clean speech.
    Only "test" clips are scored; the "tune" half was used in Task 9.
    """
    from selfaudit.perceive.video import extract_audio
    from selfaudit.perceive.voice import band_for, voice_exposure

    audio_dir = Path(audio_dir)
    labels = [l for l in json.loads((audio_dir / "labels.json").read_text(encoding="utf-8"))
              if l.get("split", "test") == "test"]
    me = extract_audio(Path(enrol).read_bytes())
    right, errors, other_seconds = 0, [], 0.0
    for l in labels:
        clip = extract_audio((audio_dir / l["file"]).read_bytes())
        # One clip per call, so one clip's speech cannot be clustered with another's.
        v = voice_exposure({l["file"]: clip}, me, vad=vad, embedder=embedder, gate=gate)
        got = v.seconds_by_post.get(l["file"], 0.0)
        right += band_for(got) == band_for(l["seconds"])
        errors.append(abs(got - l["seconds"]))
        if l["seconds"] == 0:
            other_seconds += got  # speech credited to the user that was not theirs
    n = len(labels)
    return {"clips": n, "band_correct": right, "band_interval": wilson(right, n),
            "mean_abs_error_s": float(np.mean(errors)) if errors else 0.0,
            "other_speaker_seconds_counted": other_seconds}


def _meets(got: str | None, want: str | None) -> bool:
    """want is a level, None for "not shown", or "max:<level>" for "not above"."""
    from selfaudit.recipes import LEVEL_RANK
    if want is None:
        return got is None
    if want.startswith("max:"):
        return got is None or LEVEL_RANK[got] <= LEVEL_RANK[want[4:]]
    return got == want


def persona_check(persona_dir: Path, expected: dict[str, str | None], enrol: Path | None,
                  backends) -> dict[str, bool]:
    from selfaudit.perceive.video import extract_audio
    from selfaudit.pipeline import run_audit

    wav = extract_audio(Path(enrol).read_bytes()) if enrol else None
    report = run_audit(Path(persona_dir), wav, backends).report()
    levels = {r.recipe_id: r.level for r in report.recipes}
    out = {rid: _meets(levels.get(rid), want) for rid, want in expected.items() if rid != "not_sure"}
    if "not_sure" in expected:  # count of "Not sure" findings the persona should show
        out["not_sure"] = len(report.unsure) == int(expected["not_sure"])
    return out


def _table(name: str, m: Metrics) -> str:
    # Counts first, then percentages with their intervals (spec 10).
    rows = [f"### {name}", "", "| category | caught | missed | false alarms |", "|---|---|---|---|"]
    rows += [f"| {c} | {n.caught} | {n.missed} | {n.false_alarms} |" for c, n in m.per_category.items()]
    lo, hi = wilson(m.risky_flagged, m.risky_total)
    blo, bhi = wilson(m.benign_flagged, m.benign_total)
    rows += ["", f"Risky flagged: {m.risky_flagged} of {m.risky_total} "
                 f"({m.risky_flagged / max(m.risky_total, 1):.0%}, 95% interval {lo:.0%}–{hi:.0%})",
             f"Benign flagged: {m.benign_flagged} of {m.benign_total} "
             f"({m.benign_flagged / max(m.benign_total, 1):.0%}, 95% interval {blo:.0%}–{bhi:.0%}); "
             f"{m.benign_confirmed} of those confirmed", f"Items marked Not sure: {m.unsure_items}", ""]
    return "\n".join(rows)


def _check_frozen(split: Path) -> None:
    if not verify(split):
        sys.exit(f"{split} changed since it was frozen; refusing to evaluate.")
    # The committed manifest guards against re-freezing a changed set: verify()
    # alone would pass if someone regenerated both the set and its manifest.
    if split.name == "heldout":
        if not COMMITTED_MANIFEST.exists():
            sys.exit(f"{COMMITTED_MANIFEST} is missing; the held-out set has no committed record.")
        if COMMITTED_MANIFEST.read_text(encoding="utf-8") != (split / MANIFEST).read_text(encoding="utf-8"):
            sys.exit(f"{split} does not match {COMMITTED_MANIFEST}; refusing to evaluate.")


def main(argv: list[str] | None = None, backends: Backends | None = None) -> None:
    p = argparse.ArgumentParser(prog="selfaudit.devtools.evaluate")
    p.add_argument("--split", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--systems", nargs="*", default=list(SYSTEMS))
    p.add_argument("--frozen", action="store_true", help="refuse to run unless the split matches its freeze")
    a = p.parse_args(argv)
    if a.frozen or a.split.name == "heldout":
        _check_frozen(a.split)

    if backends is None:
        from selfaudit.devtools.devrun import real_backends
        backends = real_backends()
    a.out.mkdir(parents=True, exist_ok=True)
    md = []
    for name in a.systems:
        m = run_system(name, a.split, backends)
        (a.out / f"{name}.json").write_text(m.model_dump_json(indent=1), encoding="utf-8")
        md.append(_table(name, m))
        print(md[-1])
    (a.out / "results.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    main()
