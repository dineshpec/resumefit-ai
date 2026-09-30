"""Page behaviour through Streamlit's official AppTest harness.

The analysis pipeline is replaced by a fake that emits timeline entries and
returns fixture outcomes, and the process-wide dependencies by in-memory ones,
so no test touches OpenAI or the tools service.
"""

import json
import re
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest
import streamlit as st
from pipeline_fakes import FIXED_NOW, FakeModerator, report_draft
from streamlit.runtime.context import StreamlitHeaders
from streamlit.testing.v1 import AppTest

from resumefit import pipeline, ui
from resumefit.config import ConfigError, Settings
from resumefit.limits import UsageLimiter
from resumefit.observability import visitor_key
from resumefit.outcomes import (
    AnalysisFailure,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisSuccess,
    FailureCategory,
    TimelineEntry,
    failure_message,
)
from resumefit.report import (
    SECTION_HEADINGS,
    finalize_report,
    render_markdown,
    report_json,
)
from resumefit.schemas import MatchReport, ReportMeta

APP_DIR = Path(__file__).resolve().parents[1]
PAGE = APP_DIR / "streamlit_app.py"
CONFIG = APP_DIR / ".streamlit" / "config.toml"
ACCESS_CODE = "open-sesame-42"
SECRET = "ui-test-secret"
RESUME = ("resume.pdf", b"%PDF-1.7 fixture resume bytes", "application/pdf")
JOB_TEXT = "We are hiring a senior backend engineer to build payment services. " * 5
TIMELINE = (
    TimelineEntry("System", "status", "Request accepted"),
    TimelineEntry("Orchestrator", "delegation", "Delegates to Resume Parser"),
    TimelineEntry("Resume Parser", "tool_call", "Calls normalize_skills with 4 skills"),
)
EXCEPTION_TEXT = r"boom at C:\secret\path\settings.py with OPENAI_API_KEY=sk-live"


def plain(markdown: str) -> str:
    """Markdown source with backslash escapes removed, as the visitor reads it."""
    return re.sub(r"\\(.)", r"\1", markdown)


def make_deps(access_code: str = "", limiter: UsageLimiter | None = None):
    settings = Settings.from_env(
        {
            "OPENAI_API_KEY": "sk-test-not-real",
            "APP_ACCESS_CODE": access_code,
            "VISITOR_HASH_SECRET": SECRET,
        }
    )

    def unused() -> None:
        raise AssertionError("the page must not build analysis resources itself")

    return pipeline.PipelineDeps(
        settings=settings,
        limiter=limiter
        or UsageLimiter(per_visitor_daily=5, global_daily=200, max_concurrent=3),
        tools_factory=unused,  # type: ignore[arg-type]
        moderator=FakeModerator(),
        model_client_factory=unused,  # type: ignore[arg-type]
        clock=lambda: FIXED_NOW,
    )


def fixture_report(support_id: str) -> MatchReport:
    meta = ReportMeta(
        generated_at=FIXED_NOW, support_id=support_id, model="gpt-4o-mini"
    )
    return finalize_report(report_draft(), {"email": 1, "phone": 1}, meta)


def success(request: AnalysisRequest, with_pdf: bool = True) -> AnalysisSuccess:
    report = fixture_report(request.support_id)
    return AnalysisSuccess(
        support_id=request.support_id,
        report=report,
        markdown=render_markdown(report),
        json=report_json(report),
        pdf=b"%PDF-1.4 rendered report" if with_pdf else None,
    )


class FakeAnalysis:
    """Stands in for ``pipeline.analyse``: emits the timeline, then responds."""

    def __init__(self, respond: Callable[[AnalysisRequest], AnalysisOutcome]) -> None:
        self.respond = respond
        self.requests: list[AnalysisRequest] = []

    async def __call__(self, request: AnalysisRequest, on_event) -> AnalysisOutcome:
        self.requests.append(request)
        for entry in TIMELINE:
            on_event(entry)
        return self.respond(request)


@pytest.fixture(autouse=True)
def fresh_process_state():
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def page(monkeypatch):
    """Return a loader: page(deps, respond) -> (AppTest after first run, fake)."""

    def load(deps=None, respond=success):
        deps = deps or make_deps()
        fake = FakeAnalysis(respond)
        monkeypatch.setattr(pipeline, "default_deps", lambda: deps)
        monkeypatch.setattr(pipeline, "analyse", fake)
        at = AppTest.from_file(str(PAGE), default_timeout=20)
        at.run()
        assert not at.exception
        return at, fake

    return load


def fill_and_analyse(at: AppTest) -> AppTest:
    at.file_uploader[0].set_value(RESUME)
    at.run()  # an upload reruns the page, as in the browser
    at.text_area[0].set_value(JOB_TEXT)
    at.button(key="analyse").click()
    at.run()
    assert not at.exception
    return at


def page_texts(at: AppTest) -> list[str]:
    texts = []
    for node in at.main:
        value = getattr(node, "value", None)
        if isinstance(value, str):
            texts.append(plain(value))
        label = getattr(node, "label", None)
        if isinstance(label, str):
            texts.append(label)
    return texts


def page_text(at: AppTest) -> str:
    return "\n".join(page_texts(at))


def test_privacy_notice_appears_before_uploader(page):
    at, _ = page()

    order = [node.type for node in at.main]
    notice_index = next(
        index
        for index, node in enumerate(at.main)
        if node.type == "markdown" and "OpenAI" in node.value
    )
    notice = page_text(at)
    assert notice_index < order.index("file_uploader")
    assert "nothing is stored" in notice.lower()
    assert "redact" in notice.lower()
    assert ui.OPENAI_DATA_POLICY_URL in notice


def test_ungated_page_shows_the_form_directly(page):
    at, _ = page()

    assert len(at.file_uploader) == 1
    assert len(at.text_area) == 1
    assert len(at.text_input) == 0


def test_gated_page_shows_only_code_prompt_until_correct_code(page):
    at, _ = page(make_deps(access_code=ACCESS_CODE))

    assert len(at.file_uploader) == 0
    assert len(at.text_area) == 0
    assert "OpenAI" not in page_text(at)
    assert [field.label for field in at.text_input] == ["Access code"]

    at.text_input[0].set_value(ACCESS_CODE)
    at.button[0].click()
    at.run()

    assert not at.exception
    assert len(at.text_input) == 0
    assert len(at.file_uploader) == 1
    assert len(at.text_area) == 1


def test_wrong_code_is_refused_and_the_form_stays_hidden(page):
    at, _ = page(make_deps(access_code=ACCESS_CODE))

    at.text_input[0].set_value("not-the-code")
    at.button[0].click()
    at.run()

    assert [error.value for error in at.error] == [ui.WRONG_CODE_MESSAGE]
    assert len(at.file_uploader) == 0


def test_five_wrong_codes_lock_out_even_the_right_code(page):
    at, _ = page(make_deps(access_code=ACCESS_CODE))

    for _ in range(5):
        at.text_input[0].set_value("not-the-code")
        at.button[0].click()
        at.run()
    assert [error.value for error in at.error] == [ui.LOCKED_MESSAGE]

    at.text_input[0].set_value(ACCESS_CODE)
    at.button[0].click()
    at.run()

    assert [error.value for error in at.error] == [ui.LOCKED_MESSAGE]
    assert len(at.file_uploader) == 0


def test_quota_counter_shows_analyses_left_today(page):
    limiter = UsageLimiter(per_visitor_daily=5, global_daily=200, max_concurrent=3)
    visitor = visitor_key("local", SECRET)
    for _ in range(2):
        lease = limiter.try_admit(visitor, FIXED_NOW)
        lease.start(FIXED_NOW)  # type: ignore[union-attr]
        lease.release()  # type: ignore[union-attr]

    at, _ = page(make_deps(limiter=limiter))

    assert "Analyses left today: 3" in page_text(at)


def test_every_input_has_a_visible_label(page):
    at, _ = page()
    gated, _ = page(make_deps(access_code=ACCESS_CODE))

    widgets = [*at.file_uploader, *at.text_area, *gated.text_input]
    assert widgets
    for widget in widgets:
        assert widget.label.strip()
        assert widget.proto.label_visibility.value == 0  # visible
    assert at.button(key="analyse").label == "Analyse"


def test_missing_inputs_ask_for_both_and_do_not_analyse(page):
    at, fake = page()

    at.button(key="analyse").click()
    at.run()

    assert not at.exception
    assert fake.requests == []
    assert [warning.value for warning in at.warning] == [ui.MISSING_INPUT_MESSAGE]
    assert not at.button(key="analyse").disabled


def test_completed_analysis_shows_score_sections_and_three_downloads(page):
    at, fake = page()

    fill_and_analyse(at)

    [request] = fake.requests
    assert request.filename == RESUME[0]
    assert request.file_bytes == RESUME[1]
    assert request.job_description == JOB_TEXT
    assert request.visitor == visitor_key("local", SECRET)
    assert re.fullmatch(r"RF-[0-9A-Z]{8}", request.support_id)

    [status] = at.status
    assert status.state == "complete"
    assert "completed" in status.label.lower()
    timeline_lines = [plain(node.value) for node in status if node.type == "markdown"]
    assert timeline_lines == [
        "**System** · Status: Request accepted",
        "**Orchestrator** · Delegation: Delegates to Resume Parser",
        "**Resume Parser** · Tool call: Calls normalize_skills with 4 skills",
    ]

    report = fixture_report(request.support_id)
    text = page_text(at)
    assert f"{report.overall_score} / 100" in text
    assert [heading.value for heading in at.subheader] == [
        "Privacy",
        *SECTION_HEADINGS,
    ]
    assert report.summary in text
    assert report.job.role_title in text
    for line in report.rubric:
        assert line.label in text
    assert [button.label for button in at.get("download_button")] == [
        "Download JSON",
        "Download Markdown",
        "Download PDF",
    ]
    assert not at.button(key="analyse").disabled
    assert at.text_area[0].value == JOB_TEXT
    assert at.file_uploader[0].value.name == RESUME[0]


def test_analyse_button_is_disabled_while_analysis_runs(page):
    def stop_midway(request: AnalysisRequest) -> AnalysisOutcome:
        st.stop()
        raise AssertionError("unreachable")

    at, _ = page(respond=stop_midway)

    fill_and_analyse(at)

    assert at.button(key="analyse").disabled
    assert at.file_uploader[0].disabled
    assert at.text_area[0].disabled
    [status] = at.status
    assert status.state == "running"
    assert "running" in status.label.lower()
    assert len([node for node in status if node.type == "markdown"]) == len(TIMELINE)


def test_pdf_unavailable_shows_two_downloads_and_a_note(page):
    at, _ = page(respond=lambda request: success(request, with_pdf=False))

    fill_and_analyse(at)

    assert [button.label for button in at.get("download_button")] == [
        "Download JSON",
        "Download Markdown",
    ]
    assert [info.value for info in at.info] == [ui.PDF_UNAVAILABLE_NOTE]
    assert at.status[0].state == "complete"


def test_failed_analysis_shows_message_with_support_id(page):
    def tools_down(request: AnalysisRequest) -> AnalysisOutcome:
        category = FailureCategory.SERVICE_UNAVAILABLE
        return AnalysisFailure(
            request.support_id, category, failure_message(category, request.support_id)
        )

    at, fake = page(respond=tools_down)

    fill_and_analyse(at)

    support_id = fake.requests[0].support_id
    [error] = at.error
    assert error.value.endswith(f"Support ID: {support_id}")
    assert "unavailable" in error.value
    [status] = at.status
    assert status.state == "error"
    assert "failed" in status.label.lower()
    assert at.get("download_button") == []


def test_crashing_analysis_shows_generic_message_without_exception_text(page):
    def crash(request: AnalysisRequest) -> AnalysisOutcome:
        raise RuntimeError(EXCEPTION_TEXT)

    at, fake = page(respond=crash)

    fill_and_analyse(at)

    support_id = fake.requests[0].support_id
    [error] = at.error
    internal = failure_message(FailureCategory.INTERNAL, support_id)
    assert internal in error.value
    text = page_text(at)
    for fragment in ("boom", "secret", "settings.py", "OPENAI_API_KEY", "RuntimeError"):
        assert fragment not in text
    assert at.status[0].state == "error"
    assert not at.button(key="analyse").disabled


def test_missing_configuration_shows_friendly_message(monkeypatch):
    def broken() -> pipeline.PipelineDeps:
        raise ConfigError("OPENAI_API_KEY must be set")

    monkeypatch.setattr(pipeline, "default_deps", broken)
    at = AppTest.from_file(str(PAGE), default_timeout=20)
    at.run()

    assert not at.exception
    [error] = at.error
    assert re.search(r"Support ID: RF-[0-9A-Z]{8}$", error.value)
    assert "OPENAI_API_KEY" not in page_text(at)
    assert len(at.file_uploader) == 0


def test_start_over_clears_report_and_timeline(page):
    at, _ = page()
    fill_and_analyse(at)
    assert at.get("download_button")

    at.button(key="start_over").click()
    at.run()

    assert not at.exception
    assert len(at.status) == 0
    assert at.get("download_button") == []
    assert [heading.value for heading in at.subheader] == ["Privacy"]
    assert at.file_uploader[0].value is None
    assert at.text_area[0].value == ""
    assert not at.button(key="analyse").disabled


def test_report_text_is_escaped_and_never_rendered_as_html(page):
    hostile = "**Bold** [click](https://evil.example) <b>tag</b> $x$ :red[alert]"

    def hostile_report(request: AnalysisRequest) -> AnalysisOutcome:
        outcome = success(request)
        report = outcome.report.model_copy(update={"summary": hostile})
        return AnalysisSuccess(
            outcome.support_id, report, outcome.markdown, outcome.json, outcome.pdf
        )

    at, _ = page(respond=hostile_report)

    fill_and_analyse(at)

    markdown = [node for node in at.main if node.type == "markdown"]
    assert all(not node.proto.allow_html for node in markdown)
    assert ui.escape_markdown(hostile) in [node.value for node in markdown]
    assert hostile not in [node.value for node in markdown]


def test_escape_markdown_neutralises_markup():
    escaped = ui.escape_markdown("*a* _b_ [c](d) <e> $f$ :g[h] `i` #j |k|\nnext")

    assert plain(escaped) == "*a* _b_ [c](d) <e> $f$ :g[h] `i` #j |k| next"
    assert re.search(r"(?<!\\)[*_\[\]()<>$:`#|]", escaped) is None


def test_download_files_carry_valid_json_markdown_and_pdf():
    request = AnalysisRequest("resume.pdf", b"", JOB_TEXT, "visitor", "RF-ABCDEFGH")
    outcome = success(request)

    files = ui.download_files(outcome)

    assert [file.file_name for file in files] == [
        "resumefit-report-RF-ABCDEFGH.json",
        "resumefit-report-RF-ABCDEFGH.md",
        "resumefit-report-RF-ABCDEFGH.pdf",
    ]
    assert [file.mime for file in files] == [
        "application/json",
        "text/markdown",
        "application/pdf",
    ]
    parsed = MatchReport.model_validate_json(files[0].data)
    assert parsed.schema_version == "1.0"
    assert json.loads(files[0].data)["support_id"] == "RF-ABCDEFGH"
    for heading in SECTION_HEADINGS:
        assert f"## {heading}" in files[1].data
    assert files[2].data == outcome.pdf


def test_visitor_key_ignores_forwarded_for_and_conflicting_headers():
    settings = Settings.from_env(
        {
            "OPENAI_API_KEY": "sk-test-not-real",
            "VISITOR_HASH_SECRET": SECRET,
            "TRUST_PROXY_HEADERS": "true",
        }
    )
    trusted = StreamlitHeaders([("X-Real-IP", "203.0.113.7")])
    forged = StreamlitHeaders(
        [("X-Real-IP", "203.0.113.7"), ("X-Forwarded-For", "198.51.100.1")]
    )
    conflicting = StreamlitHeaders(
        [("X-Real-IP", "203.0.113.7"), ("X-Real-IP", "198.51.100.1")]
    )

    assert ui.visitor_for(trusted, None, settings) == visitor_key("203.0.113.7", SECRET)
    assert ui.visitor_for(forged, "10.0.0.2", settings) == visitor_key(
        "203.0.113.7", SECRET
    )
    assert ui.visitor_for(conflicting, None, settings) == visitor_key(
        "proxy-unknown", SECRET
    )


def test_streamlit_config_hardens_browser_settings():
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))

    assert config["server"]["enableXsrfProtection"] is True
    assert config["server"]["enableCORS"] is True
    assert config["server"]["maxUploadSize"] == 2
    assert config["server"]["headless"] is True
    assert config["server"]["port"] == 8501
    assert config["browser"]["gatherUsageStats"] is False
    assert config["client"]["showErrorDetails"] == "none"
