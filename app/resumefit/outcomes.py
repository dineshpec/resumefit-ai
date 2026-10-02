"""Shared outcome types: the analysis request, timeline entries, outcomes, and failures.

Visitor messages come only from the fixed catalogue below, so no exception text,
path, or configuration value can reach the page.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from resumefit.report import sanitize_text
from resumefit.schemas import MatchReport

MAX_TIMELINE_SUMMARY_CHARS = 200

TimelineKind = Literal["delegation", "tool_call", "tool_result", "output", "status"]


class FailureCategory(StrEnum):
    INVALID_FILE = "invalid_file"
    INVALID_JOB_DESCRIPTION = "invalid_job_description"
    SUSPICIOUS_INPUT = "suspicious_input"
    OFF_TOPIC = "off_topic"
    CONTENT_POLICY = "content_policy"
    SERVICE_UNAVAILABLE = "service_unavailable"
    ALREADY_RUNNING = "already_running"
    BUSY = "busy"
    DAILY_BUDGET = "daily_budget"
    QUOTA = "quota"
    LIMIT_REACHED = "limit_reached"
    REPORT_INVALID = "report_invalid"
    INTERNAL = "internal"


FAILURE_LABELS: dict[FailureCategory, str] = {
    FailureCategory.INVALID_FILE: "Invalid file",
    FailureCategory.INVALID_JOB_DESCRIPTION: "Invalid job description",
    FailureCategory.SUSPICIOUS_INPUT: "Suspicious input",
    FailureCategory.OFF_TOPIC: "Off-topic input",
    FailureCategory.CONTENT_POLICY: "Content policy",
    FailureCategory.SERVICE_UNAVAILABLE: "Service unavailable",
    FailureCategory.ALREADY_RUNNING: "Already running",
    FailureCategory.BUSY: "Service busy",
    FailureCategory.DAILY_BUDGET: "Daily service limit reached",
    FailureCategory.QUOTA: "Daily quota used",
    FailureCategory.LIMIT_REACHED: "Safety limit reached",
    FailureCategory.REPORT_INVALID: "Report invalid",
    FailureCategory.INTERNAL: "Internal error",
}

_MESSAGES: dict[FailureCategory, str] = {
    FailureCategory.INVALID_FILE: (
        "We could not accept this file. Please upload a PDF, DOCX, or plain-text resume "
        "of at most 7 MB."
    ),
    FailureCategory.INVALID_JOB_DESCRIPTION: "Paste a job description of 200–10,000 characters.",
    FailureCategory.SUSPICIOUS_INPUT: (
        "Your input contains text that looks like instructions to the AI. "
        "Please remove it and try again."
    ),
    FailureCategory.OFF_TOPIC: "This does not look like a resume and a job description.",
    FailureCategory.CONTENT_POLICY: "The content cannot be processed under our content policy.",
    FailureCategory.SERVICE_UNAVAILABLE: "A required service is unavailable; please try again later.",
    FailureCategory.ALREADY_RUNNING: (
        "You already have an analysis in progress. Please wait for it to finish."
    ),
    FailureCategory.BUSY: "The service is busy right now. Please try again in a few minutes.",
    FailureCategory.DAILY_BUDGET: (
        "The service has reached its analysis limit for today. It resets at 00:00 UTC."
    ),
    FailureCategory.QUOTA: "You have used all of today's analyses. Your quota resets at 00:00 UTC.",
    FailureCategory.LIMIT_REACHED: (
        "The analysis hit its safety limit; please try again with shorter input."
    ),
    FailureCategory.REPORT_INVALID: (
        "We could not produce a reliable report this time. Please try again."
    ),
    FailureCategory.INTERNAL: "Something went wrong on our side. Please try again later.",
}

# Reason codes are the upload problems, extraction error codes, text problems,
# and input names produced by the guard functions and the tools service.
_REASON_MESSAGES: dict[FailureCategory, dict[str, str]] = {
    FailureCategory.INVALID_FILE: {
        "unsupported_type": "Please upload a PDF, DOCX, or plain-text (.txt) resume.",
        "mismatch": (
            "The file content does not match its extension. "
            "Please upload a genuine PDF, DOCX, or text file."
        ),
        "too_large": "Resume files can be at most 7 MB.",
        "bad_encoding": "Text files must be UTF-8 encoded.",
        "too_many_pages": "PDFs can have at most 5 pages.",
        "archive_too_large": "This DOCX file is too large or complex to process.",
        "archive_unsafe": "This DOCX file contains encrypted or embedded content we cannot process.",
        "unreadable": "We could not read this file. It may be damaged, encrypted, or image-only.",
        "timeout": "We could not read this file in time.",
        "too_short": "The resume must contain at least 300 characters of readable text.",
        "too_long": "The resume can contain at most 20,000 characters of text.",
    },
    FailureCategory.INVALID_JOB_DESCRIPTION: {
        "too_short": "The job description is too short. Paste 200–10,000 characters.",
        "too_long": "The job description is too long. Paste 200–10,000 characters.",
    },
    FailureCategory.SUSPICIOUS_INPUT: {
        "resume": (
            "Your resume contains text that looks like instructions to the AI. "
            "Please remove it and try again."
        ),
        "job_description": (
            "Your job description contains text that looks like instructions to the AI. "
            "Please remove it and try again."
        ),
    },
    FailureCategory.OFF_TOPIC: {
        "resume": "This does not look like a resume.",
        "job_description": "This does not look like a job description.",
    },
}


def failure_message(
    category: FailureCategory, support_id: str, reason: str | None = None
) -> str:
    """Return the fixed visitor message for a failure, ending with the support ID."""
    text = _REASON_MESSAGES.get(category, {}).get(reason or "", _MESSAGES[category])
    return f"{text} Support ID: {support_id}"


def failure_reasons(category: FailureCategory) -> tuple[str, ...]:
    """Reason codes that have a more specific message for this category."""
    return tuple(_REASON_MESSAGES.get(category, {}))


@dataclass(frozen=True)
class AnalysisRequest:
    filename: str
    file_bytes: bytes = field(repr=False)
    job_description: str = field(repr=False)
    visitor: str
    support_id: str


@dataclass(frozen=True)
class TimelineEntry:
    """One visible progress step; the summary is sanitised and at most 200 characters."""

    agent: str
    kind: TimelineKind
    summary: str

    def __post_init__(self) -> None:
        summary = sanitize_text(self.summary)[:MAX_TIMELINE_SUMMARY_CHARS]
        object.__setattr__(self, "summary", summary)


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class AnalysisSuccess:
    support_id: str
    report: MatchReport
    markdown: str
    json: str
    pdf: bytes | None
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True)
class AnalysisFailure:
    support_id: str
    failure: FailureCategory
    message: str
    usage: TokenUsage = TokenUsage()


AnalysisOutcome = AnalysisSuccess | AnalysisFailure
