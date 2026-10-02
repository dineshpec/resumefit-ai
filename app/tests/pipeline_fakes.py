"""Offline test doubles for the agent team and the analysis pipeline.

The OpenAI boundary is replaced by AutoGen's official ``ReplayChatCompletionClient``;
the tools service by an in-memory gateway with the same three methods as
``ToolsGateway``; moderation by a recording fake.
"""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autogen_core import FunctionCall
from autogen_core.models import CreateResult, ModelInfo, RequestUsage
from autogen_core.tools import BaseTool, FunctionTool
from autogen_ext.models.replay import ReplayChatCompletionClient

from resumefit.adapters.tools_gateway import ExtractResult
from resumefit.guardrails.moderation import ModerationUnavailable, ModerationVerdict
from resumefit.schemas import (
    BulletSuggestion,
    CandidateProfile,
    CoachingPlan,
    CriterionJudgement,
    EducationEntry,
    ExperienceEntry,
    InterviewQuestion,
    JobRequirements,
    LearningItem,
    MatchAssessment,
    ProjectEntry,
    ReportDraft,
)

FIXTURES = Path(__file__).parent / "fixtures"
RESUME_TEXT = (FIXTURES / "legitimate_samples" / "resume_backend.txt").read_text(
    encoding="utf-8"
)
JOB_DESCRIPTION = (FIXTURES / "legitimate_samples" / "jd_backend.txt").read_text(
    encoding="utf-8"
)
CONTACT_DETAILS = (
    "asha.example@example.com",
    "+91 98765 43210",
    "98765 43210",
    "linkedin.com/in/asha-example-000",
)
# Phrases that appear only in the inputs; they must never reach logs or the timeline.
FIXTURE_PHRASES = (
    "Asha Example",
    "Example Payments",
    "ledger service",
    "Payments Platform",
    *CONTACT_DETAILS,
)

MODEL_INFO = ModelInfo(
    vision=False,
    function_calling=True,
    json_output=True,
    family="gpt-4o",
    structured_output=True,
)
FIXED_NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def candidate_profile() -> CandidateProfile:
    return CandidateProfile(
        skills=["Python", "Go", "PostgreSQL", "Kafka"],
        experience=[
            ExperienceEntry(
                title="Lead Engineer",
                organization="Payments company",
                years=5,
                highlights=["Led system design for a high-throughput service."],
            ),
            ExperienceEntry(
                title="Software Engineer",
                organization="Retail company",
                years=3,
                highlights=["Built REST APIs."],
            ),
        ],
        education=[
            EducationEntry(
                qualification="B.Tech Computer Science",
                institution="Institute of Technology",
                year="2016",
            )
        ],
        projects=[
            ProjectEntry(
                name="Contract tests",
                summary="Cut integration defects.",
                skills=["Python"],
            )
        ],
        total_years_experience=8,
    )


def job_requirements() -> JobRequirements:
    return JobRequirements(
        role_title="Senior Backend Engineer",
        seniority="senior",
        must_have=["Python", "PostgreSQL", "Terraform"],
        nice_to_have=["gRPC", "Rust"],
        min_years_experience=6,
        responsibilities=["Operate high-throughput services", "Mentor engineers"],
    )


def match_assessment() -> MatchAssessment:
    return MatchAssessment(
        matched_skills=["Python", "PostgreSQL", "gRPC"],
        missing_must_have=["Terraform"],
        missing_nice_to_have=["Rust"],
        judgements=[
            CriterionJudgement(
                criterion="relevant_experience",
                awarded=20,
                rationale="Eight years of backend work.",
            ),
            CriterionJudgement(
                criterion="responsibilities_alignment",
                awarded=12,
                rationale="Has led design reviews.",
            ),
            CriterionJudgement(
                criterion="education_certifications",
                awarded=4,
                rationale="Relevant degree and cloud certificate.",
            ),
        ],
    )


def coaching_plan(bullets: int = 3) -> CoachingPlan:
    return CoachingPlan(
        improved_bullets=[
            BulletSuggestion(
                original=None,
                improved=f"Delivered measurable outcome number {number}.",
                targets_requirement="Operate high-throughput services",
            )
            for number in range(1, bullets + 1)
        ],
        interview_questions=[
            InterviewQuestion(
                question=f"Question number {number}?", reason="Checks depth."
            )
            for number in range(1, 6)
        ],
        learning_plan=[
            LearningItem(
                skill="Terraform",
                actions=["Complete the official tutorial."],
                estimated_weeks=3,
            )
        ],
    )


def report_draft(bullets: int = 3) -> ReportDraft:
    return ReportDraft(
        summary="A strong backend candidate with one missing must-have skill.",
        candidate=candidate_profile(),
        job=job_requirements(),
        assessment=match_assessment(),
        coaching=coaching_plan(bullets),
    )


def invalid_report_draft() -> ReportDraft:
    """A draft that parses but breaks the bullet-count rule."""
    return report_draft(bullets=1)


def normalize_skills_call(
    skills: Sequence[str] = ("js", "python"), completion_tokens: int = 20
) -> CreateResult:
    return CreateResult(
        finish_reason="function_calls",
        content=[
            FunctionCall(
                id="call-1",
                name="normalize_skills",
                arguments=json.dumps({"skills": list(skills)}),
            )
        ],
        usage=RequestUsage(prompt_tokens=0, completion_tokens=completion_tokens),
        cached=False,
    )


def text_with_usage(content: str, completion_tokens: int) -> CreateResult:
    return CreateResult(
        finish_reason="stop",
        content=content,
        usage=RequestUsage(prompt_tokens=0, completion_tokens=completion_tokens),
        cached=False,
    )


def delegation(agent: str) -> str:
    return f"NEXT: {agent}\nThis specialist's output is needed next."


def team_script(
    report: str | CreateResult | None = None,
) -> list[str | CreateResult]:
    """One model response per call, in the order the hub-and-spoke team makes them."""
    return [
        delegation("resume_parser"),
        normalize_skills_call(),
        candidate_profile().model_dump_json(),
        delegation("jd_analyst"),
        job_requirements().model_dump_json(),
        delegation("matcher"),
        match_assessment().model_dump_json(),
        delegation("coach"),
        coaching_plan().model_dump_json(),
        delegation("report_writer"),
        report if report is not None else report_draft().model_dump_json(),
    ]


def replay_client(
    script: Sequence[str | CreateResult],
) -> ReplayChatCompletionClient:
    return ReplayChatCompletionClient(list(script), model_info=MODEL_INFO)


class HangingReplayClient(ReplayChatCompletionClient):
    """Replays the script, then never answers again (a stuck model call).

    Like the real OpenAI client, the pending call is linked to the caller's
    cancellation token, so cancelling the token cancels the call.
    """

    async def create(self, *args: Any, **kwargs: Any) -> CreateResult:
        if self._current_index >= len(self.chat_completions):
            never: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            token = kwargs.get("cancellation_token")
            if token is not None:
                token.link_future(never)
            await never
        return await super().create(*args, **kwargs)


class CountingClient(ReplayChatCompletionClient):
    """Counts ``close`` calls so lifecycle tests can prove the client is released."""

    close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        await super().close()


class CountingHangingClient(CountingClient, HangingReplayClient):
    pass


def model_messages_text(client: ReplayChatCompletionClient) -> str:
    """Every message the replay client received, as one string."""
    return "\n".join(
        str(message.content)
        for call in client.create_calls
        for message in call["messages"]
    )


def fake_normalize_skills(skills: list[str]) -> str:
    """Map skill names to canonical names (offline stand-in for the MCP tool)."""
    return json.dumps(
        [
            {"input": skill, "canonical": skill.strip().title(), "category": "other"}
            for skill in skills
        ]
    )


def fake_skill_tool() -> FunctionTool:
    return FunctionTool(
        fake_normalize_skills,
        name="normalize_skills",
        description="Map skill names to canonical names.",
    )


@dataclass
class InMemoryToolsGateway:
    """Same methods as ``ToolsGateway``; records every call and its lifecycle."""

    extract_result: ExtractResult | None = None
    extract_error: Exception | None = None
    pdf: bytes | None = b"%PDF-1.4 fake"
    pdf_error: Exception | None = None
    normalize_error: Exception | None = None
    enter_error: Exception | None = None
    calls: list[str] = field(default_factory=list)
    entered: int = 0
    exited: int = 0

    async def __aenter__(self) -> "InMemoryToolsGateway":
        self.entered += 1
        if self.enter_error is not None:
            self.exited += 1
            raise self.enter_error
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.exited += 1

    async def extract_resume_text(self, filename: str, data: bytes) -> ExtractResult:
        self.calls.append("extract_resume_text")
        if self.extract_error is not None:
            raise self.extract_error
        if self.extract_result is not None:
            return self.extract_result
        return ExtractResult(
            ok=True,
            file_type="txt",
            text=data.decode("utf-8"),
            pages=None,
            truncated=False,
            error_code=None,
        )

    async def render_pdf(self, markdown: str, title: str) -> bytes | None:
        self.calls.append("render_pdf")
        if self.pdf_error is not None:
            raise self.pdf_error
        return self.pdf

    async def normalize_skills(self, skills: list[str]) -> dict[str, str]:
        self.calls.append("normalize_skills")
        if self.normalize_error is not None:
            raise self.normalize_error
        return {skill: skill.strip().title() for skill in skills}

    async def skill_tools(self) -> list[BaseTool[Any, Any]]:
        self.calls.append("skill_tools")
        return [fake_skill_tool()]


def extraction_error(code: str) -> ExtractResult:
    return ExtractResult(
        ok=False, file_type=None, text="", pages=None, truncated=False, error_code=code
    )


@dataclass
class FakeModerator:
    flagged: bool = False
    unavailable: bool = False
    calls: list[list[str]] = field(default_factory=list)

    async def check(self, texts: list[str]) -> ModerationVerdict:
        self.calls.append(list(texts))
        if self.unavailable:
            raise ModerationUnavailable("moderation check failed")
        return ModerationVerdict(flagged=self.flagged)
