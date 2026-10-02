"""Report finalisation: validation, deterministic scoring, sanitising, and rendering."""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from resumefit.schemas import (
    CriterionJudgement,
    MatchAssessment,
    MatchReport,
    ReportDraft,
    ReportMeta,
    RubricLine,
)

MAX_FIELD_CHARS = 600

SECTION_HEADINGS = (
    "Overall score",
    "Summary",
    "Rubric",
    "Matched and missing skills",
    "Candidate profile",
    "Job requirements",
    "Improved resume bullets",
    "Interview questions",
    "Learning plan",
)

_JUDGED_MAX_POINTS = {
    "relevant_experience": 25,
    "responsibilities_alignment": 15,
    "education_certifications": 5,
}
_MIN_BULLETS, _MAX_BULLETS = 3, 6
_MIN_QUESTIONS, _MAX_QUESTIONS = 5, 8
_MAX_LEARNING_ITEMS_REQUIRED = 5
_MAX_LISTED_SKILLS = 5

_SCRIPT_OR_STYLE = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_HTML_TAG = re.compile(r"</?[A-Za-z!][^>]*>")
_LINK_TARGET = r"\((?:[^()]|\([^()]*\))*\)"
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]" + _LINK_TARGET)
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]" + _LINK_TARGET)
_BARE_URL = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]*://|\bwww\.)(?:[^\s<>\"'()\[\]]*[^\s<>\"'()\[\].,;:!?])?",
    re.IGNORECASE,
)
_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-!|<>~])")


@dataclass(frozen=True)
class SkillEvidence:
    """What the coverage score is checked against: the redacted resume the team saw.

    A required skill is supported when the resume text names it, either directly or
    through one of the candidate's listed skills with the same canonical name, so a
    model talked into reporting no gaps cannot raise the coverage score above what
    the resume shows. ``canonical`` maps skill keys to canonical keys (from the
    ``normalize_skills`` tool); a skill missing from it is its own canonical name.
    """

    resume_text: str = field(repr=False)
    canonical: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_names(
        cls, resume_text: str, canonical_names: Mapping[str, str]
    ) -> "SkillEvidence":
        """Build from ``normalize_skills`` output: skill name -> canonical name."""
        return cls(
            resume_text,
            {
                _skill_key(name): _skill_key(canonical)
                for name, canonical in canonical_names.items()
            },
        )

    def canonical_key(self, skill: str) -> str:
        key = _skill_key(skill)
        return self.canonical.get(key, key)

    def supports(self, skill: str, candidate_skills: list[str]) -> bool:
        target = self.canonical_key(skill)
        spellings = [skill] + [
            other for other in candidate_skills if self.canonical_key(other) == target
        ]
        return any(self._mentions(spelling) for spelling in spellings)

    @cached_property
    def _text(self) -> str:
        return _skill_key(self.resume_text)

    def _mentions(self, skill: str) -> bool:
        key = _skill_key(skill)
        if not key:
            return False
        return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", self._text) is not None


class ReportValidationError(Exception):
    """The draft breaks a report rule; ``reasons`` are fixed sentences for the retry prompt."""

    def __init__(self, reasons: list[str]) -> None:
        super().__init__("report draft failed validation")
        self.reasons = reasons


def sanitize_text(value: str) -> str:
    """Return inert single-line text: no HTML, images, links, URLs, or control characters."""
    text = _SCRIPT_OR_STYLE.sub(" ", value)
    text = _HTML_TAG.sub(" ", text)
    text = _MARKDOWN_IMAGE.sub(" ", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _BARE_URL.sub("[URL]", text)
    text = "".join(
        character
        for character in text
        if character.isspace() or not unicodedata.category(character).startswith("C")
    )
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:MAX_FIELD_CHARS].rstrip()


def finalize_report(
    draft: ReportDraft,
    redactions: dict[str, int],
    meta: ReportMeta,
    evidence: SkillEvidence | None = None,
) -> MatchReport:
    """Sanitise, validate, and score a draft; raise ``ReportValidationError`` when it breaks a rule.

    With ``evidence``, a skill the Matcher reports as covered counts only when the
    resume text names it, and uncounted skills are moved to the missing lists.
    """
    clean = ReportDraft.model_validate(_sanitized(draft.model_dump()))
    reasons = _validation_reasons(clean)
    if reasons:
        raise ReportValidationError(reasons)
    rubric, unsupported_must_have, unsupported_nice_to_have = _rubric(clean, evidence)
    assessment = _corrected_assessment(
        clean.assessment, unsupported_must_have, unsupported_nice_to_have, evidence
    )
    return MatchReport(
        generated_at=meta.generated_at,
        support_id=meta.support_id,
        model=meta.model,
        overall_score=sum(line.awarded for line in rubric),
        rubric=rubric,
        summary=clean.summary,
        candidate=clean.candidate,
        job=clean.job,
        assessment=assessment,
        coaching=clean.coaching,
        redactions=dict(redactions),
    )


def report_json(report: MatchReport) -> str:
    return report.model_dump_json(indent=2)


def render_markdown(report: MatchReport) -> str:
    """Render the report with fixed headings; all report text is Markdown-escaped."""
    candidate, job, assessment, coaching = (
        report.candidate,
        report.job,
        report.assessment,
        report.coaching,
    )
    lines = [
        "# ResumeFit AI match report",
        "",
        f"Support ID: {_md(report.support_id)}. "
        f"Generated: {report.generated_at:%Y-%m-%d %H:%M} UTC. Model: {_md(report.model)}.",
        *_section("Overall score", [f"**{report.overall_score} / 100**"]),
        *_section("Summary", [_md(report.summary)]),
        *_section(
            "Rubric",
            [
                "| Criterion | Points | Rationale |",
                "| --- | --- | --- |",
                *(
                    f"| {_md(line.label)} | {line.awarded} / {line.max_points} | {_md(line.rationale)} |"
                    for line in report.rubric
                ),
            ],
        ),
        *_section(
            "Matched and missing skills",
            [
                f"- **Matched:** {_md_list(assessment.matched_skills)}",
                f"- **Missing must-have:** {_md_list(assessment.missing_must_have)}",
                f"- **Missing nice-to-have:** {_md_list(assessment.missing_nice_to_have)}",
            ],
        ),
        *_section(
            "Candidate profile",
            [
                f"- **Skills:** {_md_list(candidate.skills)}",
                f"- **Total experience:** {_years(candidate.total_years_experience)}",
                *(
                    f"- **Role:** {_md(entry.title)}, {_md(entry.organization)} "
                    f"({_years(entry.years)}): {_md_list(entry.highlights, '; ')}"
                    for entry in candidate.experience
                ),
                *(
                    f"- **Education:** {_md(entry.qualification)}, {_md(entry.institution)}"
                    + (f" ({_md(entry.year)})" if entry.year else "")
                    for entry in candidate.education
                ),
                *(
                    f"- **Project:** {_md(project.name)}: {_md(project.summary)} "
                    f"(skills: {_md_list(project.skills)})"
                    for project in candidate.projects
                ),
            ],
        ),
        *_section(
            "Job requirements",
            [
                f"- **Role:** {_md(job.role_title)}",
                f"- **Seniority:** {_md(job.seniority)}",
                f"- **Minimum experience:** {_years(job.min_years_experience)}",
                f"- **Must-have:** {_md_list(job.must_have)}",
                f"- **Nice-to-have:** {_md_list(job.nice_to_have)}",
                f"- **Responsibilities:** {_md_list(job.responsibilities, '; ')}",
            ],
        ),
        *_section(
            "Improved resume bullets",
            [
                f"{number}. {_md(bullet.improved)} (targets: {_md(bullet.targets_requirement)})"
                + (f" Original: {_md(bullet.original)}" if bullet.original else "")
                for number, bullet in enumerate(coaching.improved_bullets, start=1)
            ],
        ),
        *_section(
            "Interview questions",
            [
                f"{number}. {_md(item.question)} Why: {_md(item.reason)}"
                for number, item in enumerate(coaching.interview_questions, start=1)
            ],
        ),
        *_section(
            "Learning plan",
            [
                f"- **{_md(item.skill)}** (about {item.estimated_weeks} weeks): "
                f"{_md_list(item.actions, '; ')}"
                for item in coaching.learning_plan
            ]
            or ["No missing must-have skills."],
        ),
    ]
    return "\n".join(lines) + "\n"


def _sanitized(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [_sanitized(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitized(item) for key, item in value.items()}
    return value


def _validation_reasons(draft: ReportDraft) -> list[str]:
    reasons = []
    judgements = draft.assessment.judgements
    if sorted(judgement.criterion for judgement in judgements) != sorted(
        _JUDGED_MAX_POINTS
    ):
        reasons.append(
            "The matcher must judge relevant_experience, responsibilities_alignment, and "
            "education_certifications exactly once each."
        )
    for judgement in judgements:
        maximum = _JUDGED_MAX_POINTS[judgement.criterion]
        if not 0 <= judgement.awarded <= maximum:
            reasons.append(f"{judgement.criterion} must award 0 to {maximum} points.")
    if not _MIN_BULLETS <= len(draft.coaching.improved_bullets) <= _MAX_BULLETS:
        reasons.append(f"Provide {_MIN_BULLETS} to {_MAX_BULLETS} improved bullets.")
    if not _MIN_QUESTIONS <= len(draft.coaching.interview_questions) <= _MAX_QUESTIONS:
        reasons.append(
            f"Provide {_MIN_QUESTIONS} to {_MAX_QUESTIONS} interview questions."
        )
    required_items = min(
        len(draft.assessment.missing_must_have), _MAX_LEARNING_ITEMS_REQUIRED
    )
    if len(draft.coaching.learning_plan) < required_items:
        reasons.append(
            f"Provide at least {required_items} learning-plan items, "
            "one per missing must-have skill."
        )
    if not draft.summary:
        reasons.append("Provide a non-empty summary.")
    return reasons


def _rubric(
    draft: ReportDraft, evidence: SkillEvidence | None
) -> tuple[list[RubricLine], list[str], list[str]]:
    """The five rubric lines, plus the must-have and nice-to-have skills not counted."""
    judged: dict[str, CriterionJudgement] = {
        judgement.criterion: judgement for judgement in draft.assessment.judgements
    }

    def judged_line(key: str, label: str) -> RubricLine:
        judgement = judged[key]
        return RubricLine(
            key=key,
            label=label,
            max_points=_JUDGED_MAX_POINTS[key],
            awarded=judgement.awarded,
            rationale=judgement.rationale,
            computed=False,
        )

    candidate_skills = draft.candidate.skills
    must_have, unsupported_must_have = _coverage_line(
        "must_have_skills",
        "Must-have skills",
        40,
        draft.job.must_have,
        draft.assessment.missing_must_have,
        "must-have",
        candidate_skills,
        evidence,
    )
    nice_to_have, unsupported_nice_to_have = _coverage_line(
        "nice_to_have_skills",
        "Nice-to-have skills",
        15,
        draft.job.nice_to_have,
        draft.assessment.missing_nice_to_have,
        "nice-to-have",
        candidate_skills,
        evidence,
    )
    rubric = [
        must_have,
        judged_line("relevant_experience", "Relevant experience"),
        nice_to_have,
        judged_line(
            "responsibilities_alignment", "Responsibilities and domain alignment"
        ),
        judged_line("education_certifications", "Education and certifications"),
    ]
    return rubric, unsupported_must_have, unsupported_nice_to_have


def _coverage_line(
    key: str,
    label: str,
    max_points: int,
    required: list[str],
    missing: list[str],
    kind: str,
    candidate_skills: list[str],
    evidence: SkillEvidence | None,
) -> tuple[RubricLine, list[str]]:
    """Score one coverage line; return it with the claimed skills the resume does not name."""
    canonical = evidence.canonical_key if evidence is not None else _skill_key
    missing_keys = {canonical(skill) for skill in missing}
    claimed = [skill for skill in required if canonical(skill) not in missing_keys]
    unsupported = (
        [skill for skill in claimed if not evidence.supports(skill, candidate_skills)]
        if evidence is not None
        else []
    )
    total = len(required)
    matched = len(claimed) - len(unsupported)
    if total:
        awarded = (2 * max_points * matched + total) // (2 * total)  # round half up
        rationale = f"Matched {matched} of {total} {kind} skills."
        if unsupported:
            rationale += (
                " Not counted because the resume text does not name them: "
                f"{_short_list(unsupported)}."
            )
    else:
        awarded = max_points
        rationale = f"The job lists no {kind} skills."
    line = RubricLine(
        key=key,
        label=label,
        max_points=max_points,
        awarded=awarded,
        rationale=rationale,
        computed=True,
    )
    return line, unsupported


def _short_list(items: list[str]) -> str:
    shown = ", ".join(items[:_MAX_LISTED_SKILLS])
    hidden = len(items) - _MAX_LISTED_SKILLS
    return f"{shown}, and {hidden} more" if hidden > 0 else shown


def _corrected_assessment(
    assessment: MatchAssessment,
    unsupported_must_have: list[str],
    unsupported_nice_to_have: list[str],
    evidence: SkillEvidence | None,
) -> MatchAssessment:
    """Move skills the resume does not name from matched to missing."""
    if evidence is None or not (unsupported_must_have or unsupported_nice_to_have):
        return assessment
    dropped = {
        evidence.canonical_key(skill)
        for skill in (*unsupported_must_have, *unsupported_nice_to_have)
    }
    return assessment.model_copy(
        update={
            "matched_skills": [
                skill
                for skill in assessment.matched_skills
                if evidence.canonical_key(skill) not in dropped
            ],
            "missing_must_have": [
                *assessment.missing_must_have,
                *unsupported_must_have,
            ],
            "missing_nice_to_have": [
                *assessment.missing_nice_to_have,
                *unsupported_nice_to_have,
            ],
        }
    )


def _skill_key(skill: str) -> str:
    return " ".join(skill.split()).casefold()


def _section(heading: str, body: list[str]) -> list[str]:
    return ["", f"## {heading}", "", *body]


def _md(text: str) -> str:
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def _md_list(items: list[str], separator: str = ", ") -> str:
    return separator.join(_md(item) for item in items) or "None"


def _years(value: float | None) -> str:
    return "not stated" if value is None else f"{value:g} years"
