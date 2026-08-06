"""Job description generator: turn a short brief into a posting, ready to hire against."""

import streamlit as st

from core import db
from core.llm import LLMError, LLMProvider
from core.models import JobDescriptionDraft
from core.tasks import generate_job_description

from .common import bullet_list
from .recruiting import NEW_JOB_OPTION

KIND = "job_description"
NEW_DRAFT_OPTION = "➕ New draft"


def _as_markdown(jd: JobDescriptionDraft) -> str:
    parts = [f"# {jd.title}", "", jd.summary, "", "## Responsibilities", bullet_list(jd.responsibilities),
             "", "## Requirements", bullet_list(jd.hard_requirements)]
    if jd.nice_to_haves:
        parts += ["", "## Nice to have", bullet_list(jd.nice_to_haves)]
    if jd.what_we_offer:
        parts += ["", "## What we offer", bullet_list(jd.what_we_offer)]
    return "\n".join(parts)


def render_form(provider: LLMProvider) -> None:
    st.header("New job description")
    st.markdown(
        "Give the AI a short brief. It writes the posting keeping requirements honest and "
        "proportionate — inflated requirement lists shrink and skew applicant pools."
    )

    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("Role title", placeholder="Customer Success Manager", key="jd_title")
    with col2:
        seniority = st.text_input("Seniority", placeholder="Mid-level / Senior", key="jd_seniority")

    context = st.text_area(
        "Team and company context",
        height=120,
        placeholder="B2B SaaS startup, 40 people. The CS team owns retention for LATAM enterprise accounts.",
        key="jd_context",
    )
    must_haves = st.text_area(
        "Must-haves — genuinely disqualifying if absent",
        height=100,
        placeholder="3+ years in Customer Success or Account Management in B2B SaaS\nAdvanced English",
        key="jd_musts",
    )
    nice_to_haves = st.text_area(
        "Nice-to-haves (optional)",
        height=80,
        placeholder="Experience mentoring other CSMs\nBasic SQL",
        key="jd_nices",
    )
    notes = st.text_input(
        "Notes: tone, location, work model (optional)",
        placeholder="Remote within LATAM, warm and direct tone",
        key="jd_notes",
    )

    ready = bool(title.strip() and must_haves.strip())
    if st.button("✨ Write job description", type="primary", disabled=not ready):
        try:
            with st.spinner("Writing…"):
                jd = generate_job_description(
                    provider, title, seniority, context, must_haves, nice_to_haves, notes
                )
        except LLMError as e:
            st.error(str(e))
            return
        doc_id = db.save_document(KIND, jd.title, jd.model_dump_json())
        st.session_state["pending_jd_choice"] = f"{jd.title} (#{doc_id})"
        st.rerun()

    if not ready:
        st.caption("A role title and at least one must-have are required.")


def render_draft(doc, provider: LLMProvider) -> None:
    jd = JobDescriptionDraft.model_validate_json(doc["payload_json"])

    st.header(jd.title)
    st.markdown(jd.summary)

    st.subheader("Responsibilities")
    st.markdown(bullet_list(jd.responsibilities))

    st.subheader("Requirements")
    st.markdown(bullet_list(jd.hard_requirements))

    if jd.nice_to_haves:
        st.subheader("Nice to have")
        st.markdown(bullet_list(jd.nice_to_haves))

    if jd.what_we_offer:
        st.subheader("What we offer")
        st.markdown(bullet_list(jd.what_we_offer))
    else:
        st.caption(
            "No compensation or benefits section — the brief didn't mention any, and the "
            "generator never invents them."
        )

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        # Closes the loop: this posting becomes the rubric candidates are scored against.
        if st.button("🎯 Hire for this role", type="primary"):
            st.session_state["pending_new_jd_text"] = jd.to_text()
            st.session_state["pending_job_choice"] = NEW_JOB_OPTION
            st.session_state["pending_section"] = "🎯 Recruiting"
            st.rerun()
    with col2:
        st.download_button(
            "⬇️ Download Markdown",
            data=_as_markdown(jd),
            file_name=f"{jd.title.lower().replace(' ', '_')}.md",
            mime="text/markdown",
        )
    with col3:
        if st.button("🗑️ Delete draft"):
            db.delete_document(doc["id"])
            st.session_state["pending_jd_choice"] = NEW_DRAFT_OPTION
            st.rerun()


def render(provider: LLMProvider, sidebar) -> None:
    docs = db.list_documents(KIND)
    labels = {f"{d['title']} (#{d['id']})": d["id"] for d in docs}

    with sidebar:
        choice = st.radio("Drafts", [NEW_DRAFT_OPTION] + list(labels), key="jd_choice")

    if choice == NEW_DRAFT_OPTION:
        render_form(provider)
        return

    doc = db.get_document(labels[choice])
    if doc is None:
        st.error("That draft no longer exists.")
        return
    render_draft(doc, provider)
