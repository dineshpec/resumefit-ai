"""Length bounds, instruction-smuggling detection, and plausibility cues."""

import re
import unicodedata
from enum import StrEnum
from functools import cache
from pathlib import Path

RESUME_MIN_CHARS = 300
RESUME_MAX_CHARS = 20_000
JOB_DESCRIPTION_MIN_CHARS = 200
JOB_DESCRIPTION_MAX_CHARS = 10_000
MIN_CUE_GROUPS = 2

_PATTERNS_FILE = Path(__file__).with_name("injection_patterns.txt")
_ZERO_WIDTH = dict.fromkeys(
    map(
        ord,
        "\u00ad\u180e\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff",
    )
)
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")

_RESUME_CUES = (
    r"\b(experience|employment|work history)\b",
    r"\b(education|academic)\b",
    r"\b(skills|competencies)\b",
    r"\bprojects?\b",
    r"\b(certifications?|certificates?|licen[cs]es)\b",
    r"\b(summary|profile|objective)\b",
)
_JOB_DESCRIPTION_CUES = (
    r"\b(responsibilities|duties|what you will do|what you'll do)\b",
    r"\b(requirements|required|must have|must-have)\b",
    r"\bqualifications?\b",
    r"\b(preferred|nice to have|nice-to-have|bonus points)\b",
    r"\babout (the|this) (role|team|job|position)\b",
    r"\bexperience\b",
    r"\b(we are looking|we're looking)\b",
)


class TextProblem(StrEnum):
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"


def normalize_text(text: str) -> str:
    """NFKC-normalise, drop zero-width characters, and collapse spaces and tabs."""
    canonical = unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH)
    return _HORIZONTAL_SPACE.sub(" ", canonical)


def check_resume_length(text: str) -> TextProblem | None:
    return _length_problem(text, RESUME_MIN_CHARS, RESUME_MAX_CHARS)


def check_job_description_length(text: str) -> TextProblem | None:
    return _length_problem(text, JOB_DESCRIPTION_MIN_CHARS, JOB_DESCRIPTION_MAX_CHARS)


def find_smuggling(text: str) -> str | None:
    """Return the name of the first catalogue pattern found in the text, if any."""
    normalized = normalize_text(text)
    for name, pattern in _catalogue():
        if pattern.search(normalized):
            return name
    return None


def looks_like_resume(text: str) -> bool:
    return _cue_groups_found(text, _RESUME_CUES) >= MIN_CUE_GROUPS


def looks_like_job_description(text: str) -> bool:
    return _cue_groups_found(text, _JOB_DESCRIPTION_CUES) >= MIN_CUE_GROUPS


def _length_problem(text: str, minimum: int, maximum: int) -> TextProblem | None:
    length = len(" ".join(normalize_text(text).split()))
    if length < minimum:
        return TextProblem.TOO_SHORT
    if length > maximum:
        return TextProblem.TOO_LONG
    return None


def _cue_groups_found(text: str, cues: tuple[str, ...]) -> int:
    normalized = normalize_text(text).lower()
    return sum(1 for cue in cues if re.search(cue, normalized))


@cache
def _catalogue() -> tuple[tuple[str, re.Pattern[str]], ...]:
    entries = []
    for line in _PATTERNS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, _, expression = line.partition(":")
        flags = re.IGNORECASE | re.MULTILINE | re.DOTALL
        entries.append((name.strip(), re.compile(expression.strip(), flags)))
    return tuple(entries)
