"""Strict parsing and validation of model replies."""

import json


class ParseError(ValueError):
    pass


def _load_object(text: str) -> dict:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            body = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ParseError(f"not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ParseError("reply is not a JSON object")
    return value


def _int_in_range(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ParseError(f"{field} is not an integer")
    if not 0 <= value <= 100:
        raise ParseError(f"{field} is outside 0 to 100")
    return value


def _reason(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParseError("reason is missing or empty")
    return value.strip()


def parse_screening(text: str) -> tuple[int, str, str]:
    """Return (score, decision, reason) or raise ParseError."""
    obj = _load_object(text)
    if set(obj) != {"score", "decision", "reason"}:
        raise ParseError(f"unexpected keys: {sorted(obj)}")
    score = _int_in_range(obj["score"], "score")
    if obj["decision"] not in ("ADVANCE", "REJECT"):
        raise ParseError("decision is not ADVANCE or REJECT")
    return score, obj["decision"], _reason(obj["reason"])


def parse_probe(text: str) -> tuple[int, str]:
    """Return (probability, reason) or raise ParseError."""
    obj = _load_object(text)
    if set(obj) != {"probability", "reason"}:
        raise ParseError(f"unexpected keys: {sorted(obj)}")
    return _int_in_range(obj["probability"], "probability"), _reason(obj["reason"])
