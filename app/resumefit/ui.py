"""Streamlit rendering helpers: fixed page text, escaping, timeline, report, downloads.

Every string that came from a visitor or a model passes through ``escape_markdown``
before it reaches ``st.markdown``; no call uses ``unsafe_allow_html``. Failure
messages come only from the fixed catalogue in ``outcomes``.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

import streamlit as st

from resumefit import pipeline
from resumefit.config import Settings
from resumefit.limits import AccessGate
from resumefit.observability import (
    client_identity,
    log_event,
    new_support_id,
    visitor_key,
)
from resumefit.outcomes import (
    FAILURE_LABELS,
    AnalysisFailure,
    AnalysisOutcome,
    AnalysisSuccess,
    TimelineEntry,
    TimelineKind,
)
from resumefit.report import SECTION_HEADINGS
from resumefit.schemas import MatchReport

OPENAI_DATA_POLICY_URL = "https://platform.openai.com/docs/guides/your-data"
PURPOSE = (
    "Upload your resume and paste a job description. A team of AI agents scores "
    "the match out of 100, explains the score, and suggests how to close the gaps."
)
PRIVACY_NOTICE = (
    "**What happens to your data.** Your resume text and the job description are "
    "sent to OpenAI for analysis. Before that, email addresses, phone numbers, "
    "web links, and street addresses are redacted; names and employers are not, "
    "because the analysis needs them. Nothing is stored: your inputs and the "
    "report live only in this browser session until you press **Start over** or "
    "close the tab. OpenAI handles API data under its "
    f"[API data policy]({OPENAI_DATA_POLICY_URL})."
)
ACCESS_PROMPT = "This deployment is private. Enter the access code to continue."
WRONG_CODE_MESSAGE = "That access code is not correct."
LOCKED_MESSAGE = "Too many incorrect access codes. Please try again in 15 minutes."
MISSING_INPUT_MESSAGE = (
    "Please upload a resume and paste a job description, then press Analyse."
)
CONFIG_ERROR_TEXT = "The service is not configured correctly. Please try again later."
PDF_UNAVAILABLE_NOTE = (
    "PDF is unavailable for this report. The on-screen report and the JSON and "
    "Markdown downloads are complete."
)
RESUME_LABEL = "Resume (PDF, DOCX, or TXT; at most 2 MB)"
JOB_DESCRIPTION_LABEL = "Job description (200–10,000 characters)"
JOB_DESCRIPTION_MAX_CHARS = 10_000
RESUME_TYPES = ["pdf", "docx", "txt"]
MAX_UPLOAD_MB = 2
RUNNING_LABEL = "Analysis running…"
COMPLETED_LABEL = "Analysis completed"
FAILED_LABEL = "Analysis failed"

KIND_LABELS: dict[TimelineKind, str] = {
    "delegation": "Delegation",
    "tool_call": "Tool call",
    "tool_result": "Tool result",
    "output": "Output",
    "status": "Status",
}

_ASCII_PUNCTUATION = re.compile(r"([!-/:-@\[-`{-~])")


@dataclass(frozen=True)
class DownloadFile:
    label: str
    data: str | bytes
    file_name: str
    mime: str


def escape_markdown(text: str) -> str:
    """Single-line text whose every ASCII punctuation mark is backslash-escaped.

    This also disables Streamlit's own extensions (``$`` maths, ``:color[...]``,
    ``:emoji:``), so model or visitor text can only ever render as plain text.
    """
    return _ASCII_PUNCTUATION.sub(r"\\\1", " ".join(text.split()))


def visitor_for(
    headers: Mapping[str, str], remote_ip: object, settings: Settings
) -> str:
    """Pseudonymous visitor key from the proxy's trusted header only.

    Streamlit's header mapping exposes only the first value of a repeated
    header, so all values are collected here and a conflict is passed on as an
    absent header, which ``client_identity`` maps to the shared identity.
    """
    wanted = settings.client_ip_header
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        values = list(get_all(wanted))
    else:
        values = [v for k, v in headers.items() if k.lower() == wanted.lower()]
    trusted = {wanted: values[0]} if len(set(values)) == 1 else {}
    ip = remote_ip if isinstance(remote_ip, str) else None
    return visitor_key(
        client_identity(trusted, ip, settings), settings.visitor_hash_secret
    )


def load_deps() -> pipeline.PipelineDeps | None:
    """The process-wide dependencies, or ``None`` after showing a safe message."""
    try:
        return pipeline.default_deps()
    except Exception as exc:
        support_id = new_support_id()
        log_event(
            "app_started",
            level=logging.ERROR,
            support_id=support_id,
            outcome="failure",
            error_type=type(exc).__name__,
        )
        st.error(f"{CONFIG_ERROR_TEXT} Support ID: {support_id}")
        return None


@st.cache_resource(show_spinner=False)
def access_gate(code: str) -> AccessGate:
    """One gate per process, so lockouts hold across browser sessions."""
    return AccessGate(code)


def render_access_form(gate: AccessGate, visitor: str, now: datetime) -> None:
    """Show only the code prompt; mark the session unlocked on the right code."""
    st.markdown(ACCESS_PROMPT)
    with st.form("access_form", clear_on_submit=True):
        code = st.text_input("Access code", type="password")
        submitted = st.form_submit_button("Unlock")
    if not submitted:
        return
    result = gate.attempt(visitor, code, now)
    if result == "ok":
        st.session_state["unlocked"] = True
        st.rerun()
    elif result == "wrong":
        log_event("access_denied", visitor=visitor)
        st.error(WRONG_CODE_MESSAGE)
    else:
        log_event("access_locked", level=logging.WARNING, visitor=visitor)
        st.error(LOCKED_MESSAGE)


def timeline_markdown(entry: TimelineEntry) -> str:
    return (
        f"**{escape_markdown(entry.agent)}** · {KIND_LABELS[entry.kind]}: "
        f"{escape_markdown(entry.summary)}"
    )


def render_timeline(entries: Sequence[TimelineEntry], outcome: AnalysisOutcome) -> None:
    failed = isinstance(outcome, AnalysisFailure)
    with st.status(
        FAILED_LABEL if failed else COMPLETED_LABEL,
        state="error" if failed else "complete",
        expanded=False,
    ):
        for entry in entries:
            st.markdown(timeline_markdown(entry))


def render_failure(outcome: AnalysisFailure) -> None:
    st.error(f"**{FAILURE_LABELS[outcome.failure]}.** {outcome.message}")


def render_report(report: MatchReport) -> None:
    """Show every report section under the same headings as the downloads."""
    for heading, show in zip(SECTION_HEADINGS, _SECTION_RENDERERS, strict=True):
        st.subheader(heading)
        show(report)


def download_files(outcome: AnalysisSuccess) -> list[DownloadFile]:
    stem = f"resumefit-report-{outcome.support_id}"
    files = [
        DownloadFile("Download JSON", outcome.json, f"{stem}.json", "application/json"),
        DownloadFile(
            "Download Markdown", outcome.markdown, f"{stem}.md", "text/markdown"
        ),
    ]
    if outcome.pdf is not None:
        files.append(
            DownloadFile("Download PDF", outcome.pdf, f"{stem}.pdf", "application/pdf")
        )
    return files


def render_downloads(outcome: AnalysisSuccess) -> None:
    for file in download_files(outcome):
        st.download_button(
            file.label,
            data=file.data,
            file_name=file.file_name,
            mime=file.mime,
            on_click="ignore",
            key=f"download_{file.file_name.rsplit('.', 1)[1]}",
        )
    if outcome.pdf is None:
        st.info(PDF_UNAVAILABLE_NOTE)


def _score(report: MatchReport) -> None:
    st.markdown(f"**{report.overall_score} / 100**")
    st.progress(report.overall_score / 100)


def _summary(report: MatchReport) -> None:
    st.markdown(escape_markdown(report.summary))


def _rubric(report: MatchReport) -> None:
    rows = [
        f"| {escape_markdown(line.label)} | {line.awarded} / {line.max_points} "
        f"| {escape_markdown(line.rationale)} |"
        for line in report.rubric
    ]
    st.markdown(
        "\n".join(["| Criterion | Points | Rationale |", "| --- | --- | --- |", *rows])
    )


def _skills(report: MatchReport) -> None:
    assessment = report.assessment
    _bullets(
        [
            f"**Matched:** {_joined(assessment.matched_skills)}",
            f"**Missing must-have:** {_joined(assessment.missing_must_have)}",
            f"**Missing nice-to-have:** {_joined(assessment.missing_nice_to_have)}",
        ]
    )


def _candidate(report: MatchReport) -> None:
    candidate = report.candidate
    _bullets(
        [
            f"**Skills:** {_joined(candidate.skills)}",
            f"**Total experience:** {_years(candidate.total_years_experience)}",
            *(
                f"**Role:** {escape_markdown(entry.title)}, "
                f"{escape_markdown(entry.organization)} ({_years(entry.years)}): "
                f"{_joined(entry.highlights, '; ')}"
                for entry in candidate.experience
            ),
            *(
                f"**Education:** {escape_markdown(entry.qualification)}, "
                f"{escape_markdown(entry.institution)}"
                + (f" \\({escape_markdown(entry.year)}\\)" if entry.year else "")
                for entry in candidate.education
            ),
            *(
                f"**Project:** {escape_markdown(project.name)}: "
                f"{escape_markdown(project.summary)} "
                f"\\(skills: {_joined(project.skills)}\\)"
                for project in candidate.projects
            ),
        ]
    )


def _job(report: MatchReport) -> None:
    job = report.job
    _bullets(
        [
            f"**Role:** {escape_markdown(job.role_title)}",
            f"**Seniority:** {escape_markdown(job.seniority)}",
            f"**Minimum experience:** {_years(job.min_years_experience)}",
            f"**Must-have:** {_joined(job.must_have)}",
            f"**Nice-to-have:** {_joined(job.nice_to_have)}",
            f"**Responsibilities:** {_joined(job.responsibilities, '; ')}",
        ]
    )


def _bullet_suggestions(report: MatchReport) -> None:
    _numbered(
        [
            f"{escape_markdown(bullet.improved)} "
            f"\\(targets: {escape_markdown(bullet.targets_requirement)}\\)"
            + (
                f" Original: {escape_markdown(bullet.original)}"
                if bullet.original
                else ""
            )
            for bullet in report.coaching.improved_bullets
        ]
    )


def _questions(report: MatchReport) -> None:
    _numbered(
        [
            f"{escape_markdown(item.question)} Why: {escape_markdown(item.reason)}"
            for item in report.coaching.interview_questions
        ]
    )


def _learning(report: MatchReport) -> None:
    items = report.coaching.learning_plan
    if not items:
        st.markdown("No missing must-have skills.")
        return
    _bullets(
        [
            f"**{escape_markdown(item.skill)}** \\(about {item.estimated_weeks} "
            f"weeks\\): {_joined(item.actions, '; ')}"
            for item in items
        ]
    )


_SECTION_RENDERERS = (
    _score,
    _summary,
    _rubric,
    _skills,
    _candidate,
    _job,
    _bullet_suggestions,
    _questions,
    _learning,
)


def _bullets(lines: list[str]) -> None:
    st.markdown("\n".join(f"- {line}" for line in lines))


def _numbered(lines: list[str]) -> None:
    st.markdown("\n".join(f"{number}. {line}" for number, line in enumerate(lines, 1)))


def _joined(items: list[str], separator: str = ", ") -> str:
    return separator.join(escape_markdown(item) for item in items) or "None"


def _years(value: float | None) -> str:
    return "not stated" if value is None else f"{value:g} years"
