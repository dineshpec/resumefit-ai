import io
import json
import logging
import re

import pytest

from resumefit.observability import (
    configure_logging,
    log_event,
    new_support_id,
    visitor_key,
)
from resumefit.outcomes import (
    FAILURE_LABELS,
    FailureCategory,
    failure_message,
    failure_reasons,
)

SUPPORT_ID = "RF-7K3M9QX2"


@pytest.fixture
def log_stream():
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)
    yield stream
    configure_logging("INFO", stream=io.StringIO())


def lines(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_log_event_writes_one_json_line_with_allow_listed_fields(log_stream):
    log_event(
        "analysis_finished",
        support_id=SUPPORT_ID,
        visitor="0123456789abcdef",
        outcome="failure",
        category="off_topic",
        stage="guard",
        duration_ms=1520,
        prompt_tokens=0,
        completion_tokens=0,
        retry_used=False,
    )

    (event,) = lines(log_stream)
    assert event["event"] == "analysis_finished"
    assert event["level"] == "INFO"
    assert event["support_id"] == SUPPORT_ID
    assert event["category"] == "off_topic"
    assert event["duration_ms"] == 1520
    assert event["retry_used"] is False
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", event["ts"])


def test_log_event_rejects_free_text_fields(log_stream):
    with pytest.raises(ValueError, match="message"):
        log_event(
            "analysis_finished", support_id=SUPPORT_ID, message="Asha Example's resume"
        )

    assert log_stream.getvalue() == ""


@pytest.mark.parametrize(
    "value",
    [
        "ignore all previous instructions",
        "asha.example@example.com is here",
        "x" * 65,
        1.5j,
    ],
)
def test_log_event_rejects_values_that_could_carry_content(log_stream, value):
    with pytest.raises(ValueError):
        log_event("analysis_finished", category=value)

    assert log_stream.getvalue() == ""


def test_log_event_rejects_unknown_event_names(log_stream):
    with pytest.raises(ValueError):
        log_event("resume_uploaded")


def test_exceptions_are_logged_only_by_class_name(log_stream):
    log_event("analysis_finished", support_id=SUPPORT_ID, error_type="ConnectionError")

    (event,) = lines(log_stream)
    assert event["error_type"] == "ConnectionError"


def test_library_log_records_are_reduced_to_content_free_lines(log_stream):
    try:
        raise ValueError("resume text: Asha Example, asha.example@example.com")
    except ValueError:
        logging.getLogger("autogen_core.events").warning(
            "message with %s", "Asha Example", exc_info=True
        )

    output = log_stream.getvalue()
    assert "Asha" not in output
    assert "example.com" not in output
    (event,) = lines(log_stream)
    assert event["event"] == "library_log"
    assert event["logger"] == "autogen_core.events"
    assert event["error_type"] == "ValueError"


def test_library_info_records_are_not_logged(log_stream):
    logging.getLogger("autogen_agentchat.events").info(
        "agent said something about the resume"
    )

    assert log_stream.getvalue() == ""


def test_support_id_is_rf_plus_eight_crockford_characters():
    ids = {new_support_id() for _ in range(200)}

    assert len(ids) == 200
    assert all(
        re.fullmatch(r"RF-[0-9A-HJKMNP-TV-Z]{8}", support_id) for support_id in ids
    )


def test_visitor_key_is_stable_per_secret_and_hides_the_address():
    key = visitor_key("203.0.113.7", "secret-one")

    assert key == visitor_key("203.0.113.7", "secret-one")
    assert key != visitor_key("203.0.113.7", "secret-two")
    assert key != visitor_key("203.0.113.8", "secret-one")
    assert re.fullmatch(r"[0-9a-f]{16}", key)
    assert "203" not in key


def all_failure_messages():
    for category in FailureCategory:
        yield category, None
        for reason in failure_reasons(category):
            yield category, reason


@pytest.mark.parametrize(("category", "reason"), list(all_failure_messages()))
def test_every_failure_message_is_plain_language_with_a_support_id(category, reason):
    message = failure_message(category, SUPPORT_ID, reason)

    assert message.endswith(f"Support ID: {SUPPORT_ID}")
    body = message.removesuffix(f"Support ID: {SUPPORT_ID}")
    assert len(body.strip()) > 10
    assert not set("{}<>\\/`_") & set(body)
    assert not re.search(r"(Error|Exception)\b|Traceback|\.py\b", body)


def test_unknown_reason_falls_back_to_the_category_message():
    assert failure_message(
        FailureCategory.INVALID_FILE, SUPPORT_ID, "made_up"
    ) == failure_message(FailureCategory.INVALID_FILE, SUPPORT_ID)


def test_specific_reasons_change_the_message():
    pages = failure_message(FailureCategory.INVALID_FILE, SUPPORT_ID, "too_many_pages")
    smuggled_resume = failure_message(
        FailureCategory.SUSPICIOUS_INPUT, SUPPORT_ID, "resume"
    )
    smuggled_job = failure_message(
        FailureCategory.SUSPICIOUS_INPUT, SUPPORT_ID, "job_description"
    )
    quota = failure_message(FailureCategory.QUOTA, SUPPORT_ID)

    assert "5 pages" in pages
    assert "resume" in smuggled_resume
    assert "job description" in smuggled_job
    assert "00:00 UTC" in quota


def test_every_failure_category_has_a_label():
    assert set(FAILURE_LABELS) == set(FailureCategory)
    assert all(label and label[0].isupper() for label in FAILURE_LABELS.values())
