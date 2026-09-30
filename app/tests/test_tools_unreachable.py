"""An unreachable tools service, driven exactly like the page: ``asyncio.run`` on a plain thread.

These tests are deliberately synchronous: pytest-asyncio's loop setup must not hide
how the MCP client's task-group cancellation behaves under a fresh ``asyncio.run``.
The gateway keeps its default timeout so the connection failure, not the request
timeout, ends the attempt.
"""

import asyncio
import dataclasses
import socket
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import pytest
from pipeline_fakes import (
    FIXED_NOW,
    JOB_DESCRIPTION,
    MODEL_INFO,
    RESUME_TEXT,
    CountingClient,
    FakeModerator,
    team_script,
)

from resumefit.adapters.tools_gateway import ToolsGateway, ToolsUnavailable
from resumefit.config import Settings
from resumefit.limits import AdmissionLease
from resumefit.outcomes import (
    AnalysisFailure,
    AnalysisRequest,
    FailureCategory,
    TimelineEntry,
)
from resumefit.pipeline import build_deps, run_analysis

VISITOR = "visitor-unreachable"
T = TypeVar("T")


def unreachable_url() -> str:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    return f"http://127.0.0.1:{port}/mcp"


def run_like_the_page(main: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run ``asyncio.run(main())`` on a fresh thread and return or re-raise its result."""
    results: list[T] = []
    errors: list[BaseException] = []

    def target() -> None:
        try:
            results.append(asyncio.run(main()))
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=60)
    assert not thread.is_alive(), "asyncio.run did not finish"
    if errors:
        raise errors[0]
    return results[0]


def test_gateway_raises_tools_unavailable_under_asyncio_run() -> None:
    url = unreachable_url()

    async def main() -> None:
        async with ToolsGateway(url):
            pass

    with pytest.raises(ToolsUnavailable):
        run_like_the_page(main)


def test_pipeline_reports_service_unavailable_under_asyncio_run() -> None:
    settings = Settings.from_env(
        {"OPENAI_API_KEY": "test-key", "MCP_URL": unreachable_url()}
    )
    client = CountingClient(team_script(), model_info=MODEL_INFO)
    deps = dataclasses.replace(
        build_deps(settings),
        moderator=FakeModerator(),
        model_client_factory=lambda: client,
        clock=lambda: FIXED_NOW,
    )
    entries: list[TimelineEntry] = []
    request = AnalysisRequest(
        filename="resume.txt",
        file_bytes=RESUME_TEXT.encode(),
        job_description=JOB_DESCRIPTION,
        visitor=VISITOR,
        support_id="RF-UNREACH1",
    )

    async def main() -> Any:
        return await run_analysis(request, deps, entries.append)

    outcome = run_like_the_page(main)

    assert isinstance(outcome, AnalysisFailure)
    assert outcome.failure is FailureCategory.SERVICE_UNAVAILABLE
    assert outcome.message.endswith("Support ID: RF-UNREACH1")
    lease = deps.limiter.try_admit(VISITOR, FIXED_NOW)
    assert isinstance(lease, AdmissionLease)
    lease.release()
    assert deps.limiter.remaining(VISITOR, FIXED_NOW) == (
        settings.daily_analyses_per_visitor
    )


def test_outer_cancellation_while_connecting_still_propagates() -> None:
    url = unreachable_url()
    left_over: list[set[asyncio.Task[Any]]] = []

    async def main() -> None:
        before = asyncio.all_tasks()

        async def connect() -> None:
            async with ToolsGateway(url):
                pass

        task = asyncio.create_task(connect())
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        finally:
            await asyncio.sleep(0.2)
            left_over.append(asyncio.all_tasks() - before)

    with pytest.raises(asyncio.CancelledError):
        run_like_the_page(main)
    assert left_over == [set()]


def test_caller_timeout_while_connecting_still_raises_timeout_error() -> None:
    url = unreachable_url()

    async def main() -> None:
        async with asyncio.timeout(0.3):
            async with ToolsGateway(url):
                pass

    with pytest.raises(TimeoutError):
        run_like_the_page(main)
