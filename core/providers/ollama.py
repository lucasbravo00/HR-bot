"""Ollama provider: open-source models running on your own machine (Llama 3.1, etc.).

Resumes never leave your computer — a strong privacy argument for data as sensitive
as CVs. Trade-offs vs. Claude: PDF text must be extracted locally (no native document
reading), and structured output relies on Ollama's constrained decoding
(`format` = JSON Schema) plus Pydantic validation with one retry.
"""

import io
import json
import os

import requests
from pydantic import BaseModel, ValidationError

from ..models import CandidateEvaluation, Rubric
from ..prompts import EVAL_INSTRUCTIONS, RUBRIC_SYSTEM, job_context
from .base import LLMError

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

# Resumes + rubric do not fit in Ollama's default num_ctx (4096).
NUM_CTX = 16384
TIMEOUT_S = 600


def _pdf_to_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise LLMError(
            "The PDF contains no extractable text (is it a scan/image?). "
            "Ollama can only evaluate PDFs with embedded text; try the Claude engine, "
            "which reads documents natively."
        )
    return text


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST):
        self.model = model
        self.host = host.rstrip("/")

    def _chat(self, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
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

    def extract_rubric(self, jd_text: str) -> Rubric:
        rubric = self._chat(
            RUBRIC_SYSTEM,
            f"Job description:\n\n{jd_text}",
            Rubric,
        )
        if not rubric.competencies:
            raise LLMError(
                f"Model `{self.model}` returned an empty rubric. "
                "Try again or use a larger model."
            )
        return rubric

    def evaluate_cv(
        self,
        jd_text: str,
        rubric: Rubric,
        filename: str,
        cv_text: str | None = None,
        cv_pdf: bytes | None = None,
    ) -> CandidateEvaluation:
        if cv_pdf is not None:
            cv_text = _pdf_to_text(cv_pdf)

        system = f"{EVAL_INSTRUCTIONS}\n\n{job_context(jd_text, rubric.model_dump_json(indent=2))}"
        user = f"Resume (file: {filename}):\n\n{cv_text}\n\nEvaluate this resume against the rubric."
        return self._chat(system, user, CandidateEvaluation)
