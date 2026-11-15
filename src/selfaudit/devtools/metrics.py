"""Item-level metrics and the Wilson interval (spec section 10).

An item is "flagged" when it has at least one confirmed or likely finding;
unsure findings are counted separately because the report shows them as
"Not sure", not as risks. The headline numbers are about items, not
findings, because a user acts on posts.
"""

from __future__ import annotations

import math

from pydantic import BaseModel

from selfaudit.devtools.synthetic import MVP_ITEM_CATEGORIES, ItemLabel
from selfaudit.models import Finding


class CategoryCount(BaseModel):
    caught: int = 0
    missed: int = 0
    false_alarms: int = 0


class Metrics(BaseModel):
    per_category: dict[str, CategoryCount]
    risky_total: int
    risky_flagged: int
    benign_total: int
    benign_flagged: int
    benign_confirmed: int
    unsure_items: int


def _item_key(item_id: str) -> str:
    # Findings may carry "<id>/media-0" or "<id>#f3" (video frames); labels use the bare id.
    return item_id.split("/", 1)[0].split("#", 1)[0]


def item_metrics(labels: list[ItemLabel], findings: list[Finding]) -> Metrics:
    by_item: dict[str, list[Finding]] = {}
    for f in findings:
        by_item.setdefault(_item_key(f.item_id), []).append(f)

    per = {c: CategoryCount() for c in MVP_ITEM_CATEGORIES}
    m = dict(risky_total=0, risky_flagged=0, benign_total=0, benign_flagged=0, benign_confirmed=0, unsure_items=0)
    for label in labels:
        fs = by_item.get(label.item_id, [])
        real = [f for f in fs if f.confidence in ("confirmed", "likely")]
        flagged_cats = {f.category for f in real}
        if any(f.confidence == "unsure" for f in fs):
            m["unsure_items"] += 1
        if label.categories:
            m["risky_total"] += 1
            m["risky_flagged"] += bool(real)
        else:
            m["benign_total"] += 1
            m["benign_flagged"] += bool(real)
            m["benign_confirmed"] += any(f.confidence == "confirmed" for f in fs)
        for c in per:
            if c in label.categories:
                if c in flagged_cats:
                    per[c].caught += 1
                else:
                    per[c].missed += 1
            elif c in flagged_cats:
                per[c].false_alarms += 1
    return Metrics(per_category=per, **m)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n.

    Chosen over the plain k/n +- error because it stays inside [0, 1] and is
    honest at the small n a hackathon test set has (35 risky items).
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))
