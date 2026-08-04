"""The score is computed in code, so it is worth pinning down exactly."""

from core.models import CandidateEvaluation, CompetencyEvaluation, Competency, Rubric
from core.scoring import score_candidate


def _rubric() -> Rubric:
    return Rubric(
        job_title="CSM",
        competencies=[
            Competency(name="CS in SaaS", category="technical", weight=5,
                       must_have=True, evidence_criteria="3+ years"),
            Competency(name="English C1", category="language", weight=4,
                       must_have=True, evidence_criteria="C1 level"),
            Competency(name="CRM", category="technical", weight=1,
                       must_have=False, evidence_criteria="HubSpot/Salesforce"),
        ],
    )


def _evaluation(*statuses: str) -> CandidateEvaluation:
    names = ["CS in SaaS", "English C1", "CRM"]
    return CandidateEvaluation(
        candidate_name="Candidate",
        summary="",
        evaluations=[
            CompetencyEvaluation(competency_name=n, status=s, evidence_quotes=[], reasoning="")
            for n, s in zip(names, statuses)
        ],
    )


def test_full_evidence_scores_100():
    result = score_candidate(_rubric(), _evaluation(*["evidence_found"] * 3))
    assert result["score"] == 100.0


def test_no_evidence_scores_zero():
    result = score_candidate(_rubric(), _evaluation(*["no_evidence"] * 3))
    assert result["score"] == 0.0


def test_partial_evidence_is_worth_half():
    result = score_candidate(_rubric(), _evaluation(*["partial_evidence"] * 3))
    assert result["score"] == 50.0


def test_weights_drive_the_score():
    """The heavy competency must move the score more than the light one."""
    heavy = score_candidate(_rubric(), _evaluation("evidence_found", "no_evidence", "no_evidence"))
    light = score_candidate(_rubric(), _evaluation("no_evidence", "no_evidence", "evidence_found"))
    assert heavy["score"] > light["score"]


def test_missing_must_have_is_reported():
    result = score_candidate(_rubric(), _evaluation("evidence_found", "no_evidence", "evidence_found"))
    assert result["missing_must_haves"] == ["English C1"]


def test_partial_evidence_is_not_a_missing_must_have():
    """Partial evidence is a question for the interview, not a disqualification."""
    result = score_candidate(_rubric(), _evaluation("partial_evidence", "partial_evidence", "no_evidence"))
    assert result["missing_must_haves"] == []


def test_competency_names_match_case_insensitively():
    evaluation = _evaluation("evidence_found", "evidence_found", "evidence_found")
    evaluation.evaluations[1].competency_name = "  english c1 "
    result = score_candidate(_rubric(), evaluation)
    assert result["score"] == 100.0
    assert result["unmatched_competencies"] == []


def test_hallucinated_competency_is_flagged_and_ignored():
    evaluation = _evaluation("evidence_found", "evidence_found", "evidence_found")
    evaluation.evaluations.append(
        CompetencyEvaluation(competency_name="Invented skill", status="evidence_found",
                             evidence_quotes=[], reasoning="")
    )
    result = score_candidate(_rubric(), evaluation)
    assert result["unmatched_competencies"] == ["Invented skill"]
    assert result["score"] == 100.0  # cannot inflate past the rubric's maximum
