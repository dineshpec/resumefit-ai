import pytest

from resumefit.guardrails.uploads import (
    MAX_UPLOAD_BYTES,
    UploadProblem,
    validate_upload,
)

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
DOCX = b"PK\x03\x04" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
TEXT = b"Experience\nSoftware engineer since 2019.\n"


@pytest.mark.parametrize(
    ("filename", "data", "file_type"),
    [
        ("resume.pdf", PDF, "pdf"),
        ("resume.docx", DOCX, "docx"),
        ("resume.txt", TEXT, "txt"),
        ("RESUME.PDF", PDF, "pdf"),
        ("resume.txt", b"\xef\xbb\xbf" + TEXT, "txt"),
    ],
)
def test_allowed_type_with_matching_signature_is_accepted(filename, data, file_type):
    check = validate_upload(filename, data)

    assert check.ok
    assert check.file_type == file_type
    assert check.problem is None


def test_zip_renamed_to_pdf_is_rejected_as_mismatch():
    check = validate_upload("resume.pdf", DOCX)

    assert not check.ok
    assert check.problem is UploadProblem.MISMATCH


@pytest.mark.parametrize(
    ("filename", "data", "problem"),
    [
        ("photo.png", PNG, UploadProblem.UNSUPPORTED_TYPE),
        ("resume", TEXT, UploadProblem.UNSUPPORTED_TYPE),
        ("resume.exe.doc", DOCX, UploadProblem.UNSUPPORTED_TYPE),
        ("resume.docx", PDF, UploadProblem.MISMATCH),
        ("resume.pdf", PNG, UploadProblem.MISMATCH),
        ("resume.txt", PDF, UploadProblem.MISMATCH),
        ("resume.txt", b"Skills\x00\x00binary", UploadProblem.MISMATCH),
        ("resume.txt", "Café résumé".encode("latin-1"), UploadProblem.BAD_ENCODING),
        ("resume.pdf", b"", UploadProblem.MISMATCH),
    ],
)
def test_bad_upload_is_rejected_with_specific_problem(filename, data, problem):
    check = validate_upload(filename, data)

    assert not check.ok
    assert check.file_type is None
    assert check.problem is problem


def test_file_of_exactly_two_mebibytes_is_accepted():
    data = PDF + b"0" * (MAX_UPLOAD_BYTES - len(PDF))

    assert MAX_UPLOAD_BYTES == 2_097_152
    assert validate_upload("resume.pdf", data).ok


def test_file_one_byte_over_two_mebibytes_is_rejected_as_too_large():
    data = PDF + b"0" * (MAX_UPLOAD_BYTES + 1 - len(PDF))

    check = validate_upload("resume.pdf", data)

    assert not check.ok
    assert check.problem is UploadProblem.TOO_LARGE
