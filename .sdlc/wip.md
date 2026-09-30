# SDLC Work In Progress

## Product Snapshot

Goal: ResumeFit AI — a public Streamlit app on one VPS where an AutoGen agent team (orchestrator + 5 specialists, skill files, FastMCP tools) turns a resume and a job description into a scored, explainable, downloadable match report, behind guardrails and cost limits.
Working Today: nothing runs yet; no production code exists (greenfield). Library APIs were verified in throwaway spikes (since deleted).
Reusable Today: local virtual environments `.venv` (application deps: autogen 0.7.5, `mcp` 1.30, streamlit 1.64) and `.venv-mcp` (fastmcp 4.0.10, pypdf, python-docx, fpdf2); both untracked.
Current Increment: spec, design, and plan independently assessed (Pass-with-fixes for all three); all 12 review fixes applied and all three checkers pass again.
Remaining Shared Work: none beyond the plan's five PRs.
Target-Owned Work: all five PRs in docs/plan.md, in four waves: Wave 1 foundation + tools service (parallel), Wave 2 agent team and pipeline, Wave 3 Streamlit page, Wave 4 deployment stack.
Deferred: shared-storage limiter, model-based injection classifier, script Content Security Policy.
Before Coding: nothing blocking; default limits are owner-accepted (5/day per client, 1 concurrent per client, 3 concurrent global, 200/day global, 150k tokens, 180 s, 20 messages; all env-configurable).
Next Action: /code-create Wave 1 — PR-CORE-FOUNDATION and PR-MCP-TOOLS in parallel (docs/plan.md).

## Process Snapshot

Last Updated: 2026-09-30T14:30:00Z
Updated By: agent
Current Stage: plan-assess
Current Gate: assessed-pass-with-fixes (fixes applied)
Project Entry Mode: greenfield
Work Scope: product/system
Ready To Implement: Yes
Review Level: Standard
Extra Checks: security, privacy, external-integration

## Current Artifacts

| Kind | Path | Status | Notes |
| --- | --- | --- | --- |
| Spec | docs/spec.md | assessed | Format v3; /spec-assess Pass-with-fixes, fixes applied; checker 7/7 (48 FR, 22 NFR, 59 AT) |
| Design | docs/design.md | assessed | Format v2; /design-assess Pass-with-fixes, fixes applied; checker 13/13 (24 TEST, 9 DEC, 9 RISK); docs/design.html regenerated from it |
| Plan | docs/plan.md | assessed | Format v3, Implementation plan, 5 PRs in 4 waves; /plan-assess Pass-with-fixes, fixes applied; checker 21/21 |

## Decisions And Assumptions

- User explicitly requested end-to-end authoring of spec, design, and plan without stopping between them; assess/review stages are run by another agent (source: user request).
- Two dependency sets are required: autogen-ext 0.7.5 fails to import with `mcp` 2.x, and FastMCP 4 requires `mcp` 2.x (verified 2026-09-30; see docs/design.md, Design Decisions).
- `SelectorGroupChat` needs `custom_message_types=[StructuredMessage[...]]` for structured outputs (verified).
- Rate limits are in-process and reset on restart; a non-consuming admission lease (1 per client, 3 global) is taken before parsing/moderation and quota is consumed only when the agent team starts (docs/spec.md FR-COST-ADMISSION).
- Visitor identity comes only from the header Caddy overwrites (`CLIENT_IP_HEADER`, default `X-Real-IP`; Caddy also overwrites `X-Forwarded-For`) (docs/design.md DEC-MEMLIMITS).
- Extraction runs in a killable spawned worker with a 10 s deadline, at most 2 at once; DOCX zip limits 500 entries / 20 MB / no encrypted or nested entries; compose sets `cpus` for app and mcp (DEC-EXTRACTWORKER).
- One token budget covers team, tool reflection, and the report retry; retry skipped if budget is insufficient; per-call `max_tokens` 4000. Model client and MCP sessions live in one AsyncExitStack per analysis.
- The live OpenAI test is an optional owner-run pre-release check, not merge-blocking; offline replay plus real MCP (in-process and cross-process) is merge-blocking.
- Default limits accepted by the owner (source: review fixes request 2026-09-30).
- Personal names are not redacted; PDF output is Latin-1 only; English-only heuristics (docs/spec.md, Assumptions).
- Docker is not installed locally; deployment files are verified by static tests and a manual post-deploy checklist only.
- UI Mock Preference: Not needed (docs/spec.md).

## Check And Review Evidence

- 2026-09-30 independent assessment of spec, design, and plan: Pass-with-fixes for all three (12 fixes: early admission lease, DOCX zip limits and killable extraction worker, Caddy header overwrite and trusted identity header, authoritative limits, aggregated token budget, pipeline timeline events, client/session lifecycle, executable waves, CI Docker job, optional live test, per-context .dockerignore files, coverage of new tests).
- 2026-09-30 after fixes: `python checkers/check_spec.py docs/spec.md --json` → 7/7 gates pass (UC and FR acceptance coverage 100%).
- 2026-09-30 after fixes: `python checkers/check_design.py docs/design.md --spec docs/spec.md --json` → 13/13 gates pass.
- 2026-09-30 after fixes: `python checkers/check_plan.py docs/plan.md --spec docs/spec.md --design docs/design.md --json` → 21/21 gates pass.
- 2026-09-30 PR-MCP-TOOLS (code-create, resumed after interruption; all files under `mcp_server/` except Dockerfile/.dockerignore). From the repo root: `.\.venv-mcp\Scripts\python -m pytest mcp_server/tests -q` → 67 passed; `.\.venv-mcp\Scripts\python -m pytest mcp_server/tests/test_worker.py -q` → 13 passed (slow file times out < 3 s, worker killed, `/health` 200 < 1 s in-process and over a real local socket, cap of 2 holds, `busy` after slot wait); `.\.venv-mcp\Scripts\python -m ruff check mcp_server` and `ruff format --check mcp_server` → pass (root `pyproject.toml` settings); `mypy --config-file ..\pyproject.toml resumefit_tools tests` (cwd `mcp_server`) → no issues. Manual: `python -m resumefit_tools.server` (cwd `mcp_server`) → `curl.exe http://127.0.0.1:8000/health` = `{"status":"ok"}`, Host `evil.example` → 421, Host `mcp:8000` → 200; process stopped. Red evidence for the original first-failing tests was not recorded before the interruption; the added real-socket health test was shown to fail (health 1.7 s) under a scratch mutation that blocks the event loop, then pass. Not run: Linux `RLIMIT_AS`/`RLIMIT_CPU` path (no Linux locally; covered by the Docker/CI job in Wave 4); `ruff check --isolated` differs only in first-party import grouping and two intentional broad catches. Contract note for PR-AGENTS-TEAM: `extract_resume_text` and `render_pdf` return their dictionary as structured content; `normalize_skills` returns a JSON list in its text content and `{"result": [...]}` as structured content.
- 2026-09-30 PR-CORE-FOUNDATION (code-create, resumed after interruption; kept the earlier guardrails, limits, requirements, pyproject, .gitignore, fixtures, and six test files; added `app/resumefit/{config,observability,outcomes,schemas,report}.py`, `app/tests/test_{config,observability,identity,report}.py`, `scripts/check.py`, `.pre-commit-config.yaml`, `.github/workflows/check.yml`; ruff-formatted the earlier app files). Red: the four new test files first failed with `ModuleNotFoundError`; after green, a scratch stub plugin (deleted) replacing `client_identity` with an X-Forwarded-For reader, `log_event` without validation, and coverage scoring with 0 made `test_forged_forwarded_for_does_not_change_visitor_key`, `test_locked_out_visitor_stays_locked_with_forged_headers`, `test_log_event_rejects_free_text_fields`, and `test_three_of_four_must_haves_award_thirty_of_forty` fail on assertions (20 failed). Green: `.\.venv\Scripts\python -m pytest app/tests -q` → 277 passed; `.\.venv\Scripts\python -m pytest app/tests/test_admission.py app/tests/test_identity.py -q` → 87 passed (flood test 50 repetitions); `python scripts/check.py` → Gate passed (ruff format, ruff check, mypy app 12 files, pytest app 277, mypy tools 6 files, pytest tools 67); `.\.venv\Scripts\python -m pre_commit run --files <app and scripts *.py>` → ruff-check and ruff-format Passed; `pre-commit run --all-files` → Skipped (no files tracked in git yet). Not done: `pre-commit install` (git hooks run through Git's `sh`; skipped under the no-Linux-shell constraint on this PC); CI workflow not executed (no push). Interpretations: `error_type` (exception class name) added to the log allow-list per the design's "exception class name" rule; `configure_logging(level, stream=None)` adds an optional stream for tests; `ReportMeta` lives in `schemas.py`; `AnalysisOutcome = AnalysisSuccess | AnalysisFailure`; `failure_message(category, support_id, reason=None)` maps guard/extraction codes to fixed messages; `report.SECTION_HEADINGS` fixes the Markdown section names (aligned with the tools-service PDF test).
## Results And Feedback

Expected Result: documents are specific enough for parallel /code-create on the five PRs.
Feedback From: independent assess agents (received); the owner for UI review after the page PR and the optional live check before release.
Feedback Status: received and applied
Feedback Evidence: assessment findings (Pass-with-fixes ×3) resolved in docs/spec.md, docs/design.md, docs/plan.md; checkers re-run green.
Current Work Group: Wave 1 (PR-CORE-FOUNDATION, PR-MCP-TOOLS)
Current Work: PR-CORE-FOUNDATION (code-create complete 2026-09-30; awaiting human review and /code-assess; not committed); PR-MCP-TOOLS (code-create complete 2026-09-30; awaiting human review and /code-assess; not committed)
Parallel Limit: 2 in Wave 1, then 1 per wave
What Changed: review fixes applied (new FR-COST-ADMISSION, FR-COST-IDENTITY, FR-UPLOAD-ARCHIVE, FR-UPLOAD-PARSETIME, NFR-CAP-RESOURCES; new AT-COST-ADMISSION, AT-COST-FLOOD, AT-COST-FORGEDHEADERS, AT-UPLOAD-ARCHIVE, AT-UPLOAD-PARSETIME; new TEST-LIMITS-ADMISSION, TEST-IDENTITY-FORGED, TEST-MCP-ISOLATION, TEST-PIPELINE-CLEANUP, TEST-DEPLOY-IMAGES; DEC-EXTRACTWORKER; RISK-LEAKS).
Documents To Update: none.
Stop Conditions: see docs/plan.md, Risks and stop conditions.

## Open Questions And Blockers

- Docker is not installed locally: `docker compose config` and image builds are evidenced only by the CI Docker job (Wave 4) and the VPS.
- Should DOCX get a page-equivalent cap? Currently only the text-length bound applies (docs/spec.md).
- Resolved (PR-MCP-TOOLS): FastMCP 4.0.10 checks the Host header only when `host_origin_protection=True` is passed (its "auto" default protects loopback binds only, so `0.0.0.0` would be unprotected); `allowed_hosts` entries match on host name with the port ignored, and localhost names are always allowed. `MCP_ALLOWED_HOSTS=mcp:8000,localhost:8000,127.0.0.1:8000` accepts `mcp:8000`/`mcp`; foreign hosts get 421 (tests in `mcp_server/tests/test_server.py`). Deviation from the design's literal `mcp.run(...)` call: it also passes `host_origin_protection=True` and `show_banner=False`, and `main()` accepts `--host/--port` (defaults `0.0.0.0:8000`).
- `.gitignore` now exists (foundation PR) and ignores `.env*` (except `.env.example`), `.venv*/`, and caches.

## Bootstrap Status

Bootstrap File: none
Status: not-offered
Notes: no AGENTS.md or equivalent in the repository yet.
