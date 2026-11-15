"""Task 7: item-level metrics and the Wilson interval."""

from helpers import Fd

from selfaudit.devtools.metrics import CategoryCount, item_metrics, wilson
from selfaudit.devtools.synthetic import ItemLabel


def test_item_metrics_counts():
    labels = [ItemLabel(item_id="1", file="", caption="", categories=["ID_DOCUMENT"], values={}),
              ItemLabel(item_id="2", file="", caption="", categories=["CONTACT"], values={}),
              ItemLabel(item_id="3", file="", caption="", categories=[], values={}),
              ItemLabel(item_id="4", file="", caption="", categories=[], values={})]
    found = [Fd("1", "ID_DOCUMENT", "confirmed"), Fd("3", "CONTACT", "confirmed"), Fd("4", "FINANCIAL", "unsure")]
    m = item_metrics(labels, found)
    assert (m.risky_total, m.risky_flagged, m.benign_total, m.benign_flagged, m.benign_confirmed,
            m.unsure_items) == (2, 1, 2, 1, 1, 1)
    assert m.per_category["ID_DOCUMENT"] == CategoryCount(caught=1, missed=0, false_alarms=0)
    assert m.per_category["CONTACT"] == CategoryCount(caught=0, missed=1, false_alarms=1)


def test_findings_on_media_ids_count_for_their_item():
    labels = [ItemLabel(item_id="1", file="", caption="", categories=["CONTACT"], values={})]
    m = item_metrics(labels, [Fd("1/media-0", "CONTACT", "likely")])
    assert m.risky_flagged == 1


def test_wilson_stays_in_range_and_brackets_the_rate():
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(35, 35)
    assert 0.85 < lo < 1.0 and hi == 1.0
    lo, hi = wilson(20, 35)
    assert lo < 20 / 35 < hi
