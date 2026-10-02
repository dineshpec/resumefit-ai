import base64
import io
import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx2
import pytest
from conftest import MCP_SERVER_DIR, SAMPLE_LINE, FileFactory, free_port
from fastmcp import Client
from mcp.types import TextContent
from pypdf import PdfReader
from starlette.testclient import TestClient

from resumefit_tools import server
from resumefit_tools.extraction import MAX_FILE_BYTES

EXPECTED_ARGUMENTS = {
    "extract_resume_text": ["content_base64", "filename"],
    "normalize_skills": ["skills"],
    "render_pdf": ["markdown", "title"],
}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


async def call(tool: str, arguments: dict[str, object]) -> Any:
    """Call a tool in-process and return its JSON text content, as any MCP client sees it."""
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, arguments)
    [content] = result.content
    assert isinstance(content, TextContent)
    return json.loads(content.text)


@pytest.fixture
def http_client() -> Iterator[TestClient]:
    app = server.mcp.http_app(**server.http_options({}))
    # 0.0.0.0 keeps the test client's own address out of the allow-list, so only
    # the Host header decides.
    with TestClient(app, base_url="http://0.0.0.0:8000") as client:
        yield client


@pytest.mark.asyncio
async def test_server_lists_exactly_three_tools() -> None:
    async with Client(server.mcp) as client:
        tools = await client.list_tools()

    arguments = {tool.name: sorted(tool.input_schema["properties"]) for tool in tools}
    required = {
        tool.name: sorted(tool.input_schema.get("required", [])) for tool in tools
    }
    assert arguments == EXPECTED_ARGUMENTS
    assert required == EXPECTED_ARGUMENTS


@pytest.mark.asyncio
async def test_extract_tool_returns_text_of_a_valid_pdf(files: FileFactory) -> None:
    result = await call(
        "extract_resume_text",
        {"filename": "resume.pdf", "content_base64": b64(files.pdf(2))},
    )

    assert isinstance(result, dict)
    assert set(result) == {"ok", "file_type", "text", "pages", "truncated"}
    assert result["ok"] is True
    assert result["file_type"] == "pdf"
    assert result["pages"] == 2
    assert result["truncated"] is False
    assert SAMPLE_LINE[:30] in result["text"]


@pytest.mark.asyncio
async def test_extract_tool_returns_error_code_for_six_page_pdf(
    files: FileFactory,
) -> None:
    result = await call(
        "extract_resume_text",
        {"filename": "resume.pdf", "content_base64": b64(files.pdf(6))},
    )

    assert result == {"ok": False, "error_code": "too_many_pages"}


@pytest.mark.asyncio
async def test_extract_tool_rejects_content_that_is_not_base64() -> None:
    result = await call(
        "extract_resume_text",
        {"filename": "resume.txt", "content_base64": "not base64!"},
    )

    assert result == {"ok": False, "error_code": "unreadable"}


@pytest.mark.asyncio
async def test_extract_tool_rejects_oversized_upload_before_parsing() -> None:
    result = await call(
        "extract_resume_text",
        {"filename": "resume.txt", "content_base64": b64(b"a" * (MAX_FILE_BYTES + 1))},
    )

    assert result == {"ok": False, "error_code": "too_large"}


@pytest.mark.asyncio
async def test_normalize_tool_returns_one_entry_per_input_in_order() -> None:
    result = await call("normalize_skills", {"skills": ["JS", "Cobol-ish", "k8s"]})

    assert result == [
        {"input": "JS", "canonical": "JavaScript", "category": "language"},
        {"input": "Cobol-ish", "canonical": "Cobol-ish", "category": "other"},
        {"input": "k8s", "canonical": "Kubernetes", "category": "devops"},
    ]


@pytest.mark.asyncio
async def test_render_pdf_tool_returns_a_readable_pdf() -> None:
    result = await call(
        "render_pdf", {"markdown": "## Summary\n\nScore 72 / 100", "title": "R"}
    )

    assert isinstance(result, dict)
    assert set(result) == {"ok", "pdf_base64"}
    pdf = PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"])))
    assert "Score 72 / 100" in pdf.pages[0].extract_text()


@pytest.mark.asyncio
async def test_render_pdf_tool_rejects_oversize_markdown() -> None:
    result = await call("render_pdf", {"markdown": "a" * 100_001, "title": "R"})

    assert result == {"ok": False, "error_code": "too_large"}


@pytest.mark.asyncio
async def test_render_failure_is_reported_as_render_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_renderer(markdown: str, title: str) -> bytes:
        raise RuntimeError("font table corrupt")

    monkeypatch.setattr(server, "render_markdown_pdf", broken_renderer)

    result = await call("render_pdf", {"markdown": "## Summary", "title": "R"})

    assert result == {"ok": False, "error_code": "render_failed"}


@pytest.mark.asyncio
async def test_unexpected_failure_is_a_tool_error_without_internal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exploding_run(filename: str, data: bytes) -> dict[str, object]:
        raise RuntimeError(r"C:\internal\path secret-detail")

    monkeypatch.setattr(server.extraction_runner, "run", exploding_run)

    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "extract_resume_text",
            {"filename": "resume.txt", "content_base64": b64(b"hello")},
            raise_on_error=False,
        )

    assert result.is_error is True
    assert "secret-detail" not in str(result.content)


@pytest.mark.asyncio
async def test_tool_logs_contain_no_file_content_or_name(
    files: FileFactory, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    await call(
        "extract_resume_text",
        {"filename": "jane-doe-resume.pdf", "content_base64": b64(files.pdf())},
    )

    tool_logs = [r.getMessage() for r in caplog.records if r.name == "resumefit_tools"]
    assert tool_logs == [tool_logs[0]]
    assert "extract_resume_text" in tool_logs[0]
    assert "result=ok" in tool_logs[0]
    assert "jane-doe" not in caplog.text
    assert "Kubernetes" not in caplog.text


def test_health_returns_ok(http_client: TestClient) -> None:
    response = http_client.get("/health", headers={"host": "mcp:8000"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "host", ["mcp:8000", "localhost:8000", "127.0.0.1:8000", "mcp"]
)
def test_internal_and_local_host_headers_are_accepted(
    http_client: TestClient, host: str
) -> None:
    assert http_client.get("/health", headers={"host": host}).status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:8000", "mcp.evil.example"]
)
def test_foreign_host_header_is_rejected(http_client: TestClient, host: str) -> None:
    health = http_client.get("/health", headers={"host": host})
    mcp_call = http_client.post("/mcp", headers={"host": host}, json={})

    assert health.status_code == 421
    assert mcp_call.status_code == 421


def test_allowed_hosts_setting_replaces_the_internal_default() -> None:
    options = server.http_options({"MCP_ALLOWED_HOSTS": "tools.internal:9000, other:1"})
    app = server.mcp.http_app(**options)

    with TestClient(app, base_url="http://0.0.0.0:8000") as client:
        assert (
            client.get("/health", headers={"host": "tools.internal:9000"}).status_code
            == 200
        )
        assert client.get("/health", headers={"host": "mcp:8000"}).status_code == 421


SPAWN_PROBE_DIR = Path(__file__).resolve().parent / "spawn_probe"
SERVER_ONLY_MODULES = {"fastmcp", "uvicorn", "starlette", "resumefit_tools.server"}


@contextmanager
def tools_service_process(extra_environment: dict[str, str]) -> Iterator[str]:
    """Start the service exactly as the image does (`python -m resumefit_tools`)."""
    port = free_port()
    environment = {**os.environ, "PYTHONPATH": str(MCP_SERVER_DIR), **extra_environment}
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "resumefit_tools",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=Path(MCP_SERVER_DIR),
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                if httpx2.get(f"{base_url}/health", timeout=1).status_code == 200:
                    break
            except httpx2.TransportError:
                pass
            assert process.poll() is None, "tools service exited during start-up"
            assert time.monotonic() < deadline, "tools service did not become healthy"
            time.sleep(0.2)
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture
def running_server() -> Iterator[str]:
    with tools_service_process({}) as base_url:
        yield base_url


@pytest.fixture
def probed_server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """The real service, with `spawn_probe/sitecustomize.py` logging child imports."""
    probe_environment = {
        "PYTHONPATH": os.pathsep.join([str(SPAWN_PROBE_DIR), str(MCP_SERVER_DIR)]),
        "RESUMEFIT_SPAWN_PROBE_DIR": str(tmp_path),
    }
    with tools_service_process(probe_environment) as base_url:
        yield base_url, tmp_path


@pytest.mark.asyncio
async def test_extraction_worker_does_not_reimport_the_server(
    probed_server: tuple[str, Path], files: FileFactory
) -> None:
    """A spawn child re-runs the parent's main module unless it is a `__main__`.

    If the service started as `-m resumefit_tools.server`, every extraction child
    would import FastMCP and uvicorn before its 256 MB address-space limit is set.
    """
    base_url, probe_dir = probed_server

    async with Client(f"{base_url}/mcp") as client:
        extracted = await client.call_tool(
            "extract_resume_text",
            {"filename": "resume.pdf", "content_base64": b64(files.pdf())},
        )

    assert extracted.structured_content is not None
    assert extracted.structured_content["ok"] is True
    [child_log] = probe_dir.glob("child-*.log")
    imported = child_log.read_text(encoding="utf-8").split()
    assert imported[0] == "started"
    assert "resumefit_tools.extraction" in imported
    assert SERVER_ONLY_MODULES.isdisjoint(imported), imported


@pytest.mark.asyncio
async def test_server_process_serves_health_and_tools_over_streamable_http(
    running_server: str, files: FileFactory
) -> None:
    async with Client(f"{running_server}/mcp") as client:
        tools = sorted(tool.name for tool in await client.list_tools())
        extracted = await client.call_tool(
            "extract_resume_text",
            {"filename": "resume.pdf", "content_base64": b64(files.pdf())},
        )
        normalized = await client.call_tool("normalize_skills", {"skills": ["js"]})

    assert tools == sorted(EXPECTED_ARGUMENTS)
    assert extracted.structured_content is not None
    assert extracted.structured_content["ok"] is True
    assert normalized.structured_content == {
        "result": [{"input": "js", "canonical": "JavaScript", "category": "language"}]
    }


def mcp_tool_call(arguments: dict[str, object]) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "extract_resume_text", "arguments": arguments},
    }


MCP_HEADERS = {
    "host": "mcp:8000",
    "accept": "application/json, text/event-stream",
    "content-type": "application/json",
}


def test_the_largest_resume_fits_through_the_mcp_http_endpoint(
    http_client: TestClient,
) -> None:
    # Over the MCP SDK's default 4 MiB body cap once base64-encoded.
    body = json.dumps(
        mcp_tool_call(
            {"filename": "resume.txt", "content_base64": b64(b"a" * MAX_FILE_BYTES)}
        )
    )
    assert len(body) > 4 * 1024 * 1024

    response = http_client.post("/mcp", headers=MCP_HEADERS, content=body)

    assert response.status_code == 200
    data = next(
        line.removeprefix("data:")
        for line in response.text.splitlines()
        if line.startswith("data:")
    )
    [content] = json.loads(data)["result"]["content"]
    assert json.loads(content["text"])["ok"] is True


def test_a_body_beyond_the_resume_cap_is_refused_before_parsing(
    http_client: TestClient,
) -> None:
    body = b"x" * (server.MAX_REQUEST_BODY_BYTES + 1)

    response = http_client.post("/mcp", headers=MCP_HEADERS, content=body)

    assert response.status_code == 413
