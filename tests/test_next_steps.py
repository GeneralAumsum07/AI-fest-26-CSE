"""Feature D: fixed next steps for an exposed ID, and the family card's "a caller might know" block."""

import pytest
from fastapi.testclient import TestClient

from selfaudit.app import create_app
from selfaudit.models import Finding, RecipeResult
from selfaudit.wording.next_steps import CALLER_LINES, ID_STEPS, caller_knows, next_steps


def _recipe(rid, level=None, not_sure=False, amplifiers=()):
    return RecipeResult(recipe_id=rid, level=level, not_sure=not_sure, has=[], missing=[],
                        amplifiers=list(amplifiers), look_at=[])


def _finding(cat, value="SECRET-VALUE-123"):
    return Finding(finding_id=f"f-{cat}", item_id="i1", post_id="p1", category=cat, what="x",
                   confidence="confirmed", supports=["vision"], value=value)


# ---- D1: next steps -------------------------------------------------------

def test_id_steps_appear_with_the_document_recipe():
    assert next_steps([_recipe("R3", "high")]) == {"R3": ID_STEPS}


def test_id_steps_appear_when_the_document_recipe_needs_review():
    # A "Needs review" card is still shown, so its steps are too.
    assert next_steps([_recipe("R3", None, not_sure=True)]) == {"R3": ID_STEPS}


def test_no_id_steps_without_the_document_recipe():
    assert next_steps([_recipe("R1", "high"), _recipe("R3", None)]) == {}


def test_id_steps_name_only_the_checked_official_services():
    text = " ".join(ID_STEPS)
    for must in ("sancharsaathi.gov.in", "Know Mobile Connections in Your Name", "uidai.gov.in",
                 "Lock/Unlock Biometrics", "1930", "cybercrime.gov.in"):
        assert must in text
    assert "watch for" not in text


# ---- D2: what a caller might know -----------------------------------------

def test_each_line_appears_only_with_its_ingredient():
    assert caller_knows([_finding("FAMILY_RELATION")], [], "none") == [CALLER_LINES["FAMILY_RELATION"]]
    assert caller_knows([_finding("INSTITUTION")], [], "none") == [CALLER_LINES["INSTITUTION"]]
    assert caller_knows([], [], "moderate") == [CALLER_LINES["VOICE"]]
    away = [_recipe("R1", "high", amplifiers=["AWAY_STATUS"])]
    assert caller_knows([], away, "none") == [CALLER_LINES["AWAY_STATUS"]]


def test_old_travel_is_not_travelling_right_now():
    # An away finding the recipes dropped as stale (not an amplifier) must not
    # print "travelling right now" on a card a parent keeps for months.
    assert caller_knows([_finding("AWAY_STATUS")], [_recipe("R1", "high")], "none") == []


def test_lines_come_in_a_fixed_order_once_each():
    got = caller_knows([_finding("INSTITUTION"), _finding("FAMILY_RELATION"), _finding("FAMILY_RELATION")],
                       [_recipe("R1", "high", amplifiers=["TRAVEL_DOC"])], "high")
    assert got == [CALLER_LINES[c] for c in ("FAMILY_RELATION", "INSTITUTION", "AWAY_STATUS", "VOICE")]


def test_no_ingredients_no_block():
    assert caller_knows([_finding("ID_DOCUMENT"), _finding("FACE_CLEAR")], [], "none") == []


def test_no_extracted_value_reaches_the_card():
    got = caller_knows([_finding("FAMILY_RELATION", "Amma Lakshmi"), _finding("INSTITUTION", "Mahindra University")],
                       [], "low")
    assert not any("Lakshmi" in line or "Mahindra" in line for line in got)


# ---- served with the report -----------------------------------------------

@pytest.fixture
def client(scripted_backends):
    with TestClient(create_app(lambda: scripted_backends)) as c:
        yield c


def test_report_body_carries_steps_and_card_lines_without_values(client, tmp_path, jpg, mp4_file):
    import time
    from pipeline_fakes import HIGH_EXPOSURE
    from selfaudit.devtools.persona import build_persona
    path = build_persona(HIGH_EXPOSURE(jpg, mp4_file), tmp_path / "zip", as_zip=True)
    id_ = client.post("/api/audits", files={"export": ("e.zip", path.read_bytes(), "application/zip")}).json()["id"]
    for _ in range(400):
        if client.get(f"/api/audits/{id_}/progress").json()["finished"]:
            break
        time.sleep(0.05)
    res = client.get(f"/api/audits/{id_}/report")
    body = res.json()
    shown = {r["recipe_id"] for r in body["report"]["recipes"] if r["level"] or r["not_sure"]}
    assert ("R3" in body["next_steps"]) == ("R3" in shown)
    assert set(body["caller_knows"]) <= set(CALLER_LINES.values())
    assert body["caller_knows"]  # the high persona names family and a college
    assert "Mahindra" not in " ".join(body["caller_knows"]) and "Amma" not in " ".join(body["caller_knows"])
