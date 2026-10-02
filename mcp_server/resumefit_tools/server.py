"""FastMCP tools service: extraction, skill normalisation, PDF rendering, and health.

Run with `python -m resumefit_tools [--host HOST] [--port PORT]` (see
`__main__.py` for why not `-m resumefit_tools.server`); the MCP
endpoint is `/mcp` (streamable HTTP, stateless) and `GET /health` answers
`{"status": "ok"}`.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import logging
import os
import time
from collections.abc import Mapping
from typing import Any

from fastmcp import FastMCP
from fastmcp.server import http as fastmcp_http
from mcp.server.transport_security import RequestBodyLimitMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from resumefit_tools.extraction import MAX_FILE_BYTES, error_result
from resumefit_tools.pdf_render import MarkdownTooLarge, fonts_from_env
from resumefit_tools.pdf_render import render_pdf as render_markdown_pdf
from resumefit_tools.taxonomy import NormalizedSkill
from resumefit_tools.taxonomy import normalize_skills as normalize_skill_names
from resumefit_tools.worker import runner_from_env

DEFAULT_ALLOWED_HOSTS = "mcp:8000,localhost:8000,127.0.0.1:8000"
MAX_BASE64_CHARS = 4 * -(-MAX_FILE_BYTES // 3)
# The largest resume, base64-encoded, plus room for the JSON-RPC envelope.
MAX_REQUEST_BODY_BYTES = MAX_BASE64_CHARS + 1024 * 1024


class ResumeSizedSessionManager(fastmcp_http.FastMCPStreamableHTTPSessionManager):
    """FastMCP's session manager with a request-body cap that fits the largest resume.

    The MCP SDK rejects request bodies over 4 MiB (HTTP 413) unless its session
    manager gets ``max_request_body_size``, which FastMCP 4.0 does not pass on. A
    7 MB file is about 9.4 MB once base64-encoded, so the limit is replaced here.
    ``test_server`` sends a body over 4 MiB, so a library upgrade that breaks this
    fails the tests.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.max_request_body_size = MAX_REQUEST_BODY_BYTES
        self.asgi_app = RequestBodyLimitMiddleware(
            self._handle_request, MAX_REQUEST_BODY_BYTES
        )


fastmcp_http.FastMCPStreamableHTTPSessionManager = ResumeSizedSessionManager  # type: ignore[misc]

logger = logging.getLogger("resumefit_tools")

mcp: FastMCP = FastMCP("resumefit-tools", mask_error_details=True)
extraction_runner = runner_from_env(os.environ)
pdf_fonts = fonts_from_env(os.environ)


def _log_call(tool: str, started: float, result_code: str) -> None:
    """Log only the tool name, duration, and result code; never content or file names."""
    duration_ms = round((time.monotonic() - started) * 1000)
    logger.info("tool=%s result=%s duration_ms=%d", tool, result_code, duration_ms)


def _result_code(result: Mapping[str, Any]) -> str:
    return "ok" if result.get("ok") else str(result.get("error_code"))


@mcp.tool
async def extract_resume_text(filename: str, content_base64: str) -> dict[str, Any]:
    """Extract text from a base64-encoded PDF, DOCX, or UTF-8 text resume (max 7 MB)."""
    started = time.monotonic()
    if len(content_base64) > MAX_BASE64_CHARS:
        result = error_result("too_large")
    else:
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError):
            result = error_result("unreadable")
        else:
            result = await extraction_runner.run(filename, data)
    _log_call("extract_resume_text", started, _result_code(result))
    return result


@mcp.tool
def normalize_skills(skills: list[str]) -> list[NormalizedSkill]:
    """Map skill names to canonical names; at most 100 skills, each cut to 80 characters."""
    started = time.monotonic()
    result = normalize_skill_names(skills)
    _log_call("normalize_skills", started, "ok")
    return result


@mcp.tool
def render_pdf(markdown: str, title: str) -> dict[str, Any]:
    """Render report Markdown (max 100,000 characters) to a base64-encoded PDF."""
    started = time.monotonic()
    try:
        pdf = render_markdown_pdf(markdown, title, pdf_fonts)
    except MarkdownTooLarge:
        result = error_result("too_large")
    except Exception:
        result = error_result("render_failed")
    else:
        result = {"ok": True, "pdf_base64": base64.b64encode(pdf).decode("ascii")}
    _log_call("render_pdf", started, _result_code(result))
    return result


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def http_options(environ: Mapping[str, str]) -> dict[str, Any]:
    """HTTP settings shared by `main` and the tests.

    FastMCP only checks the Host header when protection is switched on;
    `allowed_hosts` alone is ignored. Entries are matched on the host name
    (the port is ignored), and localhost names are always allowed.
    """
    hosts = environ.get("MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS)
    return {
        "stateless_http": True,
        "host_origin_protection": True,
        "allowed_hosts": [host.strip() for host in hosts.split(",") if host.strip()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="ResumeFit AI tools service")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    mcp.run(
        transport="http",
        host=arguments.host,
        port=arguments.port,
        show_banner=False,
        **http_options(os.environ),
    )


if __name__ == "__main__":
    main()
