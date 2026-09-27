"""End-to-end tests for the three clarification endpoints (offline, TestClient).

These endpoints operate on a supplied handoff (no extraction, no Gemini), so no
service override is needed. Handoffs are built via tests.api.fakes.make_handoff
and serialized to the inbound StructuredHandoffIn JSON shape with a small helper.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_analysis_service
from app.api.schemas import AnalyzeResponse, ApplyAnswersResponse
from app.domain import FieldCondition, HandoffFieldName, StructuredHandoff
from tests.api.fakes import make_analysis_service, make_handoff

client = TestClient(app)

CLARIFY_URL = "/api/handoff/clarify"
APPLY_URL = "/api/handoff/apply-answers"
FORMAT_URL = "/api/handoff/format"


def _handoff_to_in_json(handoff: StructuredHandoff) -> dict:
    """Serialize a domain StructuredHandoff into the inbound DTO JSON dict."""
    fields = {}
    for name in HandoffFieldName:
        f = getattr(handoff, name.value)
        fields[name.value] = {"value": f.value, "condition": f.condition.value}
    fields["contradictions"] = [[a.value, b.value] for a, b in handoff.contradictions]
    return fields


# --- /clarify -----------------------------------------------------------------


def test_clarify_not_ready_returns_questions():
    handoff = make_handoff(objective=(None, FieldCondition.MISSING))
    resp = client.post(CLARIFY_URL, json={"handoff": _handoff_to_in_json(handoff)})
    assert resp.status_code == 200
    questions = resp.json()["questions"]
    assert questions
    for q in questions:
        assert "field" in q and "text" in q and q["text"]


def test_clarify_ready_returns_empty():
    handoff = make_handoff()  # all present / ready
    resp = client.post(CLARIFY_URL, json={"handoff": _handoff_to_in_json(handoff)})
    assert resp.status_code == 200
    assert resp.json()["questions"] == []


# --- /apply-answers -----------------------------------------------------------


def test_apply_answers_answers_only():
    handoff = make_handoff(objective=(None, FieldCondition.MISSING))
    body = {
        "handoff": _handoff_to_in_json(handoff),
        "answers": [{"field": "objective", "value": "Deliver the Q1 report"}],
    }
    resp = client.post(APPLY_URL, json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["handoff"]["objective"]["value"] == "Deliver the Q1 report"
    assert data["handoff"]["objective"]["condition"] == "present"
    assert "readiness_state" in data["validation"]


def test_apply_answers_resolve_only():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    handoff = make_handoff(contradictions=[pair])
    body = {
        "handoff": _handoff_to_in_json(handoff),
        "resolve_contradictions": [["objective", "deadline"]],
    }
    resp = client.post(APPLY_URL, json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert ["objective", "deadline"] not in data["handoff"]["contradictions"]
    issue_types = [i["issue_type"] for i in data["validation"]["issues"]]
    assert "contradictory_information" not in issue_types


def test_apply_answers_both():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    handoff = make_handoff(
        objective=("vague", FieldCondition.AMBIGUOUS), contradictions=[pair]
    )
    body = {
        "handoff": _handoff_to_in_json(handoff),
        "answers": [{"field": "objective", "value": "Deliver a clear report"}],
        "resolve_contradictions": [["objective", "deadline"]],
    }
    resp = client.post(APPLY_URL, json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["handoff"]["objective"]["value"] == "Deliver a clear report"
    assert ["objective", "deadline"] not in data["handoff"]["contradictions"]


def test_apply_answers_unknown_pair_422():
    handoff = make_handoff()  # no contradictions
    body = {
        "handoff": _handoff_to_in_json(handoff),
        "resolve_contradictions": [["objective", "deadline"]],
    }
    resp = client.post(APPLY_URL, json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "contradiction_not_found"


def test_apply_answers_empty_answer_422():
    handoff = make_handoff(objective=(None, FieldCondition.MISSING))
    body = {
        "handoff": _handoff_to_in_json(handoff),
        "answers": [{"field": "objective", "value": "   "}],
    }
    resp = client.post(APPLY_URL, json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "empty_answer"


def test_apply_answers_without_resolution_keeps_contradiction():
    pair = (HandoffFieldName.OBJECTIVE, HandoffFieldName.DEADLINE)
    handoff = make_handoff(
        objective=("vague", FieldCondition.AMBIGUOUS), contradictions=[pair]
    )
    body = {
        "handoff": _handoff_to_in_json(handoff),
        "answers": [{"field": "objective", "value": "A concrete objective"}],
        # no resolve_contradictions
    }
    resp = client.post(APPLY_URL, json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert ["objective", "deadline"] in data["handoff"]["contradictions"]


# --- /format ------------------------------------------------------------------


def test_format_not_ready_has_marker_and_header():
    handoff = make_handoff(objective=(None, FieldCondition.MISSING))
    resp = client.post(FORMAT_URL, json={"handoff": _handoff_to_in_json(handoff)})
    assert resp.status_code == 200
    text = resp.json()["text"]
    assert "⚠ MISSING" in text
    assert "Readiness:" in text


def test_format_ready_has_values():
    handoff = make_handoff()
    resp = client.post(FORMAT_URL, json={"handoff": _handoff_to_in_json(handoff)})
    assert resp.status_code == 200
    text = resp.json()["text"]
    assert "Ship the quarterly report" in text


# --- Response-type + coexistence guards ---------------------------------------


def test_apply_answers_body_validates_against_dedicated_dto():
    handoff = make_handoff(objective=(None, FieldCondition.MISSING))
    body = {
        "handoff": _handoff_to_in_json(handoff),
        "answers": [{"field": "objective", "value": "the goal"}],
    }
    resp = client.post(APPLY_URL, json=body)
    parsed = ApplyAnswersResponse.model_validate(resp.json())
    assert isinstance(parsed, ApplyAnswersResponse)


def test_analyze_still_returns_its_own_shape():
    app.dependency_overrides[get_analysis_service] = lambda: make_analysis_service(
        make_handoff()
    )
    try:
        resp = client.post("/api/handoff/analyze", json={"text": "t"})
        assert resp.status_code == 200
        parsed = AnalyzeResponse.model_validate(resp.json())
        assert isinstance(parsed, AnalyzeResponse)
    finally:
        app.dependency_overrides.clear()


def test_health_still_ok():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
