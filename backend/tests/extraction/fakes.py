"""Test doubles implementing the ExtractionProvider Protocol structurally (Req 13.1).

Because ``ExtractionProvider`` is a ``typing.Protocol``, these fakes need no base
class — structural typing is enough. They let the whole extraction pipeline run
with no real AI API call (Req 13.1).
"""


class FakeProvider:
    """Returns a fixed payload for any input text."""

    def __init__(self, payload):
        self._payload = payload

    def extract(self, text: str):
        return self._payload


class SpyProvider:
    """Records whether/what it was called with, and returns a payload.

    Used to assert the service does NOT call the provider on empty/whitespace
    input (Req 1.2, 1.3, 14.1).
    """

    def __init__(self, payload: dict | None = None):
        self.called = False
        self.calls: list[str] = []
        self._payload = payload or {}

    def extract(self, text: str) -> dict:
        self.called = True
        self.calls.append(text)
        return self._payload


class RaisingProvider:
    """Raises a given (typed) exception when ``extract`` is called.

    Used to assert the service lets typed provider/timeout errors propagate
    unchanged (Req 14.2, 14.3).
    """

    def __init__(self, exc: Exception):
        self._exc = exc

    def extract(self, text: str) -> dict:
        raise self._exc


def valid_raw_payload() -> dict:
    """Return a fresh, fully valid nine-field RawExtraction payload.

    Every field is ``present`` with a simple value; list-valued fields
    (inputs, acceptance_criteria, constraints, dependencies) carry lists.
    ``contradictions`` starts empty. Consistent with the schema shape used in
    ``test_schema.py`` so tests can build valid handoffs and mutate one thing.
    """
    return {
        "objective": {"value": "Fix the login bug", "condition": "present"},
        "owner": {"value": "Alice", "condition": "present"},
        "inputs": {"value": ["repo access", "staging creds"], "condition": "present"},
        "expected_output": {"value": "A working login", "condition": "present"},
        "deadline": {"value": "Friday", "condition": "present"},
        "acceptance_criteria": {"value": ["users can log in"], "condition": "present"},
        "context": {"value": "Users are locked out", "condition": "present"},
        "constraints": {"value": ["no downtime"], "condition": "present"},
        "dependencies": {"value": ["auth service"], "condition": "present"},
        "contradictions": [],
    }
