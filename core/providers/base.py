"""Contrato común para proveedores de LLM.

Cualquier motor (API en la nube o modelo local) debe implementar estas dos
operaciones devolviendo los mismos modelos Pydantic. Los errores internos de cada
proveedor se traducen a `LLMError` con un mensaje apto para mostrar en la UI.
"""

from typing import Protocol

from ..models import CandidateEvaluation, Rubric


class LLMError(RuntimeError):
    """Error de un proveedor de LLM, con mensaje legible para el usuario final."""


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
