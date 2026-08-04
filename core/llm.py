"""LLM provider facade.

The UI requests a provider by name and passes it to the tasks in `core/tasks.py`;
engine-specific details live in `core/providers/`.
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
    raise ValueError(f"Unknown provider: {name}")
