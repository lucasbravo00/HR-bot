"""Ollama provider: open-source models running on your own machine (Llama 3.1, etc.).

Resumes never leave your computer — a strong privacy argument for data as sensitive
as CVs. Trade-offs vs. Claude: PDF text is extracted locally (no native document
reading), and structured output relies on Ollama's constrained decoding
(`format` = JSON Schema) plus Pydantic validation with one retry.
"""

import json
import os

import requests
from pydantic import ValidationError

from .base import LLMError, T

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

# Resumes + rubric do not fit in Ollama's default num_ctx (4096).
NUM_CTX = 16384
TIMEOUT_S = 600


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST):
        self.model = model
        self.host = host.rstrip("/")

    def complete(
        self,
        instructions: str,
        user_text: str,
        schema: type[T],
        context: str | None = None,
        pdf: bytes | None = None,
    ) -> T:
        if pdf is not None:
            from ..pdf import pdf_to_text

            user_text = f"{pdf_to_text(pdf)}\n\n{user_text}"

        system = f"{instructions}\n\n{context}" if context else instructions
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_text},
            ],
            "format": schema.model_json_schema(),
            "stream": False,
            "options": {"num_ctx": NUM_CTX},
        }

        last_error = None
        for _ in range(2):  # one retry if the model returns invalid JSON
            try:
                r = requests.post(f"{self.host}/api/chat", json=payload, timeout=TIMEOUT_S)
            except requests.exceptions.ConnectionError:
                raise LLMError(
                    f"Could not connect to Ollama at {self.host}. "
                    "Is it running? Start it with `ollama serve` (or by opening the Ollama app)."
                )
            except requests.exceptions.Timeout:
                raise LLMError(
                    f"Ollama took longer than {TIMEOUT_S}s to respond. "
                    "Try a smaller model or check your machine's load."
                )

            if r.status_code == 404:
                raise LLMError(
                    f"Model `{self.model}` is not available in Ollama. "
                    f"Download it with: `ollama pull {self.model}`"
                )
            if r.status_code != 200:
                raise LLMError(f"Ollama error ({r.status_code}): {r.text[:300]}")

            content = r.json().get("message", {}).get("content", "")
            try:
                return schema.model_validate_json(content)
            except (ValidationError, json.JSONDecodeError) as e:
                last_error = e
                continue

        raise LLMError(
            f"Model `{self.model}` failed to produce a schema-valid response after two "
            f"attempts. Detail: {str(last_error)[:300]}. "
            "Small local models sometimes fail here; try a larger one "
            "(e.g. `llama3.1:70b`) or the Claude engine."
        )
