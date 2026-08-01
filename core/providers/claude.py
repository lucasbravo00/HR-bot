"""Claude provider (Anthropic API).

Uses structured outputs (`messages.parse` + Pydantic), native PDF ingestion via
`document` blocks, and prompt caching on the per-job shared context.
"""

import base64
from contextlib import contextmanager

import anthropic

from ..models import CandidateEvaluation, Rubric
from ..prompts import EVAL_INSTRUCTIONS, RUBRIC_SYSTEM, job_context
from .base import LLMError

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


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str = MODEL):
        self.model = model

    def _client(self) -> anthropic.Anthropic:
        # Lazy instantiation: the app can boot without credentials configured.
        return anthropic.Anthropic()

    def extract_rubric(self, jd_text: str) -> Rubric:
        with _translate_errors():
            response = self._client().messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=RUBRIC_SYSTEM,
                messages=[{"role": "user", "content": f"Job description:\n\n{jd_text}"}],
                output_format=Rubric,
            )
        return response.parsed_output

    def evaluate_cv(
        self,
        jd_text: str,
        rubric: Rubric,
        filename: str,
        cv_text: str | None = None,
        cv_pdf: bytes | None = None,
    ) -> CandidateEvaluation:
        system = [
            {"type": "text", "text": EVAL_INSTRUCTIONS},
            {
                # Shared across every candidate of the same job: with cache_control
                # the prefix is cached, making subsequent evaluations faster and cheaper.
                "type": "text",
                "text": job_context(jd_text, rubric.model_dump_json(indent=2)),
                "cache_control": {"type": "ephemeral"},
            },
        ]

        if cv_pdf is not None:
            content = [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(cv_pdf).decode("utf-8"),
                    },
                },
                {"type": "text", "text": f"Evaluate this resume (file: {filename}) against the rubric."},
            ]
        else:
            content = [
                {
                    "type": "text",
                    "text": f"Resume (file: {filename}):\n\n{cv_text}\n\nEvaluate this resume against the rubric.",
                }
            ]

        with _translate_errors():
            response = self._client().messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=CandidateEvaluation,
            )
        return response.parsed_output
