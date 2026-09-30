"""Run each extraction in a fresh, killable child process with a deadline.

Parsing never happens on the event loop, so the MCP endpoint and `/health`
stay responsive while a hostile file is being parsed. At most
`max_concurrent` children exist at once; a request that cannot get a slot
within `slot_wait_s` is refused as `busy`.
"""

from __future__ import annotations

import asyncio
import math
import multiprocessing
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from multiprocessing.connection import Connection, wait
from typing import Any

from resumefit_tools.extraction import error_result, extract_text

ExtractTarget = Callable[[str, bytes], dict[str, Any]]

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_SLOT_WAIT_S = 10.0
CHILD_MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
KILL_JOIN_TIMEOUT_S = 5.0


def _limit_child_resources(cpu_seconds: int) -> None:
    if sys.platform == "win32":
        return
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (CHILD_MEMORY_LIMIT_BYTES,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def _child_main(
    connection: Connection,
    target: ExtractTarget,
    filename: str,
    data: bytes,
    cpu_seconds: int,
) -> None:
    try:
        _limit_child_resources(cpu_seconds)
        result = target(filename, data)
    except BaseException:
        result = error_result("unreadable")
    connection.send(result)
    connection.close()


@dataclass
class ExtractionRunner:
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    slot_wait_s: float = DEFAULT_SLOT_WAIT_S
    target: ExtractTarget = extract_text
    _slots: asyncio.Semaphore = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._slots = asyncio.Semaphore(self.max_concurrent)

    async def run(self, filename: str, data: bytes) -> dict[str, Any]:
        try:
            await asyncio.wait_for(self._slots.acquire(), self.slot_wait_s)
        except TimeoutError:
            return error_result("busy")
        try:
            return await self._run_in_child(filename, data)
        finally:
            self._slots.release()

    async def _run_in_child(self, filename: str, data: bytes) -> dict[str, Any]:
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        child = context.Process(
            target=_child_main,
            args=(sender, self.target, filename, data, math.ceil(self.timeout_s)),
            daemon=True,
        )
        with receiver:
            try:
                child.start()
            finally:
                sender.close()
            try:
                # Any: the pipe's class differs by platform (Connection / PipeConnection).
                waitables: list[Any] = [receiver, child.sentinel]
                ready = await asyncio.to_thread(wait, waitables, self.timeout_s)
                if receiver not in ready:
                    return error_result("unreadable" if ready else "timeout")
                try:
                    result: dict[str, Any] = receiver.recv()
                except (EOFError, OSError):
                    return error_result("unreadable")
                return result
            finally:
                if child.is_alive():
                    child.kill()
                await asyncio.to_thread(child.join, KILL_JOIN_TIMEOUT_S)


def runner_from_env(environ: Mapping[str, str]) -> ExtractionRunner:
    """Build the runner from the tools service's environment; invalid values fail start-up."""
    timeout_s = float(environ.get("EXTRACTION_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_S))
    max_concurrent = int(
        environ.get("MAX_CONCURRENT_EXTRACTIONS", DEFAULT_MAX_CONCURRENT)
    )
    if not timeout_s > 0 or max_concurrent < 1:
        raise ValueError("extraction timeout and concurrency must be positive")
    return ExtractionRunner(timeout_s=timeout_s, max_concurrent=max_concurrent)
