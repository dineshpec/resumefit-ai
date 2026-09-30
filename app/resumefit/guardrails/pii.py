"""Contact-detail redaction applied before any text leaves the application."""

import re
from dataclasses import dataclass

_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"
)
_URL_TAIL = r"(?:[^\s<>\"'()\[\]]*[^\s<>\"'()\[\].,;:!?])?"
_URL = re.compile(
    r"(?:\bhttps?://|\bwww\.)"
    + _URL_TAIL
    + r"|\b(?:[a-z0-9-]+\.)+(?:com|org|io|dev|me|co|in|ai|app)/"
    + _URL_TAIL,
    re.IGNORECASE,
)
_PHONE_CANDIDATE = re.compile(r"(?<![\w+/.])\+?\(?\d[\d \t().-]{6,24}\d(?![\w/])")
_PHONE_DIGITS = range(9, 16)
_PIN_CODE = re.compile(
    r"\b(PIN(?:[ \t]*code)?|Pincode)([ \t]*[:-]?[ \t]*)\d{3}[ \t]?\d{3}\b",
    re.IGNORECASE,
)
_ADDRESS = re.compile(
    r"\b\d{1,5}[A-Za-z]?,?[ \t]+(?:[A-Z][\w.'-]*,?[ \t]+){0,5}?"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Nagar|Marg)\b"
)


@dataclass(frozen=True)
class RedactedText:
    text: str
    counts: dict[str, int]


def redact(text: str) -> RedactedText:
    """Replace emails, phone numbers, URLs, and street addresses with placeholders."""
    counts = {"email": 0, "phone": 0, "url": 0, "address": 0}

    def placeholder(kind: str, label: str) -> str:
        counts[kind] += 1
        return label

    def phone(match: re.Match[str]) -> str:
        digits = sum(character.isdigit() for character in match.group())
        if digits not in _PHONE_DIGITS:
            return match.group()
        return placeholder("phone", "[PHONE]")

    text = _EMAIL.sub(lambda _: placeholder("email", "[EMAIL]"), text)
    text = _URL.sub(lambda _: placeholder("url", "[URL]"), text)
    text = _PHONE_CANDIDATE.sub(phone, text)
    text = _PIN_CODE.sub(
        lambda match: (
            match.group(1) + match.group(2) + placeholder("address", "[ADDRESS]")
        ),
        text,
    )
    text = _ADDRESS.sub(lambda _: placeholder("address", "[ADDRESS]"), text)
    return RedactedText(text=text, counts=counts)
