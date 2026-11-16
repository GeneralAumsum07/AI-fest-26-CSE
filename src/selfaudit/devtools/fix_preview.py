"""Before/after numbers for the deck: what the top fixes change on a finished audit.

    python -m selfaudit.devtools.fix_preview <audit-id> <name> [--server http://127.0.0.1:8765]

Asks a running server for the real report, then for the preview after the top
1 and the top 3 fixes, and writes the recipe levels to results/fix-preview/<name>.json.
It goes through the same /preview endpoint as the page instead of calling
fixes.preview directly, so the deck's numbers are exactly what a judge sees
when they tick the boxes. Levels only: no findings, names or numbers.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def _get(url: str) -> dict:
    with urllib.request.urlopen(url) as r:
        return json.load(r)


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def levels(recipes: list[dict]) -> dict[str, str]:
    # "none" rather than null so the JSON reads plainly on a slide.
    return {r["recipe_id"]: ("not sure" if r.get("not_sure") else r["level"] or "none") for r in recipes}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audit_id")
    ap.add_argument("name", help="output file name, e.g. high")
    ap.add_argument("--server", default="http://127.0.0.1:8765")
    a = ap.parse_args()
    base = f"{a.server}/api/audits/{a.audit_id}"
    body = _get(f"{base}/report")
    fixes, text = body["report"]["fixes"], body["text"]["fixes"]
    out = {"before": levels(body["report"]["recipes"])}
    for n in (1, 3):
        k = min(n, len(fixes))
        after = levels(_post(f"{base}/preview", {"fixes": list(range(k))})["recipes"])
        # A recipe that ends drops out of the list entirely; say "none" so the
        # before and after rows line up recipe for recipe.
        out[f"after_top_{n}"] = {rid: after.get(rid, "none") for rid in out["before"]}
        out[f"after_top_{n}_fixes_used"] = k        # fewer than n when the report has fewer fixes
    out["fix_text"] = text                          # "Delete post 5 (...)": already redacted by the server
    dest = Path("results/fix-preview") / f"{a.name}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
