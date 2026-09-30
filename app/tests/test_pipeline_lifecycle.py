"""Every analysis closes its model client and tools gateway exactly once and frees its lease."""

import asyncio
from typing import Any

import pytest
from pipeline_fakes import (
    FIXED_NOW,
    JOB_DESCRIPTION,
    MODEL_INFO,
    RESUME_TEXT,
    CountingClient,
    CountingHangingClient,
    FakeModerator,
    InMemoryToolsGateway,
    team_script,
)

from resumefit.adapters.tools_gateway import ToolsUnavailable
from resumefit.config import Settings
from resumefit.limits import AdmissionLease, UsageLimiter
from resumefit.outcomes import (
    AnalysisFailure,
    AnalysisRequest,
    AnalysisSuccess,
    FailureCategory,
    TimelineEntry,
)
from resumefit.pipeline import PipelineDeps, run_analysis

VISITOR = "visitor-a"


class Lifecycle:
    def __init__(
        self,
        client: CountingClient,
        gateway: InMemoryToolsGateway | None = None,
        timeout_s: str = "180",
        hard_timeout_margin_s: float = 15.0,
    ) -> None:
        self.client = client
        self.gateway = gateway or InMemoryToolsGateway()
        self.entries: list[TimelineEntry] = []
        self.team_started = asyncio.Event()
        settings = Settings.from_env(
            {"OPENAI_API_KEY": "test-key", "ANALYSIS_TIMEOUT_SECONDS": timeout_s}
        )
        self.limiter = UsageLimiter(5, 200, 3)
        self.deps = PipelineDeps(
            settings=settings,
            limiter=self.limiter,
            tools_factory=lambda: self.gateway,
            moderator=FakeModerator(),
            model_client_factory=lambda: self.client,
            clock=lambda: FIXED_NOW,
            hard_timeout_margin_s=hard_timeout_margin_s,
        )

    def record(self, entry: TimelineEntry) -> None:
        self.entries.append(entry)
        if entry.summary == "Starting agent team":
            self.team_started.set()

    async def run(self) -> Any:
        return await run_analysis(
            AnalysisRequest(
                filename="resume.txt",
                file_bytes=RESUME_TEXT.encode(),
                job_description=JOB_DESCRIPTION,
                visitor=VISITOR,
                support_id="RF-LIFECYC1",
            ),
            self.deps,
            self.record,
        )

    def assert_cleaned_up(self) -> None:
        assert (self.gateway.entered, self.gateway.exited) == (1, 1)
        assert self.client.close_calls == 1
        lease = self.limiter.try_admit(VISITOR, FIXED_NOW)
        assert isinstance(lease, AdmissionLease)
        lease.release()


async def assert_no_task_left(before: set[asyncio.Task[Any]]) -> None:
    await asyncio.sleep(0.2)
    leftover = asyncio.all_tasks() - before - {asyncio.current_task()}
    assert leftover == set()


async def test_model_client_and_gateway_closed_after_success() -> None:
    before = asyncio.all_tasks()
    lifecycle = Lifecycle(CountingClient(team_script(), model_info=MODEL_INFO))

    outcome = await lifecycle.run()

    assert isinstance(outcome, AnalysisSuccess)
    lifecycle.assert_cleaned_up()
    await assert_no_task_left(before)


async def test_model_client_and_gateway_closed_on_timeout_and_cancellation() -> None:
    before = asyncio.all_tasks()
    timed_out = Lifecycle(
        CountingHangingClient(team_script()[:3], model_info=MODEL_INFO),
        timeout_s="1",
        hard_timeout_margin_s=0.5,
    )

    outcome = await asyncio.wait_for(timed_out.run(), timeout=10)

    assert isinstance(outcome, AnalysisFailure)
    assert outcome.failure is FailureCategory.LIMIT_REACHED
    timed_out.assert_cleaned_up()

    cancelled = Lifecycle(
        CountingHangingClient(team_script()[:3], model_info=MODEL_INFO)
    )
    task = asyncio.create_task(cancelled.run())
    await asyncio.wait_for(cancelled.team_started.wait(), timeout=10)
    await asyncio.sleep(0.2)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    cancelled.assert_cleaned_up()
    await assert_no_task_left(before)


async def test_model_client_and_gateway_closed_when_the_gateway_raises() -> None:
    before = asyncio.all_tasks()
    lifecycle = Lifecycle(
        CountingClient(team_script(), model_info=MODEL_INFO),
        gateway=InMemoryToolsGateway(extract_error=ToolsUnavailable("down")),
    )

    outcome = await lifecycle.run()

    assert isinstance(outcome, AnalysisFailure)
    assert outcome.failure is FailureCategory.SERVICE_UNAVAILABLE
    lifecycle.assert_cleaned_up()
    await assert_no_task_left(before)


async def test_model_client_and_gateway_closed_when_the_team_errors() -> None:
    before = asyncio.all_tasks()
    lifecycle = Lifecycle(CountingClient(team_script()[:4], model_info=MODEL_INFO))

    outcome = await lifecycle.run()

    assert isinstance(outcome, AnalysisFailure)
    assert outcome.failure is FailureCategory.SERVICE_UNAVAILABLE
    lifecycle.assert_cleaned_up()
    await assert_no_task_left(before)
