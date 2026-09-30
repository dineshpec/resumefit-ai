from collections.abc import Sequence

from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import (
    BaseAgentEvent,
    BaseChatMessage,
    StructuredMessage,
    TextMessage,
    ToolCallExecutionEvent,
    ToolCallRequestEvent,
)
from autogen_core.models import SystemMessage
from pipeline_fakes import (
    candidate_profile,
    delegation,
    fake_skill_tool,
    replay_client,
    report_draft,
    team_script,
    text_with_usage,
)

from resumefit.agents.skills import AGENT_ORDER, load_skill
from resumefit.agents.team import (
    DATA_MARKERS,
    build_report_writer,
    build_task,
    build_team,
    select_next_speaker,
)
from resumefit.config import Settings
from resumefit.schemas import CandidateProfile, ReportDraft

Event = BaseAgentEvent | BaseChatMessage


def settings(**overrides: str) -> Settings:
    return Settings.from_env({"OPENAI_API_KEY": "test-key", **overrides})


async def run_team(
    script: Sequence[object], team_settings: Settings | None = None
) -> tuple[list[Event], TaskResult, object]:
    client = replay_client(script)  # type: ignore[arg-type]
    team = build_team(client, [fake_skill_tool()], team_settings or settings())
    events: list[Event] = []
    result: TaskResult | None = None
    async for item in team.run_stream(task=build_task("resume text", "job text")):
        if isinstance(item, TaskResult):
            result = item
        else:
            events.append(item)
    assert result is not None
    return events, result, client


def delegations(events: list[Event]) -> list[str]:
    return [
        event.content.splitlines()[0].removeprefix("NEXT: ")
        for event in events
        if isinstance(event, TextMessage) and event.source == "orchestrator"
    ]


def specialist_outputs(events: list[Event]) -> list[str]:
    return [event.source for event in events if isinstance(event, StructuredMessage)]


async def test_orchestrator_delegates_in_order_and_report_writer_ends_run() -> None:
    events, result, _ = await run_team(team_script())

    assert delegations(events) == list(AGENT_ORDER)
    assert specialist_outputs(events) == list(AGENT_ORDER)
    last = result.messages[-1]
    assert isinstance(last, StructuredMessage)
    assert last.source == "report_writer"
    assert last.content == report_draft()
    assert any(isinstance(event, ToolCallRequestEvent) for event in events)
    assert any(isinstance(event, ToolCallExecutionEvent) for event in events)


async def test_each_agent_speaks_with_its_skill_file_as_system_message() -> None:
    _, _, client = await run_team(team_script())

    system_messages = [
        next(m.content for m in call["messages"] if isinstance(m, SystemMessage))
        for call in client.create_calls  # type: ignore[attr-defined]
    ]

    assert system_messages[0] == load_skill("orchestrator")
    assert system_messages[1] == load_skill("resume_parser")
    assert system_messages[-1] == load_skill("report_writer")


async def test_unknown_next_agent_falls_back_to_next_missing_specialist() -> None:
    script = team_script()
    script[0] = "NEXT: ceo\nThe chief executive should decide."

    events, result, _ = await run_team(script)

    assert specialist_outputs(events) == list(AGENT_ORDER)
    assert isinstance(result.messages[-1], StructuredMessage)


def test_selector_returns_orchestrator_after_any_other_speaker() -> None:
    task = TextMessage(source="user", content="task")
    output = StructuredMessage[CandidateProfile](
        source="resume_parser", content=candidate_profile()
    )

    assert select_next_speaker([task]) == "orchestrator"
    assert select_next_speaker([task, output]) == "orchestrator"


def test_selector_follows_a_known_next_line() -> None:
    messages = [
        TextMessage(source="user", content="task"),
        TextMessage(source="orchestrator", content=delegation("coach")),
    ]

    assert select_next_speaker(messages) == "coach"


def test_selector_skips_specialists_that_already_produced_output() -> None:
    messages = [
        TextMessage(source="user", content="task"),
        TextMessage(source="orchestrator", content=delegation("resume_parser")),
        StructuredMessage[CandidateProfile](
            source="resume_parser", content=candidate_profile()
        ),
        TextMessage(source="orchestrator", content="I think we are done here."),
    ]

    assert select_next_speaker(messages) == "jd_analyst"


async def test_never_ending_conversation_stops_at_the_message_limit() -> None:
    script = [delegation("resume_parser"), candidate_profile().model_dump_json()] * 10

    events, result, _ = await run_team(script, settings(MAX_AGENT_MESSAGES="6"))

    assert len(result.messages) == 6
    assert "report_writer" not in specialist_outputs(events)
    assert result.stop_reason is not None
    assert "Maximum number of messages" in result.stop_reason


async def test_usage_over_the_budget_stops_at_the_token_limit() -> None:
    script = [text_with_usage(delegation("resume_parser"), 150_000), *team_script()]

    events, result, _ = await run_team(script)

    assert specialist_outputs(events) == []
    assert result.stop_reason is not None
    assert "Token usage limit" in result.stop_reason


def test_task_wraps_both_inputs_in_data_markers_and_calls_them_data() -> None:
    task = build_task("RESUME BODY", "JOB BODY")

    resume_start, resume_end, job_start, job_end = DATA_MARKERS
    assert f"{resume_start}\nRESUME BODY\n{resume_end}" in task
    assert f"{job_start}\nJOB BODY\n{job_end}" in task
    assert task.index("untrusted data") < task.index(resume_start)


async def test_standalone_report_writer_returns_a_structured_draft() -> None:
    client = replay_client([report_draft().model_dump_json()])
    writer = build_report_writer(client)

    result = await writer.run(task="Write the report.")

    last = result.messages[-1]
    assert isinstance(last, StructuredMessage)
    assert isinstance(last.content, ReportDraft)
