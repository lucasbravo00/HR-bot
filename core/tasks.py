"""Recruiting tasks, written once against the provider interface.

Each task is a prompt + a schema. Engines are interchangeable underneath, so a new
capability never has to be implemented twice.
"""

from .models import (
    AnonymizedResume,
    CandidateEvaluation,
    CompetencyMatrix,
    EmailDraft,
    EmailKind,
    InterviewKit,
    JobDescriptionDraft,
    OnboardingPlan,
    Rubric,
)
from .prompts import (
    ANONYMIZE_SYSTEM,
    COMPETENCY_MATRIX_SYSTEM,
    EMAIL_SYSTEM,
    EVAL_INSTRUCTIONS,
    INTERVIEW_KIT_SYSTEM,
    JOB_DESCRIPTION_SYSTEM,
    ONBOARDING_SYSTEM,
    RUBRIC_SYSTEM,
    job_context,
)
from .providers.base import LLMError, LLMProvider
from .redaction import scrub_residual_identity

EMAIL_KIND_LABELS = {
    "invitation": "interview invitation",
    "rejection": "rejection",
    "follow_up": "follow-up",
}


def extract_rubric(provider: LLMProvider, jd_text: str) -> Rubric:
    rubric = provider.complete(
        instructions=RUBRIC_SYSTEM,
        user_text=f"Job description:\n\n{jd_text}",
        schema=Rubric,
    )
    if not rubric.competencies:
        raise LLMError(
            "The model returned an empty rubric. Try again, or use a larger model "
            "if you are on a local engine."
        )
    return rubric


def anonymize_resume(
    provider: LLMProvider,
    filename: str,
    cv_text: str | None = None,
    cv_pdf: bytes | None = None,
) -> AnonymizedResume:
    """Split identity out of a resume so the evaluator only sees professional content."""
    body = f"Resume (file: {filename}):\n\n{cv_text}\n\n" if cv_text else ""
    result = provider.complete(
        instructions=ANONYMIZE_SYSTEM,
        user_text=f"{body}Redact this resume for blind screening.",
        schema=AnonymizedResume,
        pdf=cv_pdf,
    )
    if not result.redacted_text.strip():
        raise LLMError(
            "Anonymization returned an empty resume. Try again, or turn off blind "
            "screening for this candidate."
        )

    # Models redact inconsistently (a stripped surname with the first name left in,
    # for example). Blind screening is not something to stake on model judgment.
    result.redacted_text, caught = scrub_residual_identity(
        result.redacted_text, result.candidate_name
    )
    if caught:
        result.redacted_items = sorted(
            set(result.redacted_items) | {f"{item} (auto-scrubbed)" for item in caught}
        )
    return result


def evaluate_cv(
    provider: LLMProvider,
    jd_text: str,
    rubric: Rubric,
    filename: str,
    cv_text: str | None = None,
    cv_pdf: bytes | None = None,
) -> CandidateEvaluation:
    body = f"Resume (file: {filename}):\n\n{cv_text}\n\n" if cv_text else ""
    return provider.complete(
        instructions=EVAL_INSTRUCTIONS,
        context=job_context(jd_text, rubric.model_dump_json(indent=2)),
        user_text=f"{body}Evaluate this resume against the rubric.",
        schema=CandidateEvaluation,
        pdf=cv_pdf,
    )


def _with_real_name(evaluation: CandidateEvaluation, candidate_name: str) -> CandidateEvaluation:
    """Restore the candidate's name for recruiter-facing artifacts.

    A blind evaluation carries a placeholder ("Redacted Résumé") because the evaluator
    never saw who it was judging. Blind screening protects the ranking stage — by the
    time a recruiter is preparing an interview or a ramp-up plan, the person is known
    to them, and a brief about "Redacted Résumé" would be nonsense.
    """
    if not candidate_name.strip():
        return evaluation
    return evaluation.model_copy(update={"candidate_name": candidate_name})


def generate_interview_kit(
    provider: LLMProvider,
    jd_text: str,
    rubric: Rubric,
    evaluation: CandidateEvaluation,
    score: float,
    missing_must_haves: list[str],
    candidate_name: str = "",
) -> InterviewKit:
    evaluation = _with_real_name(evaluation, candidate_name)
    gaps = ", ".join(missing_must_haves) if missing_must_haves else "none"
    return provider.complete(
        instructions=INTERVIEW_KIT_SYSTEM,
        context=job_context(jd_text, rubric.model_dump_json(indent=2)),
        user_text=(
            f"Evaluation of this candidate (JSON):\n{evaluation.model_dump_json(indent=2)}\n\n"
            f"Weighted evidence score: {score}%. "
            f"Must-have competencies with no evidence in the resume: {gaps}.\n\n"
            "Prepare the recruiter for this candidate's interview."
        ),
        schema=InterviewKit,
    )


def generate_job_description(
    provider: LLMProvider,
    title: str,
    seniority: str,
    context: str,
    must_haves: str,
    nice_to_haves: str = "",
    notes: str = "",
) -> JobDescriptionDraft:
    brief = [f"Role title: {title}"]
    if seniority.strip():
        brief.append(f"Seniority: {seniority}")
    if context.strip():
        brief.append(f"Team and company context:\n{context}")
    if must_haves.strip():
        brief.append(f"Must-have requirements:\n{must_haves}")
    if nice_to_haves.strip():
        brief.append(f"Nice-to-have requirements:\n{nice_to_haves}")
    if notes.strip():
        brief.append(f"Additional notes (tone, location, work model):\n{notes}")

    return provider.complete(
        instructions=JOB_DESCRIPTION_SYSTEM,
        user_text="\n\n".join(brief) + "\n\nWrite the job description.",
        schema=JobDescriptionDraft,
    )


def generate_competency_matrix(
    provider: LLMProvider,
    role_description: str,
    levels: list[str],
) -> CompetencyMatrix:
    if len(levels) < 2:
        raise LLMError("A competency matrix needs at least two seniority levels.")

    matrix = provider.complete(
        instructions=COMPETENCY_MATRIX_SYSTEM,
        user_text=(
            f"Role family / role description:\n{role_description}\n\n"
            f"Seniority levels, in order: {', '.join(levels)}\n\n"
            "Build the competency matrix."
        ),
        schema=CompetencyMatrix,
    )
    if not matrix.competencies:
        raise LLMError(
            "The model returned an empty matrix. Try again, or use a larger model "
            "if you are on a local engine."
        )
    return matrix


def generate_onboarding_plan(
    provider: LLMProvider,
    jd_text: str,
    rubric: Rubric,
    evaluation: CandidateEvaluation,
    missing_must_haves: list[str],
    candidate_name: str = "",
) -> OnboardingPlan:
    """Turn the hiring evidence into a ramp-up plan for someone who was just hired."""
    evaluation = _with_real_name(evaluation, candidate_name)
    gaps = ", ".join(missing_must_haves) if missing_must_haves else "none"
    return provider.complete(
        instructions=ONBOARDING_SYSTEM,
        context=job_context(jd_text, rubric.model_dump_json(indent=2)),
        user_text=(
            f"Evaluation gathered while hiring (JSON):\n{evaluation.model_dump_json(indent=2)}\n\n"
            f"Must-have competencies with no evidence in the resume: {gaps}.\n\n"
            "Design this person's first 90 days."
        ),
        schema=OnboardingPlan,
    )


def draft_email(
    provider: LLMProvider,
    kind: EmailKind,
    jd_text: str,
    job_title: str,
    candidate_name: str,
    evaluation: CandidateEvaluation,
    notes: str = "",
) -> EmailDraft:
    """Draft a candidate-facing email. The recruiter reviews and sends it themselves.

    Only the evaluation's narrative summary is passed in — never the per-competency
    judgments or the score, which are internal decision-support artifacts.
    """
    extra = f"\n\nAdditional instructions from the recruiter: {notes}" if notes.strip() else ""
    return provider.complete(
        instructions=EMAIL_SYSTEM,
        context=f"Job description:\n{jd_text}",
        user_text=(
            f"Email type: {EMAIL_KIND_LABELS[kind]}.\n"
            f"Role: {job_title}.\n"
            f"Candidate: {candidate_name}.\n"
            f"Internal notes on the profile (do not quote or disclose): {evaluation.summary}"
            f"{extra}\n\nDraft this email."
        ),
        schema=EmailDraft,
    )
