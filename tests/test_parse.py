import pytest

from name_audit.parse import ParseError, parse_probe, parse_screening


def test_valid_reply():
    assert parse_screening('{"score": 72, "decision": "ADVANCE", "reason": "Strong SQL."}') == (
        72,
        "ADVANCE",
        "Strong SQL.",
    )


def test_code_fence_is_unwrapped():
    text = '```json\n{"score": 10, "decision": "REJECT", "reason": "No SQL."}\n```'
    assert parse_screening(text) == (10, "REJECT", "No SQL.")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[1, 2]",
        '{"score": 72, "decision": "ADVANCE"}',
        '{"score": 72, "decision": "ADVANCE", "reason": "x", "extra": 1}',
        '{"score": 101, "decision": "ADVANCE", "reason": "x"}',
        '{"score": -1, "decision": "REJECT", "reason": "x"}',
        '{"score": 72.5, "decision": "ADVANCE", "reason": "x"}',
        '{"score": "72", "decision": "ADVANCE", "reason": "x"}',
        '{"score": true, "decision": "ADVANCE", "reason": "x"}',
        '{"score": 72, "decision": "advance", "reason": "x"}',
        '{"score": 72, "decision": "MAYBE", "reason": "x"}',
        '{"score": 72, "decision": "ADVANCE", "reason": "  "}',
        'Sure! {"score": 72, "decision": "ADVANCE", "reason": "x"}',
    ],
)
def test_invalid_replies(text):
    with pytest.raises(ParseError):
        parse_screening(text)


def test_probe_reply():
    assert parse_probe('{"probability": 35, "reason": "Looks routine."}') == (35, "Looks routine.")
    with pytest.raises(ParseError):
        parse_probe('{"probability": 150, "reason": "x"}')
