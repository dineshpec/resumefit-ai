"""Pydantic models: model-facing structured outputs and the published report.

The model-facing classes use only plain field types (no defaults, dictionaries,
or numeric constraints) so OpenAI strict structured output accepts them; every
count, range, and rubric rule is checked afterwards by ``report.finalize_report``.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["1.0"] = "1.0"

Seniority = Literal[
    "intern", "junior", "mid", "senior", "lead", "principal", "unspecified"
]
JudgedCriterion = Literal[
    "relevant_experience", "responsibilities_alignment", "education_certifications"
]


class ExperienceEntry(BaseModel):
    title: str
    organization: str
    years: float | None
    highlights: list[str]


class EducationEntry(BaseModel):
    qualification: str
    institution: str
    year: str | None


class ProjectEntry(BaseModel):
    name: str
    summary: str
    skills: list[str]


class CandidateProfile(BaseModel):
    skills: list[str]
    experience: list[ExperienceEntry]
    education: list[EducationEntry]
    projects: list[ProjectEntry]
    total_years_experience: float | None


class JobRequirements(BaseModel):
    role_title: str
    seniority: Seniority
    must_have: list[str]
    nice_to_have: list[str]
    min_years_experience: float | None
    responsibilities: list[str]


class CriterionJudgement(BaseModel):
    criterion: JudgedCriterion
    awarded: int
    rationale: str


class MatchAssessment(BaseModel):
    matched_skills: list[str]
    missing_must_have: list[str]
    missing_nice_to_have: list[str]
    judgements: list[CriterionJudgement]


class BulletSuggestion(BaseModel):
    original: str | None
    improved: str
    targets_requirement: str


class InterviewQuestion(BaseModel):
    question: str
    reason: str


class LearningItem(BaseModel):
    skill: str
    actions: list[str]
    estimated_weeks: int


class CoachingPlan(BaseModel):
    improved_bullets: list[BulletSuggestion]
    interview_questions: list[InterviewQuestion]
    learning_plan: list[LearningItem]


class ReportDraft(BaseModel):
    summary: str
    candidate: CandidateProfile
    job: JobRequirements
    assessment: MatchAssessment
    coaching: CoachingPlan


class ReportMeta(BaseModel):
    """Facts about the analysis run that the model never supplies."""

    generated_at: datetime
    support_id: str
    model: str


class RubricLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    max_points: int
    awarded: int
    rationale: str
    computed: bool


class MatchReport(BaseModel):
    """The published download contract; renaming or removing a field needs a new version."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    generated_at: datetime
    support_id: str
    model: str
    overall_score: int = Field(ge=0, le=100)
    rubric: list[RubricLine]
    summary: str
    candidate: CandidateProfile
    job: JobRequirements
    assessment: MatchAssessment
    coaching: CoachingPlan
    redactions: dict[str, int]
