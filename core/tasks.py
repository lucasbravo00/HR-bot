"""Recruiting tasks, written once against the provider interface.

Each task is a prompt + a schema. Engines are interchangeable underneath, so a new
capability never has to be implemented twice.
"""

from .models import (
    AnonymizedResume,
    CandidateEvaluation,
    EmailDraft,
    EmailKind,
    InterviewKit,
    Rubric,
)
from .prompts import (
    ANONYMIZE_SYSTEM,
    EMAIL_SYSTEM,
    EVAL_INSTRUCTIONS,
    INTERVIEW_KIT_SYSTEM,
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


def generate_interview_kit(
    provider: LLMProvider,
    jd_text: str,
    rubric: Rubric,
    evaluation: CandidateEvaluation,
    score: float,
    missing_must_haves: list[str],
) -> InterviewKit:
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
