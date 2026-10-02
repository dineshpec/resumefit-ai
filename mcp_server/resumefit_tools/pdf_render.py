"""Lay out the report's Markdown subset as a PDF.

Supported: `#` headings, bullet and numbered lists, simple pipe tables, and
paragraphs. Bold markers are dropped and backslash escapes are undone.

With a Unicode TrueType font (DejaVu Sans in the container image, or the files
named by `PDF_FONT_REGULAR` and `PDF_FONT_BOLD`), text keeps its own characters;
a character the font has no glyph for is left out. Without one, fpdf2's core
fonts are used: they are Latin-1 only, so typographic characters are
transliterated and any other character becomes `?`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

MAX_MARKDOWN_CHARS = 100_000
MAX_TITLE_CHARS = 200
FONT = "helvetica"
UNICODE_FONT = "unicode"
DEFAULT_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
DEFAULT_REGULAR_FONT = DEFAULT_FONT_DIR / "DejaVuSans.ttf"
DEFAULT_BOLD_FONT = DEFAULT_FONT_DIR / "DejaVuSans-Bold.ttf"
HEADING_SIZES = {1: 18, 2: 14}
BODY_SIZE = 11

TRANSLITERATIONS = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2022": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u2026": "...",
        "\u00a0": " ",
        "\u200b": "",
    }
)
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^[-*+\u2022]\s+(.*)$")
TABLE_RULE = re.compile(r"^\|?\s*:?-{3,}")
EMPHASIS = re.compile(r"(?<!\\)(\*\*|__)")
ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")  # CommonMark: any ASCII punctuation


class MarkdownTooLarge(ValueError):
    """The Markdown exceeds the documented size limit."""


@dataclass(frozen=True)
class FontFiles:
    regular: Path
    bold: Path


def fonts_from_env(environ: Mapping[str, str]) -> FontFiles | None:
    """The Unicode font files to use, or ``None`` when either file is missing."""
    fonts = FontFiles(
        Path(environ.get("PDF_FONT_REGULAR") or DEFAULT_REGULAR_FONT),
        Path(environ.get("PDF_FONT_BOLD") or DEFAULT_BOLD_FONT),
    )
    return fonts if fonts.regular.is_file() and fonts.bold.is_file() else None


def to_latin1(text: str) -> str:
    return (
        text.translate(TRANSLITERATIONS)
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


def _plain(text: str) -> str:
    return ESCAPE.sub(r"\1", EMPHASIS.sub("", text))


def render_pdf(markdown: str, title: str, fonts: FontFiles | None = None) -> bytes:
    """Render with the Unicode ``fonts`` when given, otherwise with Latin-1 core fonts."""
    if len(markdown) > MAX_MARKDOWN_CHARS:
        raise MarkdownTooLarge(len(markdown))
    pdf = FPDF()
    if fonts is not None:
        pdf.add_font(UNICODE_FONT, "", str(fonts.regular))
        pdf.add_font(UNICODE_FONT, "B", str(fonts.bold))
        font, encode = UNICODE_FONT, _keep
    else:
        font, encode = FONT, to_latin1
    pdf.set_title(encode(title[:MAX_TITLE_CHARS]))
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            pdf.ln(3)
            continue
        if TABLE_RULE.match(line):
            continue
        style, size = "", BODY_SIZE
        if heading := HEADING.match(line):
            level = len(heading.group(1))
            style, size, line = "B", HEADING_SIZES.get(level, 12), heading.group(2)
        elif bullet := BULLET.match(line):
            line = "- " + bullet.group(1)
        elif line.startswith("|"):
            line = "   ".join(cell.strip() for cell in line.strip("|").split("|"))
        pdf.set_font(font, style, size)
        pdf.multi_cell(
            0, size * 0.55, encode(_plain(line)), new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )
    return bytes(pdf.output())


def _keep(text: str) -> str:
    return text
