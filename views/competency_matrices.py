"""Competency matrix builder: competencies by seniority level, for calibration and growth."""

import pandas as pd
import streamlit as st

from core import db
from core.llm import LLMError, LLMProvider
from core.models import CompetencyMatrix
from core.tasks import generate_competency_matrix

KIND = "competency_matrix"
NEW_MATRIX_OPTION = "➕ New matrix"
DEFAULT_LEVELS = "Junior, Semi-Senior, Senior, Lead"
MAX_LEVELS = 6


def _parse_levels(raw: str) -> list[str]:
    seen, levels = set(), []
    for part in raw.split(","):
        level = part.strip()
        if level and level.casefold() not in seen:
            seen.add(level.casefold())
            levels.append(level)
    return levels[:MAX_LEVELS]


def _as_dataframe(matrix: CompetencyMatrix) -> pd.DataFrame:
    rows = {}
    for comp in matrix.competencies:
        by_level = {le.level: le.behavioral_indicator for le in comp.levels}
        rows[comp.name] = {level: by_level.get(level, "—") for level in matrix.levels}
    return pd.DataFrame.from_dict(rows, orient="index")


def render_form(provider: LLMProvider) -> None:
    st.header("New competency matrix")
    st.markdown(
        "Describe the role family. The AI drafts competencies by level with **observable "
        "behavior** for each — the levels have to differ in scope, autonomy and complexity, "
        "not just say the same thing with stronger adjectives."
    )

    jobs = db.list_jobs()
    if jobs:
        job_labels = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs}
        col1, col2 = st.columns([3, 1])
        with col1:
            source = st.selectbox("Start from an existing job (optional)", list(job_labels), key="cm_source")
        with col2:
            st.write("")
            if st.button("📋 Load"):
                job = db.get_job(job_labels[source])
                if job:
                    st.session_state["pending_cm_role"] = job["jd_text"]
                    st.rerun()

    role_description = st.text_area(
        "Role family / role description",
        height=200,
        placeholder="Customer Success at a B2B SaaS company: owns retention, adoption and expansion…",
        key="cm_role",
    )
    levels_raw = st.text_input(
        "Seniority levels, in order",
        value=DEFAULT_LEVELS,
        help=f"Comma-separated, from most junior to most senior (max {MAX_LEVELS}).",
        key="cm_levels",
    )
    levels = _parse_levels(levels_raw)
    if levels:
        st.caption("Levels: " + " → ".join(levels))

    ready = bool(role_description.strip()) and len(levels) >= 2
    if st.button("✨ Build matrix", type="primary", disabled=not ready):
        try:
            with st.spinner("Building the matrix…"):
                matrix = generate_competency_matrix(provider, role_description, levels)
        except LLMError as e:
            st.error(str(e))
            return
        doc_id = db.save_document(KIND, matrix.role_family, matrix.model_dump_json())
        st.session_state["pending_cm_choice"] = f"{matrix.role_family} (#{doc_id})"
        st.rerun()

    if not ready:
        st.caption("A role description and at least two levels are required.")


def render_matrix(doc) -> None:
    matrix = CompetencyMatrix.model_validate_json(doc["payload_json"])

    st.header(matrix.role_family)
    st.caption("Levels: " + " → ".join(matrix.levels))

    df = _as_dataframe(matrix)
    st.dataframe(df, width="stretch")

    st.subheader("Competencies in detail")
    for comp in matrix.competencies:
        with st.expander(f"{comp.name}  ·  {comp.category}"):
            st.caption(comp.definition)
            for le in comp.levels:
                st.markdown(f"**{le.level}** — {le.behavioral_indicator}")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "⬇️ Download CSV",
            data=df.to_csv().encode("utf-8"),
            file_name=f"{matrix.role_family.lower().replace(' ', '_')}_matrix.csv",
            mime="text/csv",
        )
    with col2:
        if st.button("🗑️ Delete matrix"):
            db.delete_document(doc["id"])
            st.session_state["pending_cm_choice"] = NEW_MATRIX_OPTION
            st.rerun()


def render(provider: LLMProvider, sidebar) -> None:
    docs = db.list_documents(KIND)
    labels = {f"{d['title']} (#{d['id']})": d["id"] for d in docs}

    with sidebar:
        choice = st.radio("Matrices", [NEW_MATRIX_OPTION] + list(labels), key="cm_choice")

    if choice == NEW_MATRIX_OPTION:
        render_form(provider)
        return

    doc = db.get_document(labels[choice])
    if doc is None:
        st.error("That matrix no longer exists.")
        return
    render_matrix(doc)
