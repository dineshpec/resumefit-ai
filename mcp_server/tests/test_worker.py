import asyncio
import base64
import multiprocessing
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any, Self

import httpx2
import pytest
import slow_targets
import uvicorn
from conftest import FileFactory, free_port
from fastmcp import Client

from resumefit_tools import server
from resumefit_tools.worker import ExtractionRunner, runner_from_env


class ChildWatcher:
    """Samples how many worker processes are alive while a test runs."""

    def __init__(self) -> None:
        self.peak = 0
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        self._task = asyncio.create_task(self._sample())
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        self._stop.set()
        assert self._task is not None
        await self._task

    async def _sample(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, len(multiprocessing.active_children()))
            await asyncio.sleep(0.02)


def slow_runner(
    target: Callable[[str, bytes], dict[str, Any]] = slow_targets.never_returns,
    max_concurrent: int = 2,
    timeout_s: float = 1.0,
    slot_wait_s: float = 1.0,
) -> ExtractionRunner:
    return ExtractionRunner(
        timeout_s=timeout_s,
        max_concurrent=max_concurrent,
        slot_wait_s=slot_wait_s,
        target=target,
    )


@pytest.mark.asyncio
async def test_valid_pdf_is_extracted_in_a_worker_process(files: FileFactory) -> None:
    result = await ExtractionRunner().run("resume.pdf", files.pdf(pages=2))

    assert result["ok"] is True
    assert result["pages"] == 2
    assert multiprocessing.active_children() == []


@pytest.mark.asyncio
async def test_slow_extraction_times_out_and_worker_is_killed(
    files: FileFactory,
) -> None:
    started = time.monotonic()

    result = await slow_runner().run("resume.pdf", files.pdf())

    assert result == {"ok": False, "error_code": "timeout"}
    assert time.monotonic() - started < 3
    assert multiprocessing.active_children() == []


@pytest.mark.asyncio
async def test_cancelled_extraction_kills_its_worker(files: FileFactory) -> None:
    runner = slow_runner(timeout_s=30)
    task = asyncio.create_task(runner.run("resume.pdf", files.pdf()))
    await asyncio.sleep(1.0)
    assert len(multiprocessing.active_children()) == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert multiprocessing.active_children() == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [slow_targets.raises_error, slow_targets.exits_abruptly],
    ids=["raises", "exits"],
)
async def test_crashing_worker_is_reported_as_unreadable(
    files: FileFactory, target: Callable[[str, bytes], dict[str, Any]]
) -> None:
    result = await slow_runner(target=target, timeout_s=5).run(
        "resume.pdf", files.pdf()
    )

    assert result == {"ok": False, "error_code": "unreadable"}
    assert multiprocessing.active_children() == []


@pytest.mark.asyncio
async def test_health_answers_while_extraction_hangs(
    files: FileFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server, "extraction_runner", slow_runner(target=slow_targets.hangs_on_slow_file)
    )
    transport = httpx2.ASGITransport(app=server.mcp.http_app(**server.http_options({})))
    slow_file = base64.b64encode(files.pdf()).decode()

    async with Client(server.mcp) as client:
        started = time.monotonic()
        pending = asyncio.create_task(
            client.call_tool(
                "extract_resume_text",
                {"filename": slow_targets.SLOW_FILENAME, "content_base64": slow_file},
            )
        )
        await asyncio.sleep(0.3)
        async with httpx2.AsyncClient(
            transport=transport, base_url="http://mcp:8000"
        ) as http:
            health_started = time.monotonic()
            health = await http.get("/health")
            health_seconds = time.monotonic() - health_started
        assert not pending.done()

        timed_out = await pending
        elapsed = time.monotonic() - started
        valid = await client.call_tool(
            "extract_resume_text",
            {"filename": "resume.pdf", "content_base64": slow_file},
        )

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health_seconds < 1
    assert timed_out.structured_content == {"ok": False, "error_code": "timeout"}
    assert elapsed < 3
    assert valid.structured_content is not None
    assert valid.structured_content["ok"] is True
    assert multiprocessing.active_children() == []


@pytest.fixture
def slow_server_over_http(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve the real HTTP app on a local socket, with a worker that hangs on one file."""
    monkeypatch.setattr(
        server, "extraction_runner", slow_runner(target=slow_targets.hangs_on_slow_file)
    )
    port = free_port()
    http_server = uvicorn.Server(
        uvicorn.Config(
            server.mcp.http_app(**server.http_options({})),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=http_server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while not http_server.started:
            assert thread.is_alive(), "HTTP server stopped during start-up"
            assert time.monotonic() < deadline, "HTTP server did not start"
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}"
    finally:
        http_server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.asyncio
async def test_health_answers_over_http_while_an_http_extraction_hangs(
    slow_server_over_http: str, files: FileFactory
) -> None:
    pdf = base64.b64encode(files.pdf()).decode()

    async with Client(f"{slow_server_over_http}/mcp") as client:
        started = time.monotonic()
        pending = asyncio.create_task(
            client.call_tool(
                "extract_resume_text",
                {"filename": slow_targets.SLOW_FILENAME, "content_base64": pdf},
            )
        )
        await asyncio.sleep(0.3)
        async with httpx2.AsyncClient(base_url=slow_server_over_http) as http:
            health_started = time.monotonic()
            health = await http.get("/health", timeout=5)
            health_seconds = time.monotonic() - health_started
        assert not pending.done()

        timed_out = await pending
        elapsed = time.monotonic() - started
        valid = await client.call_tool(
            "extract_resume_text", {"filename": "resume.pdf", "content_base64": pdf}
        )

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert health_seconds < 1
    assert timed_out.structured_content == {"ok": False, "error_code": "timeout"}
    assert elapsed < 3
    assert valid.structured_content is not None
    assert valid.structured_content["ok"] is True
    assert multiprocessing.active_children() == []


@pytest.mark.asyncio
async def test_at_most_two_extractions_run_at_once(files: FileFactory) -> None:
    runner = slow_runner(max_concurrent=2, timeout_s=1.0, slot_wait_s=1.0)
    data = files.pdf()

    async with ChildWatcher() as watcher:
        results = await asyncio.gather(
            *(runner.run("resume.pdf", data) for _ in range(3))
        )

    codes = sorted(result["error_code"] for result in results)
    assert watcher.peak == 2
    assert codes in (["busy", "timeout", "timeout"], ["timeout", "timeout", "timeout"])
    assert multiprocessing.active_children() == []


@pytest.mark.asyncio
async def test_extraction_is_refused_as_busy_when_no_slot_frees_in_time(
    files: FileFactory,
) -> None:
    runner = slow_runner(max_concurrent=1, timeout_s=3.0, slot_wait_s=0.5)
    data = files.pdf()

    first = asyncio.create_task(runner.run("resume.pdf", data))
    await asyncio.sleep(0.1)
    started = time.monotonic()
    second = await runner.run("resume.pdf", data)
    waited = time.monotonic() - started

    assert second == {"ok": False, "error_code": "busy"}
    assert 0.4 < waited < 1.5
    assert (await first) == {"ok": False, "error_code": "timeout"}


def test_worker_limits_default_to_design_values_and_follow_environment() -> None:
    defaults = runner_from_env({})
    configured = runner_from_env(
        {"EXTRACTION_TIMEOUT_SECONDS": "4.5", "MAX_CONCURRENT_EXTRACTIONS": "1"}
    )

    assert (defaults.timeout_s, defaults.max_concurrent, defaults.slot_wait_s) == (
        10.0,
        2,
        10.0,
    )
    assert (configured.timeout_s, configured.max_concurrent) == (4.5, 1)


@pytest.mark.parametrize(
    "environ",
    [
        {"EXTRACTION_TIMEOUT_SECONDS": "0"},
        {"EXTRACTION_TIMEOUT_SECONDS": "soon"},
        {"MAX_CONCURRENT_EXTRACTIONS": "0"},
    ],
)
def test_invalid_worker_limits_are_refused_at_start_up(environ: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        runner_from_env(environ)
