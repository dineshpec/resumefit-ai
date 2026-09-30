"""Upload checks: extension allow-list, size cap, and content signature."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from typing import Literal

FileType = Literal["pdf", "docx", "txt"]

MAX_UPLOAD_BYTES = 2 * 1024 * 1024

_EXTENSIONS: dict[str, FileType] = {".pdf": "pdf", ".docx": "docx", ".txt": "txt"}
_PDF_SIGNATURE = b"%PDF-"
_ZIP_SIGNATURE = b"PK\x03\x04"
_UTF8_BOM = b"\xef\xbb\xbf"


class UploadProblem(StrEnum):
    UNSUPPORTED_TYPE = "unsupported_type"
    TOO_LARGE = "too_large"
    MISMATCH = "mismatch"
    BAD_ENCODING = "bad_encoding"


@dataclass(frozen=True)
class UploadCheck:
    ok: bool
    file_type: FileType | None = None
    problem: UploadProblem | None = None


def validate_upload(filename: str, data: bytes) -> UploadCheck:
    """Accept a PDF, DOCX, or UTF-8 text file whose content matches its name."""
    file_type = _EXTENSIONS.get(PurePath(filename).suffix.lower())
    if file_type is None:
        return _rejected(UploadProblem.UNSUPPORTED_TYPE)
    if len(data) > MAX_UPLOAD_BYTES:
        return _rejected(UploadProblem.TOO_LARGE)
    problem = _signature_problem(file_type, data)
    if problem is not None:
        return _rejected(problem)
    return UploadCheck(ok=True, file_type=file_type)


def _signature_problem(file_type: FileType, data: bytes) -> UploadProblem | None:
    if file_type == "pdf":
        return None if data.startswith(_PDF_SIGNATURE) else UploadProblem.MISMATCH
    if file_type == "docx":
        return None if data.startswith(_ZIP_SIGNATURE) else UploadProblem.MISMATCH
    if data.startswith((_PDF_SIGNATURE, _ZIP_SIGNATURE)) or b"\x00" in data:
        return UploadProblem.MISMATCH
    try:
        data.removeprefix(_UTF8_BOM).decode("utf-8")
    except UnicodeDecodeError:
        return UploadProblem.BAD_ENCODING
    return None


def _rejected(problem: UploadProblem) -> UploadCheck:
    return UploadCheck(ok=False, problem=problem)
