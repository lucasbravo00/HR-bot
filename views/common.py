"""Shared UI pieces across copilot modules."""

import streamlit as st

from core.llm import OLLAMA_DEFAULT_MODEL, LLMProvider, get_provider

ENGINE_LABELS = {
    "Claude (Anthropic)": "claude",
    "Ollama (local, open source)": "ollama",
}


def render_engine_picker() -> LLMProvider:
    """Engine selection, shared by every module."""
    st.divider()
    engine_label = st.selectbox("AI engine", list(ENGINE_LABELS), key="engine")

    if ENGINE_LABELS[engine_label] == "ollama":
        model = st.text_input("Ollama model", value=OLLAMA_DEFAULT_MODEL, key="ollama_model")
        model = model or OLLAMA_DEFAULT_MODEL
        st.caption(
            "Nothing leaves your machine 🔒. Requires [Ollama](https://ollama.com) running "
            f"and the model downloaded (`ollama pull {model}`). "
            "Small local models are less accurate at judging evidence than Claude."
        )
        return get_provider("ollama", ollama_model=model)

    st.caption("Requires `ANTHROPIC_API_KEY`. Best quality and native PDF reading.")
    return get_provider("claude")


def bullet_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
