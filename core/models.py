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


# ------------------------------------------------------------------ job descriptions

class JobDescriptionDraft(BaseModel):
    title: str
    summary: str
    responsibilities: list[str]
    hard_requirements: list[str]
    nice_to_haves: list[str]
    what_we_offer: list[str]

    def to_text(self) -> str:
        """Render as plain text, so a draft can feed straight into rubric extraction."""
        sections = [
            self.title,
            "",
            self.summary,
            "",
            "Responsibilities:",
            *(f"- {item}" for item in self.responsibilities),
            "",
            "Hard requirements:",
            *(f"- {item}" for item in self.hard_requirements),
        ]
        if self.nice_to_haves:
            sections += ["", "Nice to have:", *(f"- {item}" for item in self.nice_to_haves)]
        if self.what_we_offer:
            sections += ["", "What we offer:", *(f"- {item}" for item in self.what_we_offer)]
        return "\n".join(sections)


# ------------------------------------------------------------------ competency matrix

class LevelExpectation(BaseModel):
    level: str
    behavioral_indicator: str


class MatrixCompetency(BaseModel):
    name: str
    category: Category
    definition: str
    levels: list[LevelExpectation]


class CompetencyMatrix(BaseModel):
    role_family: str
    levels: list[str]
    competencies: list[MatrixCompetency]


# ------------------------------------------------------------------ onboarding

class OnboardingMilestone(BaseModel):
    title: str
    description: str
    success_signal: str


class OnboardingPhase(BaseModel):
    period: str
    focus: str
    milestones: list[OnboardingMilestone]


class OnboardingPlan(BaseModel):
    summary: str
    ramp_up_priorities: list[str]
    phases: list[OnboardingPhase]
