import pytest
from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import (
    ModelClientStreamingChunkEvent,
    StructuredMessage,
    TextMessage,
    ThoughtEvent,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
    ToolCallSummaryMessage,
)
from autogen_core import FunctionCall
from autogen_core.models import FunctionExecutionResult
from pipeline_fakes import (
    candidate_profile,
    coaching_plan,
    job_requirements,
    match_assessment,
    report_draft,
)

from resumefit.agents.timeline import SYSTEM, system_entry, to_entry
from resumefit.outcomes import TimelineEntry

RESUME_TEXT = "Jane Example, senior engineer at Example Corp since 2019"


def tool_request(arguments: str, source: str = "resume_parser") -> ToolCallRequestEvent:
    return ToolCallRequestEvent(
        source=source,
        content=[
            FunctionCall(id="call-1", name="normalize_skills", arguments=arguments)
        ],
    )


def tool_result(content: str, is_error: bool = False) -> ToolCallExecutionEvent:
    return ToolCallExecutionEvent(
        source="resume_parser",
        content=[
            FunctionExecutionResult(
                content=content,
                name="normalize_skills",
                call_id="call-1",
                is_error=is_error,
            )
        ],
    )


def test_timeline_hides_task_message_and_summarises_tool_calls() -> None:
    task = TextMessage(source="user", content=RESUME_TEXT)
    request = tool_request('{"skills": ["js", "python", "k8s"]}')
    result = tool_result(
        '[{"input": "js", "canonical": "JavaScript", "category": "language"},'
        ' {"input": "python", "canonical": "Python", "category": "language"},'
        ' {"input": "k8s", "canonical": "Kubernetes", "category": "platform"}]'
    )

    assert to_entry(task) is None
    assert to_entry(request) == TimelineEntry(
        "Resume Parser", "tool_call", "Calls normalize_skills with 3 skills"
    )
    assert to_entry(result) == TimelineEntry(
        "Resume Parser", "tool_result", "normalize_skills returned 3 results"
    )


def test_tool_result_from_the_mcp_adapter_is_counted_from_its_text_content() -> None:
    adapter_output = (
        '[{"type": "text", "text": "[{\\"input\\": \\"js\\", \\"canonical\\": '
        '\\"JavaScript\\", \\"category\\": \\"language\\"}]", "annotations": null}]'
    )

    entry = to_entry(tool_result(adapter_output))

    assert entry is not None
    assert entry.summary == "normalize_skills returned 1 results"


def test_failed_tool_call_is_reported_as_failed_without_its_error_text() -> None:
    entry = to_entry(tool_result("Traceback: secret path C:/app/x.py", is_error=True))

    assert entry == TimelineEntry(
        "Resume Parser", "tool_result", "normalize_skills failed"
    )


def test_unparseable_tool_arguments_still_give_a_tool_call_entry() -> None:
    entry = to_entry(tool_request("not json"))

    assert entry == TimelineEntry(
        "Resume Parser", "tool_call", "Calls normalize_skills"
    )


def test_orchestrator_message_becomes_a_delegation_with_display_name() -> None:
    message = TextMessage(
        source="orchestrator",
        content="NEXT: matcher\nBoth profiles are ready for comparison.",
    )

    assert to_entry(message) == TimelineEntry(
        "Orchestrator",
        "delegation",
        "Delegates to Matcher — Both profiles are ready for comparison.",
    )


def test_orchestrator_message_naming_no_known_agent_does_not_echo_the_name() -> None:
    message = TextMessage(source="orchestrator", content="NEXT: <script>x</script>")

    entry = to_entry(message)

    assert entry is not None
    assert entry.kind == "delegation"
    assert "script" not in entry.summary


@pytest.mark.parametrize(
    ("source", "content", "summary"),
    [
        (
            "resume_parser",
            candidate_profile(),
            "Profile: 4 skills, 2 roles, 1 education entries",
        ),
        (
            "jd_analyst",
            job_requirements(),
            "Requirements: 3 must-have, 2 nice-to-have skills",
        ),
        (
            "matcher",
            match_assessment(),
            "Assessment: 3 matched skills, 1 missing must-have",
        ),
        (
            "coach",
            coaching_plan(),
            "Coaching: 3 bullets, 5 questions, 1 learning items",
        ),
        ("report_writer", report_draft(), "Report draft ready"),
    ],
)
def test_specialist_structured_output_is_summarised_with_counts_only(
    source: str, content: object, summary: str
) -> None:
    message_type = StructuredMessage[type(content)]  # type: ignore[misc]
    message = message_type(source=source, content=content)

    entry = to_entry(message)

    assert entry is not None
    assert (entry.agent, entry.kind, entry.summary) == (
        {
            "resume_parser": "Resume Parser",
            "jd_analyst": "JD Analyst",
            "matcher": "Matcher",
            "coach": "Coach",
            "report_writer": "Report Writer",
        }[source],
        "output",
        summary,
    )


@pytest.mark.parametrize(
    "event",
    [
        ToolCallSummaryMessage(
            source="resume_parser", content=RESUME_TEXT, tool_calls=[], results=[]
        ),
        ThoughtEvent(source="matcher", content=RESUME_TEXT),
        ModelClientStreamingChunkEvent(source="coach", content=RESUME_TEXT),
        TextMessage(source="coach", content=RESUME_TEXT),
        TaskResult(messages=[], stop_reason="done"),
    ],
)
def test_other_events_are_not_shown(event: object) -> None:
    assert to_entry(event) is None


def test_system_entries_use_the_system_agent_name() -> None:
    assert system_entry("status", "Request accepted") == TimelineEntry(
        SYSTEM, "status", "Request accepted"
    )
