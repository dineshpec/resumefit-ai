"""ResumeFit AI page: layout and session flow only; rendering lives in ``resumefit.ui``.

Session state holds only ``unlocked``, ``running``, ``timeline``, ``outcome``, a
one-shot ``notice``, and ``input_generation`` (bumped by Start over so the upload
and text widgets are recreated empty).
"""

import asyncio
import logging

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from resumefit import pipeline, ui
from resumefit.observability import log_event, new_support_id
from resumefit.outcomes import (
    AnalysisFailure,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisSuccess,
    FailureCategory,
    TimelineEntry,
    failure_message,
)


def request_analysis(generation: int) -> None:
    # A disabled widget ignores values arriving in the same request, so the job
    # description typed just before the click is committed here first.
    job_description_key = f"job_description_{generation}"
    st.session_state[job_description_key] = st.session_state.get(
        job_description_key, ""
    )
    st.session_state["running"] = True
    st.session_state.pop("outcome", None)
    st.session_state.pop("timeline", None)


def start_over() -> None:
    for key in ("running", "timeline", "outcome", "notice"):
        st.session_state.pop(key, None)
    st.session_state["input_generation"] = st.session_state["input_generation"] + 1


def run_analysis(
    resume: UploadedFile, job_description: str, visitor: str
) -> AnalysisOutcome:
    support_id = new_support_id()
    timeline: list[TimelineEntry] = []
    st.session_state["timeline"] = timeline
    with st.status(ui.RUNNING_LABEL, state="running", expanded=True) as status:

        def on_event(entry: TimelineEntry) -> None:
            timeline.append(entry)
            status.markdown(ui.timeline_markdown(entry))

        request = AnalysisRequest(
            filename=resume.name,
            file_bytes=resume.getvalue(),
            job_description=job_description,
            visitor=visitor,
            support_id=support_id,
        )
        outcome: AnalysisOutcome
        try:
            outcome = asyncio.run(pipeline.analyse(request, on_event))
        except asyncio.CancelledError:
            # Nothing cancels this private event loop from outside, so a
            # cancellation here is an internal failure the pipeline has logged.
            outcome = _internal_failure(support_id)
        except Exception as exc:
            log_event(
                "analysis_finished",
                level=logging.ERROR,
                support_id=support_id,
                visitor=visitor,
                outcome="failure",
                category=FailureCategory.INTERNAL.value,
                error_type=type(exc).__name__,
            )
            outcome = _internal_failure(support_id)
        failed = isinstance(outcome, AnalysisFailure)
        status.update(
            label=ui.FAILED_LABEL if failed else ui.COMPLETED_LABEL,
            state="error" if failed else "complete",
        )
    return outcome


def _internal_failure(support_id: str) -> AnalysisFailure:
    category = FailureCategory.INTERNAL
    return AnalysisFailure(support_id, category, failure_message(category, support_id))


st.set_page_config(page_title="ResumeFit AI", layout="centered")
st.title("ResumeFit AI")
st.markdown(ui.PURPOSE)

deps = ui.load_deps()
if deps is None:
    st.stop()
visitor = ui.visitor_for(st.context.headers, st.context.ip_address, deps.settings)
gate = ui.access_gate(deps.settings.app_access_code)
if gate.required and not st.session_state.get("unlocked"):
    ui.render_access_form(gate, visitor, deps.clock())
    st.stop()

st.subheader("Privacy")
st.markdown(ui.PRIVACY_NOTICE)

generation = st.session_state.setdefault("input_generation", 0)
running = bool(st.session_state.get("running"))
resume = st.file_uploader(
    ui.RESUME_LABEL,
    type=ui.RESUME_TYPES,
    max_upload_size=ui.MAX_UPLOAD_MB,
    key=f"resume_{generation}",
    disabled=running,
)
job_description = st.text_area(
    ui.JOB_DESCRIPTION_LABEL,
    max_chars=ui.JOB_DESCRIPTION_MAX_CHARS,
    height=240,
    key=f"job_description_{generation}",
    disabled=running,
)
remaining = deps.limiter.remaining(visitor, deps.clock())
st.markdown(f"Analyses left today: {remaining}")
st.button(
    "Analyse",
    type="primary",
    key="analyse",
    on_click=request_analysis,
    args=(generation,),
    disabled=running,
)
notice = st.session_state.pop("notice", None)
if notice:
    st.warning(notice)

if running:
    try:
        if resume is None or not (job_description or "").strip():
            st.session_state["notice"] = ui.MISSING_INPUT_MESSAGE
        else:
            st.session_state["outcome"] = run_analysis(
                resume, job_description or "", visitor
            )
    finally:
        st.session_state["running"] = False
    st.rerun()

outcome = st.session_state.get("outcome")
if outcome is not None:
    ui.render_timeline(st.session_state.get("timeline", []), outcome)
    if isinstance(outcome, AnalysisSuccess):
        ui.render_report(outcome.report)
        ui.render_downloads(outcome)
    else:
        ui.render_failure(outcome)

st.button("Start over", key="start_over", on_click=start_over, disabled=running)
