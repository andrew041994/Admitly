import pytest

from app.services import tickets
from app.services.tickets import InvalidManualCodeError, normalize_manual_code


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ADM - 123456", "ADM-123456"),
        ("ADM-123456", "ADM-123456"),
        ("adm123456", "ADM-123456"),
        ("123456", "ADM-123456"),
    ],
)
def test_normalize_manual_code_accepts_supported_forms(raw, expected):
    assert normalize_manual_code(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "1234567", "ADM-ABC123", "ADM_123456", "ADM-12345A"])
def test_normalize_manual_code_rejects_invalid_values(raw):
    with pytest.raises(InvalidManualCodeError):
        normalize_manual_code(raw)


def test_generate_manual_code_preserves_leading_zeros(monkeypatch):
    monkeypatch.setattr(tickets.secrets, "randbelow", lambda upper: 4829)
    assert tickets._generate_manual_code() == "ADM-004829"


def test_generate_manual_code_uses_six_digits(monkeypatch):
    monkeypatch.setattr(tickets.secrets, "randbelow", lambda upper: 482913)
    code = tickets._generate_manual_code()
    assert code == "ADM-482913"
    assert code.removeprefix("ADM-").isdigit()
    assert len(code.removeprefix("ADM-")) == 6


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, existing_results):
        self.existing_results = list(existing_results)
        self.calls = 0

    def execute(self, statement):
        self.calls += 1
        return _Scalar(self.existing_results.pop(0))


def test_issue_manual_code_retries_on_collision(monkeypatch):
    generated = iter([111111, 222222])
    monkeypatch.setattr(tickets.secrets, "randbelow", lambda upper: next(generated))
    db = _FakeDb([1, None])

    assert tickets._issue_manual_code(db, event_id=10) == "ADM-222222"
    assert db.calls == 2


def test_issue_manual_code_fails_after_retries(monkeypatch):
    monkeypatch.setattr(tickets.secrets, "randbelow", lambda upper: 123456)
    db = _FakeDb([1] * 10)

    with pytest.raises(tickets.TicketIssuanceError):
        tickets._issue_manual_code(db, event_id=10)
    assert db.calls == 10
