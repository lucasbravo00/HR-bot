"""Common contract for LLM providers.

Providers expose a single primitive — a schema-constrained completion — and know
nothing about recruiting. All domain logic (which prompt, which schema) lives in
`core/tasks.py`, so adding a feature never means touching an engine.

Provider-internal errors are translated into `LLMError` with a user-facing message.
"""

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """LLM provider error carrying a user-facing message."""


class LLMProvider(Protocol):
    name: str

    def complete(
        self,
        instructions: str,
        user_text: str,
        schema: type[T],
        context: str | None = None,
        pdf: bytes | None = None,
    ) -> T:
        """Run one schema-constrained completion.

        `instructions` is the task's system prompt. `context` is the bulky, reusable
        part of the prompt (job description + rubric) that providers may cache.
        `pdf`, when given, carries the document the task is about.
        """
        ...
