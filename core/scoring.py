"""Scoring determinístico: el LLM juzga evidencia, la aritmética es del código.

El puntaje es una suma ponderada reproducible y auditable — nunca un número
generado por el modelo.
"""

from .models import CandidateEvaluation, Rubric

STATUS_POINTS = {
    "evidencia_encontrada": 2,
    "evidencia_parcial": 1,
    "sin_evidencia": 0,
}

STATUS_LABELS = {
    "evidencia_encontrada": "✅ Evidencia encontrada",
    "evidencia_parcial": "🟡 Evidencia parcial",
    "sin_evidencia": "❌ Sin evidencia",
}


def score_candidate(rubric: Rubric, evaluation: CandidateEvaluation) -> dict:
    by_name = {c.name.casefold().strip(): c for c in rubric.competencies}
    max_points = sum(c.weight * STATUS_POINTS["evidencia_encontrada"] for c in rubric.competencies)

    points = 0
    missing_must_haves: list[str] = []
    unmatched: list[str] = []

    for ev in evaluation.evaluations:
        comp = by_name.get(ev.competency_name.casefold().strip())
        if comp is None:
            unmatched.append(ev.competency_name)
            continue
        points += comp.weight * STATUS_POINTS[ev.status]
        if comp.must_have and ev.status == "sin_evidencia":
            missing_must_haves.append(comp.name)

    score = round(100 * points / max_points, 1) if max_points else 0.0
    return {
        "score": score,
        "missing_must_haves": missing_must_haves,
        "unmatched_competencies": unmatched,
    }
