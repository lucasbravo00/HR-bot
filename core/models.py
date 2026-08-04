"""Pydantic schemas shared by every AI task and the UI."""

from typing import Literal

from pydantic import BaseModel

Category = Literal["technical", "soft", "language", "other"]
EvidenceStatus = Literal["evidence_found", "partial_evidence", "no_evidence"]
EmailKind = Literal["invitation", "rejection", "follow_up"]


# ------------------------------------------------------------------ rubric

class Competency(BaseModel):
    name: str
    category: Category
    weight: Literal[1, 2, 3, 4, 5]
    must_have: bool
    evidence_criteria: str


class Rubric(BaseModel):
    job_title: str
    competencies: list[Competency]


# ------------------------------------------------------------------ evaluation

class CompetencyEvaluation(BaseModel):
    competency_name: str
    status: EvidenceStatus
    evidence_quotes: list[str]
    reasoning: str


class CandidateEvaluation(BaseModel):
    candidate_name: str
    evaluations: list[CompetencyEvaluation]
    summary: str


# ------------------------------------------------------------------ blind screening

class AnonymizedResume(BaseModel):
    """Identity split out from the resume body, so the evaluator never sees it."""

    candidate_name: str
    redacted_text: str
    redacted_items: list[str]


# ------------------------------------------------------------------ interview kit

class InterviewQuestion(BaseModel):
    competency_name: str
    question: str
    rationale: str
    what_to_listen_for: str


class InterviewKit(BaseModel):
    executive_summary: str
    focus_areas: list[str]
    questions: list[InterviewQuestion]


# ------------------------------------------------------------------ emails

class EmailDraft(BaseModel):
    subject: str
    body: str
