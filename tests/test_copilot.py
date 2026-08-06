"""Deterministic pieces of the copilot modules."""

import pytest

from core.models import CandidateEvaluation, JobDescriptionDraft
from core.tasks import _with_real_name
from views.competency_matrices import _parse_levels


# ------------------------------------------------------------------ job descriptions

def _draft(**overrides) -> JobDescriptionDraft:
    base = dict(
        title="Customer Success Manager",
        summary="Own retention for enterprise accounts.",
        responsibilities=["Run QBRs"],
        hard_requirements=["3+ years in B2B SaaS"],
        nice_to_haves=[],
        what_we_offer=[],
    )
    return JobDescriptionDraft(**{**base, **overrides})


def test_draft_renders_required_sections():
    text = _draft().to_text()
    assert "Customer Success Manager" in text
    assert "Responsibilities:\n- Run QBRs" in text
    assert "Hard requirements:\n- 3+ years in B2B SaaS" in text


def test_empty_optional_sections_are_omitted():
    """A brief with no benefits must not produce an empty 'What we offer' heading."""
    text = _draft().to_text()
    assert "Nice to have" not in text
    assert "What we offer" not in text


def test_optional_sections_appear_when_present():
    text = _draft(nice_to_haves=["Basic SQL"], what_we_offer=["Remote work"]).to_text()
    assert "Nice to have:\n- Basic SQL" in text
    assert "What we offer:\n- Remote work" in text


# ------------------------------------------------------------------ competency matrix levels

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Junior, Senior", ["Junior", "Senior"]),
        ("  Junior ,  Senior  ", ["Junior", "Senior"]),
        ("Junior, , Senior", ["Junior", "Senior"]),
        ("Junior, junior, Senior", ["Junior", "Senior"]),  # deduped case-insensitively
        ("", []),
    ],
)
def test_level_parsing(raw, expected):
    assert _parse_levels(raw) == expected


def test_level_count_is_capped():
    raw = ", ".join(f"L{i}" for i in range(12))
    assert len(_parse_levels(raw)) == 6


def test_level_order_is_preserved():
    assert _parse_levels("Lead, Junior, Senior") == ["Lead", "Junior", "Senior"]


# ------------------------------------------------------------------ blind placeholder handling

def _evaluation(name: str) -> CandidateEvaluation:
    return CandidateEvaluation(candidate_name=name, summary="", evaluations=[])


def test_blind_placeholder_is_replaced_for_recruiter_facing_artifacts():
    """Briefs about "Redacted Résumé" would be nonsense — the recruiter knows who this is."""
    result = _with_real_name(_evaluation("Redacted Résumé"), "Ana García")
    assert result.candidate_name == "Ana García"


def test_original_evaluation_is_not_mutated():
    evaluation = _evaluation("Redacted Résumé")
    _with_real_name(evaluation, "Ana García")
    assert evaluation.candidate_name == "Redacted Résumé"


@pytest.mark.parametrize("name", ["", "   "])
def test_missing_name_leaves_the_evaluation_alone(name):
    result = _with_real_name(_evaluation("Ana García"), name)
    assert result.candidate_name == "Ana García"
