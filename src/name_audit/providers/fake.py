"""A scripted provider for tests and dry runs. It never touches the network."""

import json
from collections.abc import Callable
from typing import Any

from .base import Completion, ProviderError

Reply = str | Exception


class FakeProvider:
    def __init__(
        self,
        name: str = "fake",
        model: str = "fake-model",
        reply: Callable[[str, str], Reply] | None = None,
        returned_model: str | None = None,
    ):
        self.name = name
        self.model = model
        self.returned_model = returned_model or f"{model}-2026-11-01"
        self._reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> Completion:
        self.calls.append((system, user))
        reply = self._reply(system, user) if self._reply else default_reply(user, schema)
        if isinstance(reply, Exception):
            raise ProviderError(str(reply)) from reply
        return Completion(
            text=reply,
            model=self.returned_model,
            input_tokens=len(system.split()) + len(user.split()),
            output_tokens=len(reply.split()),
            raw={"output_text": reply, "model": self.returned_model},
        )

    def list_models(self) -> list[str]:
        return [self.model]


def default_reply(user: str, schema: dict[str, Any]) -> str:
    """A deterministic reply from the text so dry runs exercise every code path."""
    score = sum(map(ord, user)) % 101
    if "probability" in schema["schema"]["properties"]:
        return json.dumps({"probability": score, "reason": "Scripted reply."})
    decision = "ADVANCE" if score >= 60 else "REJECT"
    return json.dumps({"score": score, "decision": decision, "reason": "Scripted reply."})
