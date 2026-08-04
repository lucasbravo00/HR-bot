"""People Ops Copilot — recruiting core with evidence-based evaluation."""

import json

import pandas as pd
import streamlit as st

from core import db
from core.llm import OLLAMA_DEFAULT_MODEL, LLMError, LLMProvider, get_provider
from core.models import CandidateEvaluation, Competency, InterviewKit, Rubric
from core.scoring import STATUS_LABELS, score_candidate
from core.tasks import (
    anonymize_resume,
    draft_email,
    evaluate_cv,
    extract_rubric,
    generate_interview_kit,
)

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

EMAIL_LABELS = {
    "Interview invitation": "invitation",
    "Rejection": "rejection",
    "Follow-up": "follow_up",
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
                rubric = extract_rubric(provider, jd_text)
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


# ---------------------------------------------------------------- evaluation run

def evaluate_files(job, rubric: Rubric, files, provider: LLMProvider, blind: bool) -> None:
    existing = db.candidate_filenames(job["id"])
    progress = st.progress(0.0)
    for i, f in enumerate(files):
        if f.name in existing:
            st.info(f"⏭️ {f.name}: already evaluated for this job, skipping.")
            progress.progress((i + 1) / len(files))
            continue

        is_pdf = f.name.lower().endswith(".pdf")
        cv_pdf = f.getvalue() if is_pdf else None
        cv_text = None if is_pdf else f.getvalue().decode("utf-8", errors="replace")
        blind_name = None
        # Filenames leak identity ("cv_ana_garcia.pdf"), so blind runs get a neutral one.
        eval_filename = f.name

        try:
            if blind:
                with st.spinner(f"Anonymizing {f.name}…"):
                    anon = anonymize_resume(provider, f.name, cv_text=cv_text, cv_pdf=cv_pdf)
                # The evaluator sees only the redacted text — never the original document.
                cv_text, cv_pdf = anon.redacted_text, None
                blind_name = anon.candidate_name
                eval_filename = "redacted résumé"

            with st.spinner(f"Evaluating {f.name} with {provider.name}…"):
                evaluation = evaluate_cv(
                    provider, job["jd_text"], rubric, eval_filename, cv_text=cv_text, cv_pdf=cv_pdf
                )
        except LLMError as e:
            st.error(f"{f.name}: {e}")
            continue

        result = score_candidate(rubric, evaluation)
        # In blind mode the identity comes from the anonymizer, not the evaluator.
        display_name = blind_name or evaluation.candidate_name
        db.add_candidate(
            job["id"],
            display_name,
            f.name,
            evaluation.model_dump_json(),
            result["score"],
            result["missing_must_haves"],
            blind=blind,
        )
        progress.progress((i + 1) / len(files))
    st.rerun()


# ---------------------------------------------------------------- candidate detail

def render_report(row, evaluation: CandidateEvaluation, rubric: Rubric) -> None:
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


def render_interview_kit(row, evaluation: CandidateEvaluation, rubric: Rubric,
                         job, provider: LLMProvider) -> None:
    cid = row["id"]
    if row["interview_kit_json"]:
        kit = InterviewKit.model_validate_json(row["interview_kit_json"])
        st.markdown(f"**Pre-interview brief**\n\n{kit.executive_summary}")
        if kit.focus_areas:
            st.markdown("**Focus areas:** " + " · ".join(f"`{a}`" for a in kit.focus_areas))
        st.divider()
        for i, q in enumerate(kit.questions, 1):
            st.markdown(f"**{i}. {q.question}**")
            st.caption(f"🎯 {q.competency_name} — {q.rationale}")
            st.caption(f"👂 Listen for: {q.what_to_listen_for}")
        label = "🔄 Regenerate interview kit"
    else:
        st.info(
            "Generate a pre-interview brief and behavioral (STAR) questions built from "
            "this candidate's evidence gaps."
        )
        label = "🎤 Generate interview kit"

    if st.button(label, key=f"kit_{cid}"):
        try:
            with st.spinner("Preparing the interview…"):
                kit = generate_interview_kit(
                    provider, job["jd_text"], rubric, evaluation,
                    row["score"], json.loads(row["missing_must_haves_json"]),
                )
        except LLMError as e:
            st.error(str(e))
            return
        db.save_interview_kit(cid, kit.model_dump_json())
        st.rerun()


def render_emails(row, evaluation: CandidateEvaluation, job, provider: LLMProvider) -> None:
    cid = row["id"]
    st.caption(
        "Drafts only — nothing is ever sent from here. Review, edit and send from your "
        "own email client. Internal scores and rubric judgments are never disclosed."
    )
    kind_label = st.selectbox("Email type", list(EMAIL_LABELS), key=f"email_kind_{cid}")
    kind = EMAIL_LABELS[kind_label]
    notes = st.text_input(
        "Anything to add? (optional)",
        placeholder="e.g. propose Tuesday or Thursday, mention it is a 45-minute call",
        key=f"email_notes_{cid}",
    )

    if st.button(f"✉️ Draft {kind_label.lower()}", key=f"email_btn_{cid}"):
        try:
            with st.spinner("Drafting…"):
                email = draft_email(
                    provider, kind, job["jd_text"], job["title"],
                    row["name"], evaluation, notes,
                )
        except LLMError as e:
            st.error(str(e))
            return
        db.save_email(cid, kind, email.subject, email.body)
        st.rerun()

    emails = json.loads(row["emails_json"]) if row["emails_json"] else {}
    if kind in emails:
        draft = emails[kind]
        st.text_input("Subject", value=draft["subject"], key=f"email_subject_{cid}_{kind}")
        st.text_area("Body", value=draft["body"], height=280, key=f"email_body_{cid}_{kind}")


def render_candidate_detail(row, rubric: Rubric, job, provider: LLMProvider) -> None:
    evaluation = CandidateEvaluation.model_validate_json(row["evaluation_json"])

    if row["blind"]:
        st.caption("🕶️ Evaluated blind — the model judged a redacted resume with no identity.")

    tab_report, tab_kit, tab_email = st.tabs(["📄 Report", "🎤 Interview kit", "✉️ Emails"])
    with tab_report:
        render_report(row, evaluation, rubric)
    with tab_kit:
        render_interview_kit(row, evaluation, rubric, job, provider)
    with tab_email:
        render_emails(row, evaluation, job, provider)

    st.divider()
    if st.button("🗑️ Delete candidate", key=f"del_{row['id']}"):
        db.delete_candidate(row["id"])
        st.rerun()


# ---------------------------------------------------------------- candidates tab

def render_candidates_tab(job, rubric: Rubric, provider: LLMProvider) -> None:
    st.markdown(
        "Upload resumes as PDF or plain text. Each candidate is evaluated **independently** "
        "against the rubric; the score is a weighted sum computed in code."
    )
    blind = st.toggle(
        "🕶️ Blind screening",
        value=True,
        help=(
            "Strips name, contact details, location, age and other personal markers before "
            "the evaluator sees the resume, keeping all professional content verbatim. "
            "You still see the candidate's identity here. Adds one AI call per resume."
        ),
        key=f"blind_{job['id']}",
    )
    files = st.file_uploader(
        "Candidate resumes", type=["pdf", "txt", "md"], accept_multiple_files=True,
        key=f"uploader_{job['id']}",
    )
    if files and st.button(f"🔍 Evaluate {len(files)} candidate(s)", type="primary"):
        evaluate_files(job, rubric, files, provider, blind)

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
                "Blind": "🕶️" if r["blind"] else "—",
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
            render_candidate_detail(row, rubric, job, provider)


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
