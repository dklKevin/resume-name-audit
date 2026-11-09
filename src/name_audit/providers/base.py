"""Common interface for model providers."""

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """The provider failed to return a reply after its own transport retries."""


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    raw: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> Completion:
        """Send one system and one user message; return the reply text and usage."""
        ...

    def list_models(self) -> list[str]:
        """Model ids visible to this key (a free metadata call)."""
        ...
