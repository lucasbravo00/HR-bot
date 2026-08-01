"""People Ops Copilot — MVP 1: recruiting core with evidence-based evaluation."""

import json

import pandas as pd
import streamlit as st

from core import db
from core.llm import OLLAMA_DEFAULT_MODEL, LLMError, LLMProvider, get_provider
from core.models import CandidateEvaluation, Competency, Rubric
from core.scoring import STATUS_LABELS, score_candidate

st.set_page_config(page_title="People Ops Copilot", page_icon="🧭", layout="wide")
db.init_db()

# Streamlit forbids writing to a widget's session_state key after that widget has
# been instantiated in the same run. Selecting a job after creating/deleting one
# therefore goes through this pending key, resolved before the job_choice radio
# (in render_sidebar) is created.
if "pending_job_choice" in st.session_state:
    st.session_state["job_choice"] = st.session_state.pop("pending_job_choice")

CATEGORIES = ["technical", "soft", "language", "other"]

ENGINE_LABELS = {
    "Claude (Anthropic)": "claude",
    "Ollama (local, open source)": "ollama",
}

NEW_JOB_OPTION = "➕ New job"


# ---------------------------------------------------------------- sidebar

def render_sidebar() -> tuple[str, LLMProvider]:
    st.sidebar.title("🧭 People Ops Copilot")
    st.sidebar.caption("Recruiting assistant with evidence-based evaluation")

    jobs = db.list_jobs()
    job_labels = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs}
    options = [NEW_JOB_OPTION] + list(job_labels)
    choice = st.sidebar.radio("Jobs", options, key="job_choice")

    st.sidebar.divider()
    engine_label = st.sidebar.selectbox("AI engine", list(ENGINE_LABELS), key="engine")
    engine = ENGINE_LABELS[engine_label]
    if engine == "ollama":
        ollama_model = st.sidebar.text_input("Ollama model", value=OLLAMA_DEFAULT_MODEL, key="ollama_model")
        st.sidebar.caption(
            "Resumes never leave your machine 🔒. Requires [Ollama](https://ollama.com) running "
            f"and the model downloaded (`ollama pull {ollama_model or OLLAMA_DEFAULT_MODEL}`). "
            "Small local models are less accurate at judging evidence than Claude."
        )
        provider = get_provider("ollama", ollama_model=ollama_model or OLLAMA_DEFAULT_MODEL)
    else:
        st.sidebar.caption("Requires `ANTHROPIC_API_KEY`. Best evaluation quality and native PDF reading.")
        provider = get_provider("claude")

    st.session_state["job_labels"] = job_labels
    return choice, provider


# ---------------------------------------------------------------- new job

def render_new_job(provider: LLMProvider) -> None:
    st.header("New job")
    st.markdown(
        "Paste the job description. The AI proposes a **competency rubric** "
        "you can edit before evaluating candidates."
    )
    title = st.text_input("Job name (optional, inferred from the description)")
    jd_text = st.text_area("Job description", height=350, placeholder="Paste the job description here…")

    if st.button("✨ Extract rubric with AI", type="primary", disabled=not jd_text.strip()):
        try:
            with st.spinner("Analyzing the job description…"):
                rubric = provider.extract_rubric(jd_text)
        except LLMError as e:
            st.error(str(e))
            return

        job_title = title.strip() or rubric.job_title
        job_id = db.create_job(job_title, jd_text, rubric.model_dump_json())
        st.session_state["pending_job_choice"] = f"{job_title} (#{job_id})"
        st.rerun()


# ---------------------------------------------------------------- rubric

def render_rubric_tab(job) -> Rubric:
    rubric = Rubric.model_validate_json(job["rubric_json"])

    with st.expander("View job description"):
        st.text(job["jd_text"])

    st.markdown(
        "The rubric is **editable**: adjust weights, mark must-haves or add competencies. "
        "Each candidate's score is computed in code from these weights — "
        "the model only judges evidence."
    )

    df = pd.DataFrame([c.model_dump() for c in rubric.competencies])
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "name": st.column_config.TextColumn("Competency", required=True),
            "category": st.column_config.SelectboxColumn("Type", options=CATEGORIES, required=True),
            "weight": st.column_config.NumberColumn("Weight (1-5)", min_value=1, max_value=5, step=1),
            "must_have": st.column_config.CheckboxColumn("Must-have"),
            "evidence_criteria": st.column_config.TextColumn("Evidence criterion", width="large"),
        },
        key=f"rubric_editor_{job['id']}",
    )

    if st.button("💾 Save rubric"):
        comps = []
        for row in edited.to_dict("records"):
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            comps.append(
                Competency(
                    name=name,
                    category=row.get("category") or "other",
                    weight=int(row.get("weight") or 3),
                    must_have=bool(row.get("must_have")),
                    evidence_criteria=str(row.get("evidence_criteria") or "").strip(),
                )
            )
        if not comps:
            st.warning("The rubric needs at least one competency.")
        else:
            db.update_rubric(job["id"], Rubric(job_title=rubric.job_title, competencies=comps).model_dump_json())
            st.success("Rubric saved. Upcoming evaluations will use it.")
            st.rerun()

    return rubric


# ---------------------------------------------------------------- candidates

def evaluate_files(job, rubric: Rubric, files, provider: LLMProvider) -> None:
    existing = db.candidate_filenames(job["id"])
    progress = st.progress(0.0)
    for i, f in enumerate(files):
        if f.name in existing:
            st.info(f"⏭️ {f.name}: already evaluated for this job, skipping.")
            progress.progress((i + 1) / len(files))
            continue
        try:
            with st.spinner(f"Evaluating {f.name} with {provider.name}…"):
                if f.name.lower().endswith(".pdf"):
                    evaluation = provider.evaluate_cv(job["jd_text"], rubric, f.name, cv_pdf=f.getvalue())
                else:
                    evaluation = provider.evaluate_cv(
                        job["jd_text"], rubric, f.name, cv_text=f.getvalue().decode("utf-8", errors="replace")
                    )
        except LLMError as e:
            st.error(f"{f.name}: {e}")
            continue

        result = score_candidate(rubric, evaluation)
        db.add_candidate(
            job["id"],
            evaluation.candidate_name,
            f.name,
            evaluation.model_dump_json(),
            result["score"],
            result["missing_must_haves"],
        )
        progress.progress((i + 1) / len(files))
    st.rerun()


def render_candidate_detail(row, rubric: Rubric) -> None:
    evaluation = CandidateEvaluation.model_validate_json(row["evaluation_json"])
    missing = json.loads(row["missing_must_haves_json"])
    comp_by_name = {c.name.casefold().strip(): c for c in rubric.competencies}

    if missing:
        st.error("⚠️ No evidence for must-have requirements: " + ", ".join(missing))
    st.markdown(f"**Recruiter summary:**\n\n{evaluation.summary}")
    st.divider()

    for ev in evaluation.evaluations:
        comp = comp_by_name.get(ev.competency_name.casefold().strip())
        weight_txt = f" · weight {comp.weight}" + (" · must-have" if comp.must_have else "") if comp else ""
        st.markdown(f"**{ev.competency_name}**{weight_txt} — {STATUS_LABELS[ev.status]}")
        for quote in ev.evidence_quotes:
            st.markdown(f"> {quote}")
        st.caption(ev.reasoning)

    if st.button("🗑️ Delete candidate", key=f"del_{row['id']}"):
        db.delete_candidate(row["id"])
        st.rerun()


def render_candidates_tab(job, rubric: Rubric, provider: LLMProvider) -> None:
    st.markdown(
        "Upload resumes as PDF or plain text. Each candidate is evaluated **independently** "
        "against the rubric; the score is a weighted sum computed in code."
    )
    files = st.file_uploader(
        "Candidate resumes", type=["pdf", "txt", "md"], accept_multiple_files=True,
        key=f"uploader_{job['id']}",
    )
    if files and st.button(f"🔍 Evaluate {len(files)} candidate(s)", type="primary"):
        evaluate_files(job, rubric, files, provider)

    candidates = db.list_candidates(job["id"])
    if not candidates:
        st.info("No candidates evaluated for this job yet.")
        return

    st.subheader("🏆 Ranking")
    st.caption(
        "The score reflects how much evidence the resume contains for the rubric — "
        "“no evidence” means the resume doesn't mention it, not that the candidate lacks it."
    )
    ranking = pd.DataFrame(
        [
            {
                "Candidate": r["name"],
                "File": r["filename"],
                "Match": r["score"],
                "Must-haves without evidence": ", ".join(json.loads(r["missing_must_haves_json"])) or "—",
            }
            for r in candidates
        ]
    )
    st.dataframe(
        ranking,
        width="stretch",
        hide_index=True,
        column_config={
            "Match": st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%.1f%%"),
        },
    )

    st.subheader("📄 Candidate reports")
    for row in candidates:
        flag = " ⚠️" if json.loads(row["missing_must_haves_json"]) else ""
        with st.expander(f"{row['name']} — {row['score']:.1f}%{flag}"):
            render_candidate_detail(row, rubric)


# ---------------------------------------------------------------- main

choice, provider = render_sidebar()

if choice == NEW_JOB_OPTION:
    render_new_job(provider)
else:
    job = db.get_job(st.session_state["job_labels"][choice])
    if job is None:
        st.error("The selected job no longer exists.")
    else:
        st.header(job["title"])
        tab_rubric, tab_candidates = st.tabs(["📋 Rubric", "👥 Candidates"])
        with tab_rubric:
            rubric = render_rubric_tab(job)
        with tab_candidates:
            render_candidates_tab(job, rubric, provider)

        with st.sidebar:
            st.divider()
            if st.button("🗑️ Delete this job"):
                db.delete_job(job["id"])
                st.session_state["pending_job_choice"] = NEW_JOB_OPTION
                st.rerun()
