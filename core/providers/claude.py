"""Proveedor Claude (API de Anthropic).

Usa salidas estructuradas (`messages.parse` + Pydantic), PDFs nativos como bloque
`document` y prompt caching sobre el contexto compartido de la búsqueda.
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
        raise LLMError("Límite de uso de la API de Anthropic alcanzado. Esperá un momento y reintentá.")
    except anthropic.APIStatusError as e:
        raise LLMError(f"Error de la API de Anthropic ({e.status_code}): {e.message}")
    except anthropic.APIConnectionError:
        raise LLMError("No se pudo conectar con la API de Anthropic. Revisá tu conexión.")
    except anthropic.AnthropicError as e:
        raise LLMError(f"Error de configuración de Anthropic: {e}. ¿Está definida ANTHROPIC_API_KEY?")


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str = MODEL):
        self.model = model

    def _client(self) -> anthropic.Anthropic:
        # Instanciación diferida: la app puede arrancar sin credenciales configuradas.
        return anthropic.Anthropic()

    def extract_rubric(self, jd_text: str) -> Rubric:
        with _translate_errors():
            response = self._client().messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=RUBRIC_SYSTEM,
                messages=[{"role": "user", "content": f"Descripción del puesto:\n\n{jd_text}"}],
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
                # Bloque compartido entre todos los candidatos de una misma búsqueda:
                # con cache_control el prefijo se cachea y las evaluaciones siguientes
                # son más rápidas y baratas.
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
                {"type": "text", "text": f"Evaluá este CV (archivo: {filename}) contra la rúbrica."},
            ]
        else:
            content = [
                {
                    "type": "text",
                    "text": f"CV (archivo: {filename}):\n\n{cv_text}\n\nEvaluá este CV contra la rúbrica.",
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
