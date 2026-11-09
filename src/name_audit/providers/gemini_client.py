"""Google Gemini API client."""

from typing import Any

from google import genai
from google.genai import errors, types

from .base import Completion, ProviderError

RETRY_STATUS = [408, 429, 500, 502, 503, 504]


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str, timeout: float = 120.0, attempts: int = 7):
        self.model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=attempts, http_status_codes=RETRY_STATUS
                ),
            ),
        )

    def complete(self, system: str, user: str, schema: dict[str, Any]) -> Completion:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema["schema"],
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
        )
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=user, config=config
            )
        except errors.APIError as exc:
            raise ProviderError(f"{type(exc).__name__}: {exc}") from exc
        usage = response.usage_metadata
        output_tokens = 0
        input_tokens = 0
        if usage:
            input_tokens = usage.prompt_token_count or 0
            output_tokens = (usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)
        return Completion(
            text=response.text or "",
            model=response.model_version or "",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw=response.model_dump(mode="json", exclude={"sdk_http_response"}),
        )

    def list_models(self) -> list[str]:
        return sorted((m.name or "").removeprefix("models/") for m in self._client.models.list())
