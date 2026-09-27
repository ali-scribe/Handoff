"""Protocol-conformance tests for ExtractionProvider (Req 11.1, 11.2, 11.4, 12).

ExtractionProvider is a @runtime_checkable typing.Protocol with a single
method, ``extract``. runtime_checkable checks method *name* presence (not the
signature), so these tests assert what the Protocol actually guarantees:
structural member presence plus a functional call.
"""

from app.extraction.provider import ExtractionProvider


class FakeProvider:
    """A minimal structural implementation: defines ONLY ``extract``."""

    def __init__(self, payload: dict):
        self._payload = payload

    def extract(self, text: str) -> dict:
        return self._payload


class NotAProvider:
    """A class that does NOT implement ``extract``."""

    def something_else(self) -> None:
        return None


def test_fake_with_extract_satisfies_protocol():
    fake = FakeProvider({"summary": "hi"})
    assert isinstance(fake, ExtractionProvider) is True


def test_fake_extract_returns_configured_dict():
    payload = {"summary": "done", "items": [1, 2, 3]}
    fake = FakeProvider(payload)
    result = fake.extract("some text")
    assert result == payload
    assert isinstance(result, dict)


def test_class_missing_extract_does_not_satisfy_protocol():
    assert isinstance(NotAProvider(), ExtractionProvider) is False


def test_protocol_requires_only_extract_member():
    # The abstraction is a narrow boundary: it declares the single member
    # ``extract`` and a fake defining only that member conforms.
    assert hasattr(ExtractionProvider, "extract")
    fake = FakeProvider({})
    assert isinstance(fake, ExtractionProvider) is True

    # runtime_checkable Protocols expose their members via __protocol_attrs__
    # (or fall back to dir); the only non-dunder member is ``extract``.
    members = getattr(ExtractionProvider, "__protocol_attrs__", None)
    if members is not None:
        assert members == {"extract"}


def test_extract_is_callable_with_text_and_returns_dict():
    fake = FakeProvider({"ok": True})
    result = fake.extract(text="hello world")
    assert isinstance(result, dict)
    assert result == {"ok": True}
