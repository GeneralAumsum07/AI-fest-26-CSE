"""Re-run the YouTube live check after the keyframe-duplicate fix (c8da02b).

Same synthetic fixture and the same assertions as results/youtube-e2e/check_report.py,
plus the one this re-check exists for: each (post, category) appears once.
Uploads through the same /api/audits endpoint the page uses; the report is then
opened in the browser separately. Prints the audit id for that.
"""
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Fixtures stay git-ignored under results/; rebuild them with
# results/youtube-e2e/build_fixture.py. Repo root is three levels up.
EVID = Path(__file__).resolve().parents[3] / "results" / "youtube-e2e"
BASE = "http://127.0.0.1:8766"

with httpx.Client(base_url=BASE, timeout=60) as client:
    # The server loads spaCy and friends at start; wait for it rather than fail.
    for _ in range(180):
        try:
            client.get("/")
            break
        except httpx.TransportError:
            time.sleep(1)
    else:
        raise SystemExit("server on 8766 never came up")

    files = {"export": ("takeout-youtube.zip", (EVID / "takeout-youtube.zip").read_bytes(), "application/zip"),
             "enrol": ("enrol.wav", (EVID / "enrol.wav").read_bytes(), "audio/wav")}
    audit = client.post("/api/audits", files=files).raise_for_status().json()["id"]
    print("audit:", audit, flush=True)

    start, last = time.monotonic(), None
    while time.monotonic() - start < 900:
        p = client.get(f"/api/audits/{audit}/progress").raise_for_status().json()
        stage = (p["stage"], p["done"], p["total"])
        if stage != last:
            print("progress:", stage, flush=True)
            last = stage
        assert p["error"] is None, p
        if p["finished"]:
            break
        time.sleep(1)
    else:
        raise AssertionError("audit did not finish in 15 minutes")

    body = client.get(f"/api/audits/{audit}/report").raise_for_status().json()
    report = body["report"]
    payload = client.get(f"/api/audits/{audit}/payload").raise_for_status().json()
    shown = report["findings"] + report["unsure"]
    pairs = Counter((f["post_id"], f["category"]) for f in shown)
    categories = sorted({f["category"] for f in report["findings"]})
    summary = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "audit_id": audit,
               "after_commit": "c8da02b", "real_models": True, "upload": "api (same endpoint as the page)",
               "posts_read": report["posts_read"], "categories": categories,
               "finding_counts": {f"{k[0]}:{k[1]}": v for k, v in sorted(pairs.items())},
               "voice": report["voice"], "recipes": {r["recipe_id"]: r["level"] for r in report["recipes"]},
               "skipped": report["couldnt_check"], "fix_count": len(report["fixes"]),
               "sent_to_cloud": body["sent_to_cloud"]}
    (EVID / "recheck-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)

    # --- the new check ---
    dupes = {k: v for k, v in pairs.items() if v > 1}
    assert not dupes, f"duplicate findings: {dupes}"

    # --- GPT's original assertions, unchanged ---
    assert report["posts_read"] == 2
    assert {"ID_DOCUMENT", "CONTACT", "FAMILY_RELATION", "AWAY_STATUS"} <= set(categories)
    assert [s["reason"] for s in report["couldnt_check"]] == ["not_public", "not_public"]
    assert report["voice"]["enrolled"] and report["voice"]["clean_seconds"] > 5
    assert set(report["voice"]["seconds_by_post"]) == {"video-0001"}
    assert all(f["post_id"] == "video-0001" for f in report["findings"])
    assert not any("value" in f for f in shown)
    assert report["fixes"] and any(r["recipe_id"] == "R3" and r["level"] for r in report["recipes"])
    assert body["sent_to_cloud"] is False
    outgoing = json.dumps([body, payload])
    secrets = ["owner@example.com", "private@example.com", "unlisted@example.com",
               "PRIVATE-SENTINEL-7841", "UNLISTED-SENTINEL-9312",
               "SECRET-HISTORY", "SECRET-COMMENT", "SECRET-SUB", "Synthetic Smoke Channel"]
    assert not any(s in outgoing for s in secrets)
    values = json.loads((EVID / "synthetic-values.json").read_text())
    numbers = [re.sub(r"\D", "", str(v)) for v in values.values()]
    assert not any(len(n) >= 10 and n in re.sub(r"\D", "", outgoing) for n in numbers)
    for post in ("video-0001", "video-0002"):
        t = client.get(f"/api/audits/{audit}/media/{post}/0")
        assert t.status_code == 200 and t.headers["content-type"].startswith("image/jpeg")
    for post in ("video-0003", "video-0004"):
        assert client.get(f"/api/audits/{audit}/media/{post}/0").status_code == 404
    print("RECHECK PASSED", flush=True)
