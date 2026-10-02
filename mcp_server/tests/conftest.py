"""Test-time generators for resume files, including hostile ones.

No binary fixtures are committed; every file is built here when a test asks for it.
"""

from __future__ import annotations

import io
import socket
import sys
import zipfile
from pathlib import Path

import pytest
from docx import Document
from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter

MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
if str(MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER_DIR))

SAMPLE_LINE = (
    "Senior Python developer with FastAPI, PostgreSQL and Kubernetes experience."
)

from resumefit_tools.extraction import MAX_DOCX_UNCOMPRESSED_BYTES  # noqa: E402

BEYOND_DOCX_EXPANSION_LIMIT = MAX_DOCX_UNCOMPRESSED_BYTES + 1024 * 1024


class FileFactory:
    """Builds in-memory PDF, DOCX, ZIP, and text files for tests."""

    def pdf(self, pages: int = 1, line: str = SAMPLE_LINE) -> bytes:
        document = FPDF()
        document.set_font("helvetica", size=11)
        for number in range(1, pages + 1):
            document.add_page()
            document.multi_cell(0, 6, f"Page {number}. {line}")
        return bytes(document.output())

    def image_only_pdf(self) -> bytes:
        document = FPDF()
        document.add_page()
        document.image(Image.new("RGB", (60, 30), (200, 30, 30)), x=10, y=10, w=60)
        return bytes(document.output())

    def encrypted_pdf(self) -> bytes:
        writer = PdfWriter()
        for page in PdfReader(io.BytesIO(self.pdf())).pages:
            writer.add_page(page)
        writer.encrypt(user_password="secret", owner_password="owner-secret")
        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def truncated_pdf(self) -> bytes:
        data = self.pdf(pages=2)
        return data[: len(data) // 2]

    def docx(self, with_table: bool = True) -> bytes:
        document = Document()
        document.add_paragraph("Work history: " + SAMPLE_LINE)
        if with_table:
            table = document.add_table(rows=1, cols=2)
            table.cell(0, 0).text = "Skill cell: Terraform"
            table.cell(0, 1).text = "Years cell: 4"
        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    def docx_with_extra_entries(self, entries: dict[str, bytes]) -> bytes:
        buffer = io.BytesIO(self.docx())
        with zipfile.ZipFile(buffer, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return buffer.getvalue()

    def docx_expanding_beyond_limit(self) -> bytes:
        return self.docx_with_extra_entries(
            {"word/media/padding.bin": bytes(BEYOND_DOCX_EXPANSION_LIMIT)}
        )

    def docx_with_entry_count(self, total_entries: int) -> bytes:
        existing = len(zipfile.ZipFile(io.BytesIO(self.docx())).namelist())
        extra = {
            f"padding/entry{index}.xml": b"<x/>"
            for index in range(total_entries - existing)
        }
        return self.docx_with_extra_entries(extra)

    def docx_with_encrypted_entry(self) -> bytes:
        name = "word/media/secret.bin"
        return set_encryption_flag(
            self.docx_with_extra_entries({name: b"hidden"}), name
        )

    def docx_with_nested_archive(self, name: str) -> bytes:
        return self.docx_with_extra_entries({name: self.zip({"inner.txt": b"inner"})})

    def zip(self, entries: dict[str, bytes]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return buffer.getvalue()


def set_encryption_flag(archive_bytes: bytes, entry_name: str) -> bytes:
    """Set the 'encrypted' general-purpose bit for one entry, as a crafted file would."""
    data = bytearray(archive_bytes)
    encoded_name = entry_name.encode()
    for signature, flag_offset, name_offset in (
        (b"PK\x03\x04", 6, 30),
        (b"PK\x01\x02", 8, 46),
    ):
        start = 0
        while (start := data.find(signature, start)) != -1:
            if (
                data[start + name_offset : start + name_offset + len(encoded_name)]
                == encoded_name
            ):
                data[start + flag_offset] |= 0x01
            start += len(signature)
    return bytes(data)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def files() -> FileFactory:
    return FileFactory()
