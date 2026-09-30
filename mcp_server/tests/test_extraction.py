import time
from collections.abc import Callable

import pytest
from conftest import SAMPLE_LINE, FileFactory

from resumefit_tools.extraction import MAX_FILE_BYTES, MAX_TEXT_CHARS, extract_text


def test_five_page_pdf_is_accepted_with_its_text_and_page_count(
    files: FileFactory,
) -> None:
    result = extract_text("resume.pdf", files.pdf(pages=5))

    assert result["ok"] is True
    assert result["file_type"] == "pdf"
    assert result["pages"] == 5
    assert result["truncated"] is False
    assert "Page 5." in result["text"]
    assert "Kubernetes" in result["text"]


def test_six_page_pdf_is_rejected_as_too_many_pages(files: FileFactory) -> None:
    assert extract_text("resume.pdf", files.pdf(pages=6)) == {
        "ok": False,
        "error_code": "too_many_pages",
    }


def test_image_only_pdf_yields_empty_text(files: FileFactory) -> None:
    result = extract_text("scan.pdf", files.image_only_pdf())

    assert result["ok"] is True
    assert result["pages"] == 1
    assert result["text"] == ""


def test_docx_paragraphs_and_table_cells_are_extracted(files: FileFactory) -> None:
    result = extract_text("resume.docx", files.docx(with_table=True))

    assert result["ok"] is True
    assert result["file_type"] == "docx"
    assert result["pages"] is None
    assert SAMPLE_LINE in result["text"]
    assert "Skill cell: Terraform" in result["text"]
    assert "Years cell: 4" in result["text"]


def test_utf8_text_with_byte_order_mark_is_extracted() -> None:
    result = extract_text(
        "resume.txt", "\ufeffR\u00e9sum\u00e9 \u2014 Python engineer".encode()
    )

    assert result == {
        "ok": True,
        "file_type": "txt",
        "text": "R\u00e9sum\u00e9 \u2014 Python engineer",
        "pages": None,
        "truncated": False,
    }


def test_long_text_is_truncated_at_the_character_cap() -> None:
    result = extract_text("resume.txt", ("a" * (MAX_TEXT_CHARS + 10)).encode())

    assert result["ok"] is True
    assert len(result["text"]) == MAX_TEXT_CHARS
    assert result["truncated"] is True


def test_file_of_exactly_two_megabytes_is_accepted_and_one_byte_more_is_too_large() -> (
    None
):
    assert extract_text("resume.txt", b"a" * MAX_FILE_BYTES)["ok"] is True
    assert extract_text("resume.txt", b"a" * (MAX_FILE_BYTES + 1)) == {
        "ok": False,
        "error_code": "too_large",
    }


def test_docx_expanding_beyond_limit_is_rejected(files: FileFactory) -> None:
    data = files.docx_expanding_beyond_limit()
    assert len(data) < MAX_FILE_BYTES

    assert extract_text("resume.docx", data) == {
        "ok": False,
        "error_code": "archive_too_large",
    }


def test_docx_with_more_than_five_hundred_entries_is_rejected(
    files: FileFactory,
) -> None:
    assert extract_text("resume.docx", files.docx_with_entry_count(500))["ok"] is True
    assert extract_text("resume.docx", files.docx_with_entry_count(501)) == {
        "ok": False,
        "error_code": "archive_too_large",
    }


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda f: f.docx_with_encrypted_entry(), id="encrypted-entry"),
        pytest.param(
            lambda f: f.docx_with_nested_archive("word/embeddings/a.zip"), id="zip"
        ),
        pytest.param(
            lambda f: f.docx_with_nested_archive("word/embeddings/b.docx"), id="docx"
        ),
        pytest.param(
            lambda f: f.docx_with_nested_archive("word/media/c.bin"), id="zip-bytes"
        ),
    ],
)
def test_docx_with_encrypted_or_nested_entry_is_rejected_as_unsafe(
    files: FileFactory, build: Callable[[FileFactory], bytes]
) -> None:
    data = build(files)

    assert extract_text("resume.docx", data) == {
        "ok": False,
        "error_code": "archive_unsafe",
    }


@pytest.mark.parametrize(
    ("filename", "build", "expected_code"),
    [
        ("resume.pdf", lambda f: f.encrypted_pdf(), "unreadable"),
        ("resume.pdf", lambda f: f.truncated_pdf(), "unreadable"),
        ("resume.docx", lambda f: f.zip({"notes.txt": b"hello"}), "unsupported_type"),
        ("resume.pdf", lambda f: f.zip({"notes.txt": b"hello"}), "unsupported_type"),
        ("resume.docx", lambda f: f.pdf(), "unsupported_type"),
        ("resume.exe", lambda f: f.pdf(), "unsupported_type"),
        ("resume.txt", lambda f: "R\u00e9sum\u00e9".encode("latin-1"), "bad_encoding"),
        ("resume.txt", lambda f: b"skills\x00python", "bad_encoding"),
    ],
    ids=[
        "encrypted-pdf",
        "truncated-pdf",
        "zip-without-word-part",
        "zip-renamed-pdf",
        "pdf-renamed-docx",
        "unsupported-extension",
        "latin1-text",
        "nul-bytes",
    ],
)
def test_hostile_or_mislabelled_file_is_rejected_quickly_with_its_error_code(
    files: FileFactory,
    filename: str,
    build: Callable[[FileFactory], bytes],
    expected_code: str,
) -> None:
    data = build(files)
    started = time.monotonic()

    result = extract_text(filename, data)

    assert result == {"ok": False, "error_code": expected_code}
    assert time.monotonic() - started < 5
