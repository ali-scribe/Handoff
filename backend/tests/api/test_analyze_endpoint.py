"""End-to-end tests for POST /api/handoff/analyze.

These use TestClient(app) and override get_analysis_service with a REAL
AnalysisService whose extraction is faked (so the genuine validate_handoff runs
offline). They cover success serialization, request validation (422 handled by
FastAPI), every extraction-failure -> status/code mapping, secret non-leakage,
and architecture guards (route delegates to the service and does not duplicate
the validator).
"""

import inspect

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_analysis_service
from app.application.analysis import AnalysisService
from app.domain import FieldCondition, HandoffFieldName
from app.extraction import (
    EmptyInputError,
    ExtractionError,
    MalformedResponseError,
    MissingApiKeyError,
    ProviderFailureError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SchemaValidationError,
    UnexpectedResponseError,
)
from tests.api.fakes import (
    FakeExtractionService,
    make_analysis_service,
    make_handoff,
    make_raising_analysis_service,
)

client = TestClient(app)

ANALYZE_URL = "/api/handoff/analyze"


@pytest.fixture(autouse=True)
def _default_override():
    """Provide a safe default service override and clear it after each test.

    In this Starlette/FastAPI build the endpoint's dependency is resolved as
    part of request handling even when body validation fails, so the production
    factory (which builds a real GeminiProvider and needs an API key) must never
    run in tests. We install a harmless in-memory AnalysisService by default so
    every test stays offline; request-validation tests still get their 422 from
    FastAPI, and failure-mapping tests replace this with a raising service.
    """
    app.dependency_overrides[get_analysis_service] = lambda: make_analysis_service(
        make_handoff()
    )
    yield
    app.dependency_overrides.clear()


def _override(service: AnalysisService) -> None:
    app.dependency_overrides[get_analysis_service] = lambda: service


# --- Success cases ----------------------------------------------------------


def test_valid_request_returns_200_with_handoff_and_validation():
    _override(make_analysis_service(make_handoff()))
    response = client.post(ANALYZE_URL, json={"text": "some handoff text"})
    assert response.status_code == 200
    body = response.json()
    assert "handoff" in body
    assert "validation" in body


def test_structured_handoff_nine_fields_serialize():
    handoff = make_handoff(
        owner=(None, FieldCondition.MISSING),  # None value
        inputs=(["a", "b", "c"], FieldCondition.PRESENT),  # list value
    )
    _override(make_analysis_service(handoff))
    body = client.post(ANALYZE_URL, json={"text": "t"}).json()
    h = body["handoff"]

    for name in [
        "objective",
        "owner",
        "inputs",
        "expected_output",
        "deadline",
        "acceptance_criteria",
        "context",
        "constraints",
        "dependencies",
    ]:
        assert name in h
        assert "value" in h[name]
        assert "condition" in h[name]

    # None value preserved
    assert h["owner"]["value"] is None
    assert h["owner"]["condition"] == "missing"
    # list value serialized as a JSON array
    assert h["inputs"]["value"] == ["a", "b", "c"]
    assert h["inputs"]["condition"] == "present"


def test_all_field_conditions_serialize():
    handoff = make_handoff(
        objective=("Do the thing", FieldCondition.PRESENT),
        owner=(None, FieldCondition.MISSING),
        deadline=("soon-ish", FieldCondition.AMBIGUOUS),
        constraints=(None, FieldCondition.NOT_APPLICABLE),
    )
    _override(make_analysis_service(handoff))
    h = client.post(ANALYZE_URL, json={"text": "t"}).json()["handoff"]
    conditions = {h[name]["condition"] for name in h if name != "contradictions"}
    assert {"present", "missing", "ambiguous", "not_applicable"} <= conditions


def test_contradictions_serialize_as_list_of_pairs():
    handoff = make_handoff(
        contradictions=[
            (HandoffFieldName.DEADLINE, HandoffFieldName.DEPENDENCIES),
            (HandoffFieldName.OBJECTIVE, HandoffFieldName.OWNER),
        ]
    )
    _override(make_analysis_service(handoff))
    h = client.post(ANALYZE_URL, json={"text": "t"}).json()["handoff"]
    assert h["contradictions"] == [
        ["deadline", "dependencies"],
        ["objective", "owner"],
    ]


def test_issues_serialize_with_expected_shape():
    # Missing objective -> real validator produces a missing_objective issue.
    handoff = make_handoff(objective=(None, FieldCondition.MISSING))
    _override(make_analysis_service(handoff))
    validation = client.post(ANALYZE_URL, json={"text": "t"}).json()["validation"]
    assert validation["issues"], "expected at least one issue"
    issue = validation["issues"][0]
    for key in ("issue_type", "severity", "field", "explanation"):
        assert key in issue
    assert issue["issue_type"] == "missing_objective"
    assert issue["severity"] == "critical"
    assert issue["field"] == "objective"
    assert isinstance(issue["explanation"], str) and issue["explanation"]


# --- Readiness states (through the REAL validator) --------------------------


def test_readiness_ready():
    _override(make_analysis_service(make_handoff()))
    validation = client.post(ANALYZE_URL, json={"text": "t"}).json()["validation"]
    assert validation["readiness_state"] == "ready"


def test_readiness_needs_clarification():
    # Ambiguous deadline -> IMPORTANT vague_deadline, no CRITICAL.
    handoff = make_handoff(deadline=("sometime soon", FieldCondition.AMBIGUOUS))
    _override(make_analysis_service(handoff))
    validation = client.post(ANALYZE_URL, json={"text": "t"}).json()["validation"]
    assert validation["readiness_state"] == "needs_clarification"


def test_readiness_not_ready():
    # Missing objective -> CRITICAL -> NOT_READY.
    handoff = make_handoff(objective=(None, FieldCondition.MISSING))
    _override(make_analysis_service(handoff))
    validation = client.post(ANALYZE_URL, json={"text": "t"}).json()["validation"]
    assert validation["readiness_state"] == "not_ready"


# --- Request validation (handled by FastAPI, no service needed) -------------


def test_missing_body_returns_422():
    response = client.post(ANALYZE_URL)
    assert response.status_code == 422


def test_malformed_json_returns_422():
    response = client.post(
        ANALYZE_URL,
        content="{ not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code in (400, 422)


def test_missing_text_field_returns_422():
    response = client.post(ANALYZE_URL, json={})
    assert response.status_code == 422


def test_wrong_text_type_returns_422():
    response = client.post(ANALYZE_URL, json={"text": 123})
    assert response.status_code == 422


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_text_reaches_service_and_maps_empty_input(blank):
    # Blank strings pass request validation (they are strings) and reach the
    # service; a fake that mimics the real ExtractionService raises
    # EmptyInputError, which maps to 422 empty_input.
    _override(make_raising_analysis_service(EmptyInputError("empty")))
    response = client.post(ANALYZE_URL, json={"text": blank})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_input"


# --- Extraction failure mapping ---------------------------------------------

FAILURE_CASES = [
    (EmptyInputError("x"), 422, "empty_input"),
    (ProviderFailureError("x"), 502, "provider_failure"),
    (ProviderTimeoutError("x"), 504, "provider_timeout"),
    (ProviderUnavailableError("x"), 503, "provider_unavailable"),
    (MalformedResponseError("x"), 502, "malformed_ai_response"),
    (SchemaValidationError("x"), 502, "schema_validation_failed"),
    (UnexpectedResponseError("x"), 502, "unexpected_ai_response"),
    (ExtractionError("x"), 502, "extraction_error"),
]


@pytest.mark.parametrize("exc,status,code", FAILURE_CASES)
def test_extraction_failures_map_to_status_and_code(exc, status, code):
    _override(make_raising_analysis_service(exc))
    response = client.post(ANALYZE_URL, json={"text": "t"})
    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_missing_api_key_maps_to_500_and_hides_secret():
    secret = "SECRET_KEY_zzz999"
    _override(make_raising_analysis_service(MissingApiKeyError(secret)))
    response = client.post(ANALYZE_URL, json={"text": "t"})
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "server_configuration_error"
    assert secret not in response.text


# --- Architecture checks ----------------------------------------------------


def test_endpoint_delegates_to_analysis_service_with_request_text():
    fake_extraction = FakeExtractionService(handoff=make_handoff())
    service = AnalysisService(fake_extraction)
    _override(service)
    client.post(ANALYZE_URL, json={"text": "the exact text"})
    assert fake_extraction.received_text == "the exact text"


def test_route_module_does_not_duplicate_validator():
    source = inspect.getsource(__import__("app.api.analyze", fromlist=["x"]))
    assert "validate_handoff" not in source
    assert "ReadinessState" not in source


def test_health_endpoint_still_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
