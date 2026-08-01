"""Deterministic scoring: the LLM judges evidence, the arithmetic belongs to code.

The score is a reproducible, auditable weighted sum — never a number generated
by the model.
"""

from .models import CandidateEvaluation, Rubric

STATUS_POINTS = {
    "evidence_found": 2,
    "partial_evidence": 1,
    "no_evidence": 0,
}

STATUS_LABELS = {
    "evidence_found": "✅ Evidence found",
    "partial_evidence": "🟡 Partial evidence",
    "no_evidence": "❌ No evidence",
}


def score_candidate(rubric: Rubric, evaluation: CandidateEvaluation) -> dict:
    by_name = {c.name.casefold().strip(): c for c in rubric.competencies}
    max_points = sum(c.weight * STATUS_POINTS["evidence_found"] for c in rubric.competencies)

    points = 0
    missing_must_haves: list[str] = []
    unmatched: list[str] = []

    for ev in evaluation.evaluations:
        comp = by_name.get(ev.competency_name.casefold().strip())
        if comp is None:
            unmatched.append(ev.competency_name)
            continue
        points += comp.weight * STATUS_POINTS[ev.status]
        if comp.must_have and ev.status == "no_evidence":
            missing_must_haves.append(comp.name)

    score = round(100 * points / max_points, 1) if max_points else 0.0
    return {
        "score": score,
        "missing_must_haves": missing_must_haves,
        "unmatched_competencies": unmatched,
    }
