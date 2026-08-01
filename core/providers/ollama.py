"""Proveedor Ollama: modelos open source corriendo en tu máquina (Llama 3.1, etc.).

Los CVs nunca salen de tu computadora — argumento fuerte de privacidad para datos
sensibles como CVs. Trade-offs frente a Claude: hay que extraer el texto de los PDFs
localmente (sin lectura nativa de documentos), y la salida estructurada depende del
decoding restringido de Ollama (`format` = JSON Schema) más una validación Pydantic
con reintento.
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

# Los CVs + rúbrica no entran en el num_ctx default de Ollama (4096).
NUM_CTX = 16384
TIMEOUT_S = 600


def _pdf_to_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if not text.strip():
        raise LLMError(
            "El PDF no contiene texto extraíble (¿es un escaneo/imagen?). "
            "Con Ollama solo se pueden evaluar PDFs con texto; probá con el motor Claude, "
            "que lee documentos de forma nativa."
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
        for _ in range(2):  # un reintento si el modelo devuelve JSON inválido
            try:
                r = requests.post(f"{self.host}/api/chat", json=payload, timeout=TIMEOUT_S)
            except requests.exceptions.ConnectionError:
                raise LLMError(
                    f"No se pudo conectar con Ollama en {self.host}. "
                    "¿Está corriendo? Iniciálo con `ollama serve` (o abriendo la app de Ollama)."
                )
            except requests.exceptions.Timeout:
                raise LLMError(
                    f"Ollama tardó más de {TIMEOUT_S}s en responder. "
                    "Probá con un modelo más chico o revisá la carga de tu máquina."
                )

            if r.status_code == 404:
                raise LLMError(
                    f"El modelo `{self.model}` no está descargado en Ollama. "
                    f"Descargalo con: `ollama pull {self.model}`"
                )
            if r.status_code != 200:
                raise LLMError(f"Error de Ollama ({r.status_code}): {r.text[:300]}")

            content = r.json().get("message", {}).get("content", "")
            try:
                return schema.model_validate_json(content)
            except (ValidationError, json.JSONDecodeError) as e:
                last_error = e
                continue

        raise LLMError(
            f"El modelo `{self.model}` no devolvió una respuesta válida contra el esquema "
            f"tras dos intentos. Detalle: {str(last_error)[:300]}. "
            "Los modelos locales chicos a veces fallan acá; probá con uno más grande "
            "(ej. `llama3.1:70b`) o con el motor Claude."
        )

    def extract_rubric(self, jd_text: str) -> Rubric:
        rubric = self._chat(
            RUBRIC_SYSTEM,
            f"Descripción del puesto:\n\n{jd_text}",
            Rubric,
        )
        if not rubric.competencies:
            raise LLMError(
                f"El modelo `{self.model}` devolvió una rúbrica vacía. "
                "Probá de nuevo o usá un modelo más grande."
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
        user = f"CV (archivo: {filename}):\n\n{cv_text}\n\nEvaluá este CV contra la rúbrica."
        return self._chat(system, user, CandidateEvaluation)
