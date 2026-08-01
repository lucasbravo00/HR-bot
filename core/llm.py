"""Fachada de proveedores de LLM.

La UI pide un proveedor por nombre y trabaja contra la interfaz común
(`LLMProvider`); los detalles de cada motor viven en `core/providers/`.
"""

from .providers.base import LLMError, LLMProvider
from .providers.claude import ClaudeProvider
from .providers.ollama import DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL
from .providers.ollama import OllamaProvider

__all__ = ["LLMError", "LLMProvider", "OLLAMA_DEFAULT_MODEL", "get_provider"]


def get_provider(name: str = "claude", ollama_model: str = OLLAMA_DEFAULT_MODEL) -> LLMProvider:
    if name == "claude":
        return ClaudeProvider()
    if name == "ollama":
        return OllamaProvider(model=ollama_model)
    raise ValueError(f"Proveedor desconocido: {name}")
