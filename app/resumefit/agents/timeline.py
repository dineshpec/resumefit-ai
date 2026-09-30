"""Map AutoGen events to visitor-facing timeline entries.

Entries carry counts and names only. The user task message (which holds the
resume), free-text replies, tool-call summaries, thoughts, and streaming chunks
are never shown.
"""

import json
import re

from autogen_agentchat.messages import (
    StructuredMessage,
    TextMessage,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
)
from pydantic import BaseModel

from resumefit.agents.skills import AGENT_ORDER, DISPLAY_NAMES, ORCHESTRATOR
from resumefit.outcomes import TimelineEntry, TimelineKind
from resumefit.schemas import (
    CandidateProfile,
    CoachingPlan,
    JobRequirements,
    MatchAssessment,
    ReportDraft,
)

SYSTEM = "System"
_NEXT_LINE = re.compile(r"^\s*NEXT:\s*([A-Za-z_]+)\s*$", re.MULTILINE)


def system_entry(kind: TimelineKind, summary: str) -> TimelineEntry:
    """An entry emitted by the pipeline itself, from fixed templates only."""
    return TimelineEntry(SYSTEM, kind, summary)


def next_agent(text: str) -> str | None:
    """The agent named on the last ``NEXT:`` line, if it is a known specialist."""
    names = _NEXT_LINE.findall(text)
    if names and names[-1] in AGENT_ORDER:
        return str(names[-1])
    return None


def to_entry(event: object) -> TimelineEntry | None:
    """The timeline entry for one team event, or ``None`` when it must not be shown."""
    if isinstance(event, TextMessage):
        if event.source != ORCHESTRATOR:
            return None
        return TimelineEntry(
            _display(event.source), "delegation", _delegation(event.content)
        )
    if isinstance(event, ToolCallRequestEvent):
        summaries = [_call_summary(call.name, call.arguments) for call in event.content]
        return TimelineEntry(_display(event.source), "tool_call", "; ".join(summaries))
    if isinstance(event, ToolCallExecutionEvent):
        summaries = [
            f"{result.name} failed"
            if result.is_error
            else _result_summary(result.name, result.content)
            for result in event.content
        ]
        return TimelineEntry(
            _display(event.source), "tool_result", "; ".join(summaries)
        )
    if isinstance(event, StructuredMessage) and isinstance(event.content, BaseModel):
        summary = _output_summary(event.content)
        if summary is None:
            return None
        return TimelineEntry(_display(event.source), "output", summary)
    return None


def _display(source: str) -> str:
    return DISPLAY_NAMES.get(source, "Agent")


def _delegation(text: str) -> str:
    agent = next_agent(text)
    if agent is None:
        return "Delegation names no known specialist"
    reason = " ".join(
        line.strip()
        for line in text.splitlines()
        if line.strip() and not _NEXT_LINE.fullmatch(line)
    )
    summary = f"Delegates to {DISPLAY_NAMES[agent]}"
    return f"{summary} — {reason}" if reason else summary


def _call_summary(name: str, arguments: str) -> str:
    try:
        skills = json.loads(arguments).get("skills")
    except (ValueError, AttributeError):
        skills = None
    if isinstance(skills, list):
        return f"Calls {name} with {len(skills)} skills"
    return f"Calls {name}"


def _result_summary(name: str, content: str) -> str:
    count = _result_count(content)
    if count is None:
        return f"{name} returned results"
    return f"{name} returned {count} results"


def _result_count(content: str) -> int | None:
    """Count list items in a tool result: plain JSON, or MCP text content holding JSON."""
    try:
        value = json.loads(content)
    except ValueError:
        return None
    if (
        isinstance(value, list)
        and value
        and all(isinstance(item, dict) and item.get("type") == "text" for item in value)
    ):
        try:
            value = json.loads("".join(str(item.get("text", "")) for item in value))
        except ValueError:
            return None
    if isinstance(value, dict) and isinstance(value.get("result"), list):
        value = value["result"]
    return len(value) if isinstance(value, list) else None


def _output_summary(output: BaseModel) -> str | None:
    if isinstance(output, CandidateProfile):
        return (
            f"Profile: {len(output.skills)} skills, {len(output.experience)} roles, "
            f"{len(output.education)} education entries"
        )
    if isinstance(output, JobRequirements):
        return (
            f"Requirements: {len(output.must_have)} must-have, "
            f"{len(output.nice_to_have)} nice-to-have skills"
        )
    if isinstance(output, MatchAssessment):
        return (
            f"Assessment: {len(output.matched_skills)} matched skills, "
            f"{len(output.missing_must_have)} missing must-have"
        )
    if isinstance(output, CoachingPlan):
        return (
            f"Coaching: {len(output.improved_bullets)} bullets, "
            f"{len(output.interview_questions)} questions, "
            f"{len(output.learning_plan)} learning items"
        )
    if isinstance(output, ReportDraft):
        return "Report draft ready"
    return None
