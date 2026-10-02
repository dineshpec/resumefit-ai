"""MCP tools gateway: the application's only client of the tools service.

The pipeline calls ``extract_resume_text`` and ``render_pdf`` itself, so raw
resume text and binary content never pass through a model, and it calls
``normalize_skills`` to check the coverage score. Agents receive only the
``normalize_skills`` adapter, bound to this gateway's own session.
"""

import asyncio
import base64
import json
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Protocol

from autogen_core.tools import BaseTool
from autogen_ext.tools.mcp import (
    McpWorkbench,
    StreamableHttpServerParams,
    create_mcp_server_session,
    mcp_server_tools,
)
from mcp import ClientSession

AGENT_TOOL_NAMES = frozenset({"normalize_skills"})
DEFAULT_TIMEOUT_S = 30.0
NORMALIZE_BATCH = 100  # the tool's own per-call limit


class ToolsUnavailable(Exception):
    """The tools service could not be reached or answered with a protocol error."""


@dataclass(frozen=True)
class ExtractResult:
    ok: bool
    file_type: str | None
    text: str = field(repr=False)
    pages: int | None
    truncated: bool
    error_code: str | None


class ToolsGatewayProtocol(Protocol):
    """What the pipeline needs from the tools service; tests substitute an in-memory one."""

    async def __aenter__(self) -> "ToolsGatewayProtocol": ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def extract_resume_text(
        self, filename: str, data: bytes
    ) -> ExtractResult: ...

    async def render_pdf(self, markdown: str, title: str) -> bytes | None: ...

    async def normalize_skills(self, skills: list[str]) -> dict[str, str]: ...

    async def skill_tools(self) -> list[BaseTool[Any, Any]]: ...


class ToolsGateway:
    """One ``McpWorkbench`` and one agent-tool session, opened and closed together.

    Both live in a dedicated owner task. The MCP client's anyio task groups cancel
    their host task when a transport task fails (for example a refused connection);
    hosting them in the owner task keeps that cancellation away from the caller, so
    it surfaces as ``ToolsUnavailable`` while a cancellation of the caller itself
    still propagates as ``CancelledError`` after the owner task has finished.
    """

    def __init__(self, url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._params = StreamableHttpServerParams(
            url=url, timeout=timeout_s, sse_read_timeout=timeout_s
        )
        self._owner: asyncio.Task[None] | None = None
        self._closing = asyncio.Event()
        self._workbench: McpWorkbench | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "ToolsGateway":
        ready: asyncio.Future[tuple[ClientSession, McpWorkbench]] = (
            asyncio.get_running_loop().create_future()
        )
        self._closing = asyncio.Event()
        owner = asyncio.create_task(self._hold_connection(ready, self._closing))
        waiting: set[asyncio.Future[Any]] = {ready, owner}
        try:
            await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            await _finish(owner, self._closing, cancel=True)
            raise
        if not ready.done():
            error = await _finish(owner, self._closing, cancel=True)
            raise ToolsUnavailable("tools service unavailable") from error
        self._session, self._workbench = ready.result()
        self._owner = owner
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        owner, self._owner = self._owner, None
        self._workbench = self._session = None
        if owner is not None:
            await _finish(owner, self._closing, cancel=False)

    async def _hold_connection(
        self,
        ready: "asyncio.Future[tuple[ClientSession, McpWorkbench]]",
        closing: asyncio.Event,
    ) -> None:
        async with AsyncExitStack() as stack:
            # The session is opened first: its initialize call proves the service is
            # reachable before the workbench starts its background connection.
            session = await stack.enter_async_context(
                create_mcp_server_session(self._params)
            )
            await session.initialize()
            workbench = await stack.enter_async_context(McpWorkbench(self._params))
            ready.set_result((session, workbench))
            await closing.wait()

    async def extract_resume_text(self, filename: str, data: bytes) -> ExtractResult:
        result = await self._call(
            "extract_resume_text",
            {
                "filename": filename,
                "content_base64": base64.b64encode(data).decode("ascii"),
            },
        )
        if result.get("ok") is True:
            return ExtractResult(
                ok=True,
                file_type=_optional_str(result.get("file_type")),
                text=str(result.get("text", "")),
                pages=_optional_int(result.get("pages")),
                truncated=bool(result.get("truncated", False)),
                error_code=None,
            )
        return ExtractResult(
            ok=False,
            file_type=None,
            text="",
            pages=None,
            truncated=False,
            error_code=str(result.get("error_code", "unreadable")),
        )

    async def render_pdf(self, markdown: str, title: str) -> bytes | None:
        """Return the PDF bytes, or ``None`` when the service reports an expected error."""
        result = await self._call("render_pdf", {"markdown": markdown, "title": title})
        if result.get("ok") is not True:
            return None
        try:
            return base64.b64decode(str(result["pdf_base64"]), validate=True)
        except (KeyError, ValueError):
            return None

    async def normalize_skills(self, skills: list[str]) -> dict[str, str]:
        """Map each skill name to its canonical name, keyed by the input as sent."""
        canonical: dict[str, str] = {}
        for start in range(0, len(skills), NORMALIZE_BATCH):
            payload = await self._call_json(
                "normalize_skills", {"skills": skills[start : start + NORMALIZE_BATCH]}
            )
            if isinstance(payload, dict):
                payload = payload.get("result")
            if not isinstance(payload, list):
                raise ToolsUnavailable("normalize_skills returned an unexpected shape")
            for item in payload:
                if isinstance(item, dict):
                    name, value = item.get("input"), item.get("canonical")
                    if isinstance(name, str) and isinstance(value, str):
                        canonical[name] = value
        return canonical

    async def skill_tools(self) -> list[BaseTool[Any, Any]]:
        if self._session is None:
            raise ToolsUnavailable("tools gateway is not open")
        try:
            tools = await mcp_server_tools(self._params, session=self._session)
        except Exception as error:
            raise ToolsUnavailable("tools service unavailable") from error
        return [tool for tool in tools if tool.name in AGENT_TOOL_NAMES]

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = await self._call_json(name, arguments)
        if not isinstance(payload, dict):
            raise ToolsUnavailable(f"{name} returned an unexpected shape")
        return payload

    async def _call_json(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._workbench is None:
            raise ToolsUnavailable("tools gateway is not open")
        try:
            result = await self._workbench.call_tool(name, arguments)
        except Exception as error:
            raise ToolsUnavailable(f"{name} failed") from error
        if result.is_error:
            raise ToolsUnavailable(f"{name} failed")
        try:
            payload = json.loads(result.to_text())
        except ValueError as error:
            raise ToolsUnavailable(f"{name} returned malformed content") from error
        return payload


async def _finish(
    owner: asyncio.Task[None], closing: asyncio.Event, *, cancel: bool
) -> BaseException | None:
    """Stop the owner task and wait until it has closed the session and workbench.

    Returns how the owner ended (a transport error while closing is not actionable).
    If the caller is cancelled meanwhile, the owner is cancelled too and still awaited
    before the caller's ``CancelledError`` is re-raised.
    """
    closing.set()
    if cancel:
        owner.cancel()
    interrupted: asyncio.CancelledError | None = None
    while not owner.done():
        try:
            await asyncio.wait({owner})
        except asyncio.CancelledError as error:
            interrupted = error
            owner.cancel()
    if interrupted is not None:
        raise interrupted
    if owner.cancelled():
        return asyncio.CancelledError()
    return owner.exception()


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
