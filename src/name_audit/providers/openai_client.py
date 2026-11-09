"""OpenAI Responses API client."""

from typing import Any

import openai

from ..config import REASONING
from .base import Completion, ProviderError


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, api_key: str, timeout: float = 120.0, max_retries: int = 6):
        self.model = model
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> Completion:
        try:
            response = self._client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                reasoning={"effort": REASONING["openai"]},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema["name"],
                        "schema": schema["schema"],
                        "strict": True,
                    }
                },
                store=False,
            )
        except openai.OpenAIError as exc:
            raise ProviderError(f"{type(exc).__name__}: {exc}") from exc
        usage = response.usage
        return Completion(
            text=response.output_text,
            model=response.model,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            raw=response.model_dump(mode="json"),
        )

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self._client.models.list())
