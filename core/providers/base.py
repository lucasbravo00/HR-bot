"""Common contract for LLM providers.

Any engine (cloud API or local model) must implement these two operations and
return the same Pydantic models. Provider-internal errors are translated into
`LLMError` with a message fit for the UI.
"""

from typing import Protocol

from ..models import CandidateEvaluation, Rubric


class LLMError(RuntimeError):
    """LLM provider error carrying a user-facing message."""


class LLMProvider(Protocol):
    name: str

    def extract_rubric(self, jd_text: str) -> Rubric: ...

    def evaluate_cv(
        self,
        jd_text: str,
        rubric: Rubric,
        filename: str,
        cv_text: str | None = None,
        cv_pdf: bytes | None = None,
    ) -> CandidateEvaluation: ...
