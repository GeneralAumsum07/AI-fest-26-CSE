"""Run the readers over a labelled split and print item metrics.

    uv run python -m selfaudit.devtools.devrun --split data/dev

Use on the development split only. The held-out split is run once, by
devtools/evaluate.py, after tuning is finished.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from selfaudit.devtools.metrics import item_metrics, wilson
from selfaudit.devtools.synthetic import load_labels


def real_backends():
    """The production readers. Imported lazily: loading them takes seconds."""
    from selfaudit.perceive.captions import GlinerNames, OllamaCaptions
    from selfaudit.perceive.items import Backends
    from selfaudit.perceive.patterns import build_analyzer
    from selfaudit.perceive.vision import OllamaVision

    return Backends(vision=OllamaVision(), captions=OllamaCaptions(), names=GlinerNames(),
                    analyzer=build_analyzer())


def main(split: Path) -> None:
    from selfaudit.perceive.items import ItemInput, analyse_items

    labels = load_labels(split)
    items = [ItemInput(item_id=f"{l.item_id}/media-0", post_id=l.item_id,
                       image=(split / l.file).read_bytes(), caption=l.caption) for l in labels]
    start = time.perf_counter()
    findings, skipped = analyse_items(items, real_backends(),
                                      on_progress=lambda s, d, t: print(f"\r{s} {d}/{t}", end=""))
    elapsed = time.perf_counter() - start
    print(f"\n{len(items)} items in {elapsed:.0f} s ({elapsed / max(len(items), 1):.1f} s/item), "
          f"{len(skipped)} skipped")

    m = item_metrics(labels, findings)
    print(f"{'category':<16}{'caught':>8}{'missed':>8}{'false':>8}")
    for c, n in m.per_category.items():
        print(f"{c:<16}{n.caught:>8}{n.missed:>8}{n.false_alarms:>8}")
    lo, hi = wilson(m.risky_flagged, m.risky_total)
    print(f"risky flagged {m.risky_flagged}/{m.risky_total} (95% CI {lo:.2f}-{hi:.2f})")
    print(f"benign flagged {m.benign_flagged}/{m.benign_total}, confirmed {m.benign_confirmed}, "
          f"unsure items {m.unsure_items}")

    # Item ids only, never content: enough to open the image and look.
    by_item: dict[str, set[str]] = {}
    for f in findings:
        if f.confidence != "unsure":
            by_item.setdefault(f.post_id, set()).add(f.category)
    for l in labels:
        got = by_item.get(l.item_id, set())
        missed, extra = set(l.categories) - got, got - set(l.categories)
        if missed or extra:
            print(f"  {l.item_id}: missed {sorted(missed)} extra {sorted(extra)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--split", type=Path, required=True)
    main(p.parse_args().split)
