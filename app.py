"""People Ops Copilot — MVP 1: núcleo de recruiting con evaluación basada en evidencia."""

import json

import pandas as pd
import streamlit as st

from core import db
from core.llm import OLLAMA_DEFAULT_MODEL, LLMError, LLMProvider, get_provider
from core.models import CandidateEvaluation, Competency, Rubric
from core.scoring import STATUS_LABELS, score_candidate

st.set_page_config(page_title="People Ops Copilot", page_icon="🧭", layout="wide")
db.init_db()

CATEGORIES = ["tecnica", "blanda", "idioma", "otra"]

ENGINE_LABELS = {
    "Claude (Anthropic)": "claude",
    "Ollama (modelo local, open source)": "ollama",
}


# ---------------------------------------------------------------- sidebar

def render_sidebar() -> tuple[str, LLMProvider]:
    st.sidebar.title("🧭 People Ops Copilot")
    st.sidebar.caption("Asistente de selección con evaluación basada en evidencia")

    jobs = db.list_jobs()
    job_labels = {f"{j['title']} (#{j['id']})": j["id"] for j in jobs}
    options = ["➕ Nueva búsqueda"] + list(job_labels)
    choice = st.sidebar.radio("Búsquedas", options, key="job_choice")

    st.sidebar.divider()
    engine_label = st.sidebar.selectbox("Motor de IA", list(ENGINE_LABELS), key="engine")
    engine = ENGINE_LABELS[engine_label]
    if engine == "ollama":
        ollama_model = st.sidebar.text_input("Modelo de Ollama", value=OLLAMA_DEFAULT_MODEL, key="ollama_model")
        st.sidebar.caption(
            "Los CVs no salen de tu máquina 🔒. Requiere [Ollama](https://ollama.com) corriendo "
            f"y el modelo descargado (`ollama pull {ollama_model or OLLAMA_DEFAULT_MODEL}`). "
            "Los modelos locales chicos son menos precisos juzgando evidencia que Claude."
        )
        provider = get_provider("ollama", ollama_model=ollama_model or OLLAMA_DEFAULT_MODEL)
    else:
        st.sidebar.caption("Requiere `ANTHROPIC_API_KEY`. Mayor calidad de evaluación y lectura nativa de PDFs.")
        provider = get_provider("claude")

    st.session_state["job_labels"] = job_labels
    return choice, provider


# ---------------------------------------------------------------- nueva búsqueda

def render_new_job(provider: LLMProvider) -> None:
    st.header("Nueva búsqueda")
    st.markdown(
        "Pegá la descripción del puesto. La IA propone una **rúbrica de competencias** "
        "que después podés editar antes de evaluar candidatos."
    )
    title = st.text_input("Nombre de la búsqueda (opcional, se infiere del puesto)")
    jd_text = st.text_area("Descripción del puesto", height=350, placeholder="Pegá acá la job description…")

    if st.button("✨ Extraer rúbrica con IA", type="primary", disabled=not jd_text.strip()):
        try:
            with st.spinner("Analizando la descripción del puesto…"):
                rubric = provider.extract_rubric(jd_text)
        except LLMError as e:
            st.error(str(e))
            return

        job_title = title.strip() or rubric.job_title
        job_id = db.create_job(job_title, jd_text, rubric.model_dump_json())
        st.session_state["job_choice"] = f"{job_title} (#{job_id})"
        st.rerun()


# ---------------------------------------------------------------- rúbrica

def render_rubric_tab(job) -> Rubric:
    rubric = Rubric.model_validate_json(job["rubric_json"])

    with st.expander("Ver descripción del puesto"):
        st.text(job["jd_text"])

    st.markdown(
        "La rúbrica es **editable**: ajustá pesos, marcá excluyentes o agregá competencias. "
        "El puntaje de cada candidato se calcula en código a partir de estos pesos — "
        "el modelo solo juzga la evidencia."
    )

    df = pd.DataFrame([c.model_dump() for c in rubric.competencies])
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "name": st.column_config.TextColumn("Competencia", required=True),
            "category": st.column_config.SelectboxColumn("Tipo", options=CATEGORIES, required=True),
            "weight": st.column_config.NumberColumn("Peso (1-5)", min_value=1, max_value=5, step=1),
            "must_have": st.column_config.CheckboxColumn("Excluyente"),
            "evidence_criteria": st.column_config.TextColumn("Criterio de evidencia", width="large"),
        },
        key=f"rubric_editor_{job['id']}",
    )

    if st.button("💾 Guardar rúbrica"):
        comps = []
        for row in edited.to_dict("records"):
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            comps.append(
                Competency(
                    name=name,
                    category=row.get("category") or "otra",
                    weight=int(row.get("weight") or 3),
                    must_have=bool(row.get("must_have")),
                    evidence_criteria=str(row.get("evidence_criteria") or "").strip(),
                )
            )
        if not comps:
            st.warning("La rúbrica necesita al menos una competencia.")
        else:
            db.update_rubric(job["id"], Rubric(job_title=rubric.job_title, competencies=comps).model_dump_json())
            st.success("Rúbrica guardada. Las próximas evaluaciones la usarán.")
            st.rerun()

    return rubric


# ---------------------------------------------------------------- candidatos

def evaluate_files(job, rubric: Rubric, files, provider: LLMProvider) -> None:
    existing = db.candidate_filenames(job["id"])
    progress = st.progress(0.0)
    for i, f in enumerate(files):
        if f.name in existing:
            st.info(f"⏭️ {f.name}: ya fue evaluado para esta búsqueda, se omite.")
            progress.progress((i + 1) / len(files))
            continue
        try:
            with st.spinner(f"Evaluando {f.name} con {provider.name}…"):
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
        st.error("⚠️ Sin evidencia de requisitos excluyentes: " + ", ".join(missing))
    st.markdown(f"**Resumen para el recruiter:**\n\n{evaluation.summary}")
    st.divider()

    for ev in evaluation.evaluations:
        comp = comp_by_name.get(ev.competency_name.casefold().strip())
        weight_txt = f" · peso {comp.weight}" + (" · excluyente" if comp.must_have else "") if comp else ""
        st.markdown(f"**{ev.competency_name}**{weight_txt} — {STATUS_LABELS[ev.status]}")
        for quote in ev.evidence_quotes:
            st.markdown(f"> {quote}")
        st.caption(ev.reasoning)

    if st.button("🗑️ Eliminar candidato", key=f"del_{row['id']}"):
        db.delete_candidate(row["id"])
        st.rerun()


def render_candidates_tab(job, rubric: Rubric, provider: LLMProvider) -> None:
    st.markdown(
        "Subí CVs en PDF o texto plano. Cada candidato se evalúa **de forma independiente** "
        "contra la rúbrica; el puntaje es una suma ponderada calculada en código."
    )
    files = st.file_uploader(
        "CVs de candidatos", type=["pdf", "txt", "md"], accept_multiple_files=True,
        key=f"uploader_{job['id']}",
    )
    if files and st.button(f"🔍 Evaluar {len(files)} candidato(s)", type="primary"):
        evaluate_files(job, rubric, files, provider)

    candidates = db.list_candidates(job["id"])
    if not candidates:
        st.info("Todavía no hay candidatos evaluados para esta búsqueda.")
        return

    st.subheader("🏆 Ranking")
    st.caption(
        "El puntaje refleja cuánta evidencia hay en el CV para la rúbrica — "
        "«sin evidencia» significa que el CV no lo menciona, no que el candidato no lo tenga."
    )
    ranking = pd.DataFrame(
        [
            {
                "Candidato": r["name"],
                "Archivo": r["filename"],
                "Match": r["score"],
                "Excluyentes sin evidencia": ", ".join(json.loads(r["missing_must_haves_json"])) or "—",
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

    st.subheader("📄 Informes por candidato")
    for row in candidates:
        flag = " ⚠️" if json.loads(row["missing_must_haves_json"]) else ""
        with st.expander(f"{row['name']} — {row['score']:.1f}%{flag}"):
            render_candidate_detail(row, rubric)


# ---------------------------------------------------------------- main

choice, provider = render_sidebar()

if choice == "➕ Nueva búsqueda":
    render_new_job(provider)
else:
    job = db.get_job(st.session_state["job_labels"][choice])
    if job is None:
        st.error("La búsqueda seleccionada ya no existe.")
    else:
        st.header(job["title"])
        tab_rubric, tab_candidates = st.tabs(["📋 Rúbrica", "👥 Candidatos"])
        with tab_rubric:
            rubric = render_rubric_tab(job)
        with tab_candidates:
            render_candidates_tab(job, rubric, provider)

        with st.sidebar:
            st.divider()
            if st.button("🗑️ Eliminar esta búsqueda"):
                db.delete_job(job["id"])
                st.session_state["job_choice"] = "➕ Nueva búsqueda"
                st.rerun()
