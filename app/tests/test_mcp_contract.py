"""Cross-process contract test: the application's MCP client against the real tools service.

The tools service runs from its own virtual environment (``.venv-mcp``; override
with ``RESUMEFIT_MCP_PYTHON``) because it needs ``mcp`` 2.x while the application
pins ``mcp`` below 2.
"""

import asyncio
import json
import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from autogen_core import CancellationToken

from resumefit.adapters.tools_gateway import ToolsGateway, ToolsUnavailable
from resumefit.agents.timeline import to_entry

ROOT = Path(__file__).resolve().parents[2]
MCP_SERVER_DIR = ROOT / "mcp_server"
SAMPLE_LINE = "Senior Python developer with FastAPI and Kubernetes experience."


def tools_python() -> Path:
    configured = os.environ.get("RESUMEFIT_MCP_PYTHON")
    if configured:
        return Path(configured)
    if os.name == "nt":
        return ROOT / ".venv-mcp" / "Scripts" / "python.exe"
    return ROOT / ".venv-mcp" / "bin" / "python"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def text_pdf(pages: int, line: str = SAMPLE_LINE) -> bytes:
    """A minimal valid PDF with one line of Helvetica text per page."""
    page_ids = [4 + 2 * index for index in range(pages)]
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids ["
        + b" ".join(f"{page} 0 R".encode() for page in page_ids)
        + f"] /Count {pages} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for number, page in enumerate(page_ids, start=1):
        stream = f"BT /F1 11 Tf 72 720 Td (Page {number}. {line}) Tj ET".encode()
        objects[page] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> "
            + f"/Contents {page + 1} 0 R >>".encode()
        )
        objects[page + 1] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    output = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number in sorted(objects):
        offsets[number] = len(output)
        output += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref_at = len(output)
    size = max(objects) + 1
    output += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for number in range(1, size):
        output += f"{offsets[number]:010d} 00000 n \n".encode()
    output += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(output)


@pytest.fixture(scope="module")
def tools_url() -> Iterator[str]:
    python = tools_python()
    if not python.exists():
        pytest.skip(f"tools-service interpreter not found at {python}")
    port = free_port()
    process = subprocess.Popen(
        [str(python), "-m", "resumefit_tools.server", "--host", "127.0.0.1"]
        + ["--port", str(port)],
        cwd=MCP_SERVER_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            assert process.poll() is None, "tools service exited during start-up"
            assert time.monotonic() < deadline, "tools service did not become healthy"
            time.sleep(0.2)
        yield f"{base_url}/mcp"
    finally:
        process.terminate()
        process.wait(timeout=10)


async def test_gateway_extracts_pdf_text_from_real_tools_service(
    tools_url: str,
) -> None:
    async with ToolsGateway(tools_url) as tools:
        result = await tools.extract_resume_text("resume.pdf", text_pdf(pages=2))

    assert result.ok is True
    assert result.file_type == "pdf"
    assert result.pages == 2
    assert result.truncated is False
    assert result.error_code is None
    assert SAMPLE_LINE[:30] in result.text


async def test_gateway_reports_the_page_limit_error_code_for_a_six_page_pdf(
    tools_url: str,
) -> None:
    async with ToolsGateway(tools_url) as tools:
        result = await tools.extract_resume_text("resume.pdf", text_pdf(pages=6))

    assert result.ok is False
    assert result.error_code == "too_many_pages"
    assert result.text == ""


async def test_gateway_renders_markdown_to_pdf_bytes(tools_url: str) -> None:
    async with ToolsGateway(tools_url) as tools:
        pdf = await tools.render_pdf(
            "# Report\n\n## Overall score\n\n72 / 100\n", "Report"
        )

    assert pdf is not None
    assert pdf.startswith(b"%PDF-")


async def test_gateway_returns_no_pdf_when_the_service_rejects_the_markdown(
    tools_url: str,
) -> None:
    async with ToolsGateway(tools_url) as tools:
        pdf = await tools.render_pdf("x" * 100_001, "Report")

    assert pdf is None


async def test_agents_get_only_normalize_skills_and_it_works_through_the_adapter(
    tools_url: str,
) -> None:
    async with ToolsGateway(tools_url) as tools:
        agent_tools = await tools.skill_tools()
        [tool] = agent_tools
        value = await tool.run_json({"skills": ["JS", "k8s"]}, CancellationToken())
        as_text = tool.return_value_as_string(value)

    assert [tool.name for tool in agent_tools] == ["normalize_skills"]
    [content] = json.loads(as_text)
    canonical = [item["canonical"] for item in json.loads(content["text"])]
    assert canonical == ["JavaScript", "Kubernetes"]


async def test_timeline_counts_results_of_the_real_adapter_output(
    tools_url: str,
) -> None:
    from autogen_agentchat.messages import ToolCallExecutionEvent
    from autogen_core.models import FunctionExecutionResult

    async with ToolsGateway(tools_url) as tools:
        [tool] = await tools.skill_tools()
        value = await tool.run_json(
            {"skills": ["JS", "k8s", "Go"]}, CancellationToken()
        )
        as_text = tool.return_value_as_string(value)
    event = ToolCallExecutionEvent(
        source="matcher",
        content=[
            FunctionExecutionResult(
                content=as_text, name="normalize_skills", call_id="1", is_error=False
            )
        ],
    )

    entry = to_entry(event)

    assert entry is not None
    assert entry.summary == "normalize_skills returned 3 results"


async def test_gateway_closes_its_workbench_and_session_on_exit(
    tools_url: str,
) -> None:
    before = asyncio.all_tasks()
    gateway = ToolsGateway(tools_url)

    async with gateway as tools:
        await tools.render_pdf("# Report\n", "Report")
    await asyncio.sleep(0.1)

    assert asyncio.all_tasks() - before == set()
    with pytest.raises(ToolsUnavailable):
        await gateway.render_pdf("# Report\n", "Report")
    with pytest.raises(ToolsUnavailable):
        await gateway.skill_tools()


async def test_unreachable_tools_service_raises_tools_unavailable() -> None:
    url = f"http://127.0.0.1:{free_port()}/mcp"

    with pytest.raises(ToolsUnavailable):
        async with ToolsGateway(url, timeout_s=2) as tools:
            await tools.extract_resume_text("resume.txt", b"text")
