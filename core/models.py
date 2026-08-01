"""Pydantic schemas shared by rubric extraction, CV evaluation and the UI."""

from typing import Literal

from pydantic import BaseModel

Category = Literal["technical", "soft", "language", "other"]
EvidenceStatus = Literal["evidence_found", "partial_evidence", "no_evidence"]


class Competency(BaseModel):
    name: str
    category: Category
    weight: Literal[1, 2, 3, 4, 5]
    must_have: bool
    evidence_criteria: str


class Rubric(BaseModel):
    job_title: str
    competencies: list[Competency]


class CompetencyEvaluation(BaseModel):
    competency_name: str
    status: EvidenceStatus
    evidence_quotes: list[str]
    reasoning: str


class CandidateEvaluation(BaseModel):
    candidate_name: str
    evaluations: list[CompetencyEvaluation]
    summary: str
