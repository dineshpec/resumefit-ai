"""MCP tools gateway: the application's only client of the tools service.

The pipeline calls ``extract_resume_text`` and ``render_pdf`` itself, so raw
resume text and binary content never pass through a model. Agents receive only
the ``normalize_skills`` adapter, bound to this gateway's own session.
"""

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

    async def extract_resume_text(self, filename: str, data: bytes) -> ExtractResult: ...

    async def render_pdf(self, markdown: str, title: str) -> bytes | None: ...

    async def skill_tools(self) -> list[BaseTool[Any, Any]]: ...


class ToolsGateway:
    """One ``McpWorkbench`` and one agent-tool session, opened and closed together."""

    def __init__(self, url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._params = StreamableHttpServerParams(
            url=url, timeout=timeout_s, sse_read_timeout=timeout_s
        )
        self._stack: AsyncExitStack | None = None
        self._workbench: McpWorkbench | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "ToolsGateway":
        stack = AsyncExitStack()
        try:
            # The session is opened first: its initialize call proves the service is
            # reachable before the workbench starts its background connection.
            self._session = await stack.enter_async_context(
                create_mcp_server_session(self._params)
            )
            await self._session.initialize()
            self._workbench = await stack.enter_async_context(
                McpWorkbench(self._params)
            )
        except BaseException as error:
            self._workbench = self._session = None
            await _close_quietly(stack)
            if isinstance(error, Exception):
                raise ToolsUnavailable("tools service unavailable") from error
            raise
        self._stack = stack
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        stack, self._stack = self._stack, None
        self._workbench = self._session = None
        if stack is not None:
            await _close_quietly(stack)

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

    async def skill_tools(self) -> list[BaseTool[Any, Any]]:
        if self._session is None:
            raise ToolsUnavailable("tools gateway is not open")
        try:
            tools = await mcp_server_tools(self._params, session=self._session)
        except Exception as error:
            raise ToolsUnavailable("tools service unavailable") from error
        return [tool for tool in tools if tool.name in AGENT_TOOL_NAMES]

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._workbench is None:
            raise ToolsUnavailable("tools gateway is not open")
        result = await self._workbench.call_tool(name, arguments)
        if result.is_error:
            raise ToolsUnavailable(f"{name} failed")
        try:
            payload = json.loads(result.to_text())
        except ValueError as error:
            raise ToolsUnavailable(f"{name} returned malformed content") from error
        if not isinstance(payload, dict):
            raise ToolsUnavailable(f"{name} returned an unexpected shape")
        return payload


async def _close_quietly(stack: AsyncExitStack) -> None:
    """Close the MCP session and workbench; a transport error while closing is not actionable."""
    try:
        await stack.aclose()
    except Exception:
        pass


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
