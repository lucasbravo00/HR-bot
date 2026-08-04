"""Claude provider (Anthropic API).

Uses structured outputs (`messages.parse` + Pydantic), native PDF ingestion via
`document` blocks, and prompt caching on the reusable context block.
"""

import base64
from contextlib import contextmanager

import anthropic

from .base import LLMError, T

MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000


@contextmanager
def _translate_errors():
    try:
        yield
    except anthropic.RateLimitError:
        raise LLMError("Anthropic API rate limit reached. Wait a moment and retry.")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise LLMError("Could not reach the Anthropic API. Check your connection.")
    except anthropic.AnthropicError as e:
        raise LLMError(f"Anthropic configuration error: {e}. Is ANTHROPIC_API_KEY set?")
    except TypeError as e:
        # The SDK raises a bare TypeError (not an AnthropicError subclass) when it
        # can't resolve any credentials (no API key, auth token, or active profile).
        if "authentication" in str(e).lower():
            raise LLMError(
                "No Anthropic credentials found. Set the ANTHROPIC_API_KEY environment "
                "variable, authenticate with `ant auth login`, or switch to the Ollama "
                "engine in the sidebar."
            )
        raise


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str = MODEL):
        self.model = model

    def _client(self) -> anthropic.Anthropic:
        # Lazy instantiation: the app can boot without credentials configured.
        return anthropic.Anthropic()

    def complete(
        self,
        instructions: str,
        user_text: str,
        schema: type[T],
        context: str | None = None,
        pdf: bytes | None = None,
    ) -> T:
        system = [{"type": "text", "text": instructions}]
        if context:
            # Shared across every candidate of the same job: with cache_control the
            # prefix is cached, making subsequent calls faster and cheaper.
            system.append(
                {"type": "text", "text": context, "cache_control": {"type": "ephemeral"}}
            )

        content = []
        if pdf is not None:
            content.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(pdf).decode("utf-8"),
                    },
                }
            )
        content.append({"type": "text", "text": user_text})

        with _translate_errors():
            response = self._client().messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
            )
        return response.parsed_output
