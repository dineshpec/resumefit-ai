import io
import os
from pathlib import Path

import pytest
from pypdf import PdfReader

from resumefit_tools.pdf_render import (
    MAX_MARKDOWN_CHARS,
    FontFiles,
    MarkdownTooLarge,
    fonts_from_env,
    render_pdf,
)

HEADINGS = [
    "Overall score",
    "Rubric",
    "Summary",
    "Matched and missing skills",
    "Improved resume bullets",
    "Interview questions",
    "Learning plan",
]

SAMPLE_REPORT = """# ResumeFit AI match report

## Overall score

**72 / 100** – a solid match for the role.

## Rubric

| Criterion | Awarded |
| --- | --- |
| Must\\-have skills | 30 / 40 |

## Summary

The candidate’s “platform” work fits; the résumé mentions नमस्ते once.

## Matched and missing skills

- Python
• Kubernetes
* Missing: Terraform

## Improved resume bullets

1. Cut deployment time by 40% with GitHub Actions \\(CI\\/CD\\)

## Interview questions

- How would you design a zero\\_downtime migration?

## Learning plan

- Terraform: finish the official tutorial within 2 weeks.
"""


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def test_rendered_pdf_contains_every_section_heading() -> None:
    text = pdf_text(render_pdf(SAMPLE_REPORT, "ResumeFit AI report"))

    for heading in HEADINGS:
        assert heading in text
    assert "72 / 100" in text


def test_markdown_markers_and_escapes_are_not_printed() -> None:
    text = pdf_text(render_pdf(SAMPLE_REPORT, "ResumeFit AI report"))

    assert "**" not in text
    assert "##" not in text
    assert "Must-have skills" in text
    assert "(CI/CD)" in text
    assert "zero_downtime" in text
    assert "| --- |" not in text


def test_typographic_characters_are_transliterated_and_other_scripts_become_question_marks() -> (
    None
):
    text = pdf_text(render_pdf(SAMPLE_REPORT, "ResumeFit AI report"))

    assert "72 / 100 - a solid match" in text
    assert 'candidate\'s "platform" work' in text
    assert "résumé" in text
    assert "?????" in text
    assert "नमस्ते" not in text


def test_very_long_unbroken_text_still_renders() -> None:
    data = render_pdf("## Links\n\n" + "x" * 5_000, "Report")

    assert data.startswith(b"%PDF-")


def test_oversize_markdown_is_rejected_as_too_large() -> None:
    render_pdf("a" * MAX_MARKDOWN_CHARS, "Report")

    with pytest.raises(MarkdownTooLarge):
        render_pdf("a" * (MAX_MARKDOWN_CHARS + 1), "Report")


UNICODE_FONTS = fonts_from_env(os.environ)
needs_unicode_fonts = pytest.mark.skipif(
    UNICODE_FONTS is None,
    reason="no Unicode font: install fonts-dejavu-core or set PDF_FONT_REGULAR/BOLD",
)


def test_fonts_are_used_only_when_both_files_exist(tmp_path: Path) -> None:
    regular, bold = tmp_path / "regular.ttf", tmp_path / "bold.ttf"
    environ = {"PDF_FONT_REGULAR": str(regular), "PDF_FONT_BOLD": str(bold)}

    regular.write_bytes(b"font")
    assert fonts_from_env(environ) is None

    bold.write_bytes(b"font")
    assert fonts_from_env(environ) == FontFiles(regular, bold)


@needs_unicode_fonts
def test_a_unicode_font_keeps_non_latin_characters() -> None:
    markdown = "# Отчёт — résumé\n\n- Ελληνικά and “quotes” for José Müller\n"

    text = pdf_text(render_pdf(markdown, "Отчёт", UNICODE_FONTS))

    assert "Отчёт — résumé" in text
    assert "Ελληνικά" in text
    assert "“quotes” for José Müller" in text
    assert "?" not in text
