<!-- sarathi:artifact-format version="3" -->
# ResumeFit AI — Requirements Specification

## Product Overview

### Problem

Job seekers routinely send the same resume to many openings and cannot tell how
well it fits a particular job description. Generic "resume checker" sites give a
number without explaining it, and many keep the uploaded resume. Candidates end
up guessing which requirements they are missing and how to phrase their
experience for a specific role.

ResumeFit AI is a small public web application. A visitor uploads a resume and
pastes a job description; a team of specialised AI agents analyses both and
returns a transparent match report with concrete coaching. The visitor watches
the agents work step by step, reads the report on screen, and downloads it.

The product is also a course deliverable ("CrewAI concepts, Skills, MCP, Tools,
Multi-Agent", built with AutoGen). A reviewer must be able to see specialised
agents with clear responsibilities, an orchestrator that delegates, per-agent
skill files, tools exposed through the Model Context Protocol (MCP), and a
structured final output, following the flow Input → Skills → Model → MCP tools →
Structured Output.

### Who it is for

- **Visitors (job seekers)** who want a quick, explainable fit check for one job.
- **The owner/operator**, who hosts the service on one small VPS at a public
  domain (for example `resume.dineshlabs.in`), pays for the OpenAI usage, and
  must keep abuse and cost under control.
- **The course reviewer**, who assesses the multi-agent design.

### What users must be able to do

1. Upload a resume (PDF, DOCX, or plain text) and paste a job description.
2. Watch a live timeline of which agent is doing what, including tool calls.
3. Read a match report: an overall fit score out of 100 with a visible rubric,
   matched and missing skills, the extracted candidate profile and job
   requirements, improved resume bullets, likely interview questions, and a
   learning plan for gaps.
4. Download the report as JSON, Markdown, and PDF, then clear it.
5. As operator: deploy with one command, optionally gate the app with an access
   code, check health, and diagnose failures from logs that contain no personal
   data.

### Explicit non-goals

No user accounts, database, stored history, payments, job search, application
submission, full resume rewriting, OCR of scanned image-only PDFs, non-English
analysis guarantees, or horizontal scaling across several servers. Agents never
execute code or act on external accounts.

### What success looks like

A visitor with a normal two-page resume gets a readable, explainable report in
about two minutes, can see how the score was built, and can download it. Hostile,
oversized, off-topic, or harmful inputs are refused before any paid model call.
Daily spending stays bounded even when the URL is shared publicly. The resume is
never written to disk, and personal contact details are removed before any text
is sent to OpenAI.

### Important failures and constraints

- Invalid files, oversized inputs, hostile or slow-to-parse files, suspected
  instruction smuggling, off-topic input, moderation hits, quota exhaustion,
  busy service, model or tool outages,
  time/turn/token limits, and an invalid final report must each produce a clear,
  non-technical message with a support ID, never a stack trace.
- The OpenAI key lives only in server-side environment configuration.
- The tools service is reachable only inside the deployment's private network.
- Usage limits are held in the memory of a single application process; they
  reset when that process restarts. This is accepted for a single-VPS service.
- Docker is not available on the development machine, so deployment files can
  only be checked statically and by review before the first live deployment.

### Document status

Work Scope: product/system
Ready To Implement: Yes
Review Level: Standard
Extra Checks: security, privacy, external-integration

`Ready To Implement` is `Yes` because the design and implementation plan now
exist and all three documents have passed independent assessment with fixes
applied.

## User Needs

<!-- sarathi:need id="UN-SEEKER-FIT" -->
- **Know the fit.** A job seeker needs to know how well their resume fits one
  specific job before applying.

<!-- sarathi:need id="UN-SEEKER-GAPS" -->
- **See the gaps.** A job seeker needs to know which of the job's requirements
  their resume does not demonstrate.

<!-- sarathi:need id="UN-SEEKER-IMPROVE" -->
- **Know what to do next.** A job seeker needs concrete, job-specific ways to
  strengthen the resume and prepare for the interview.

<!-- sarathi:need id="UN-SEEKER-TRUST" -->
- **Understand the result.** A job seeker needs to see how the result was
  produced so they can judge how far to rely on it.

<!-- sarathi:need id="UN-SEEKER-KEEP" -->
- **Keep the result.** A job seeker needs a copy of the result after leaving
  the page.

<!-- sarathi:need id="UN-SEEKER-PRIVACY" -->
- **Protect personal data.** A job seeker needs confidence that the resume is
  not stored and that contact details are not shared unnecessarily.

<!-- sarathi:need id="UN-OWNER-COST" -->
- **Bounded spending.** The owner needs model spending to stay within a small,
  predictable daily budget although the site is public.

<!-- sarathi:need id="UN-OWNER-SAFETY" -->
- **Misuse resistance.** The owner needs the public service to refuse
  instruction smuggling, off-topic use, and harmful content.

<!-- sarathi:need id="UN-OWNER-OPERATE" -->
- **Simple operations.** The owner needs to deploy, run, and diagnose the
  service on one VPS without seeing visitors' personal data.

<!-- sarathi:need id="UN-REVIEWER-AGENTS" -->
- **Visible agent design.** The course reviewer needs to see specialised agents,
  orchestrator delegation, skill files, MCP tools, and a structured output.

## Non-Goals

- User accounts, sign-in, saved history, or any database.
- Persisting resumes, job descriptions, or reports on the server.
- Rewriting or generating a complete resume, cover letter, or application.
- Searching for jobs or submitting applications.
- OCR for scanned, image-only PDFs; such files are rejected as unreadable.
- Guaranteed quality for non-English resumes or job descriptions.
- Running more than one application instance or sharing limits across servers.
- Agents executing code, browsing the web, or calling third-party accounts.
- An LLM-based second-opinion prompt-injection classifier (deferred; heuristic
  checks, data delimiting, and moderation are the accepted first version).
- Payments, analytics, or tracking of visitors.

## Features

<!-- sarathi:feature id="FEAT-ANALYSIS-MATCH" needs="UN-SEEKER-FIT UN-SEEKER-GAPS UN-SEEKER-TRUST" -->
- **Explainable fit analysis.** An overall score out of 100 built from a fixed,
  visible rubric, with matched and missing skills, the extracted candidate
  profile, and the extracted job requirements.

<!-- sarathi:feature id="FEAT-ANALYSIS-COACH" needs="UN-SEEKER-IMPROVE" -->
- **Coaching.** Improved resume bullets aimed at the job, likely interview
  questions, and a learning plan for missing must-have skills.

<!-- sarathi:feature id="FEAT-PROGRESS-TIMELINE" needs="UN-SEEKER-TRUST UN-REVIEWER-AGENTS" -->
- **Live agent timeline.** A running list of agent steps and tool calls while
  the analysis is in progress, ending in a clear completed or failed state.

<!-- sarathi:feature id="FEAT-REPORT-EXPORT" needs="UN-SEEKER-KEEP" -->
- **Report display and export.** The report on screen plus JSON, Markdown, and
  PDF downloads.

<!-- sarathi:feature id="FEAT-GUARD-INPUT" needs="UN-OWNER-SAFETY UN-OWNER-COST" -->
- **Input guardrails.** File and length limits, instruction-smuggling detection,
  resume and job-description plausibility checks, and content moderation, all
  applied before paid analysis starts.

<!-- sarathi:feature id="FEAT-PRIVACY-PROTECT" needs="UN-SEEKER-PRIVACY" -->
- **Privacy protection.** Contact details removed before model calls, nothing
  stored, a clear privacy notice, and a way to clear results.

<!-- sarathi:feature id="FEAT-COST-LIMITS" needs="UN-OWNER-COST" -->
- **Usage and cost limits.** Per-visitor daily and concurrency limits, a global
  concurrency and daily cap, and per-analysis time, turn, and token limits.

<!-- sarathi:feature id="FEAT-ACCESS-GATE" needs="UN-OWNER-COST UN-OWNER-SAFETY" -->
- **Optional access code.** The owner can require a shared code before the app
  can be used.

<!-- sarathi:feature id="FEAT-OPS-SERVICE" needs="UN-OWNER-OPERATE" -->
- **Operable single-VPS service.** One-command deployment behind automatic
  HTTPS, health checks, and structured logs without personal data.

<!-- sarathi:feature id="FEAT-AGENTS-WORKFLOW" needs="UN-REVIEWER-AGENTS UN-SEEKER-TRUST" -->
- **Visible multi-agent workflow.** Named specialist agents, an orchestrator that
  delegates, per-agent skill files, MCP-served tools, and a schema-validated
  final report.

## Use Cases

### Analyse a resume against a job description
<!-- sarathi:use-case id="UC-ANALYSIS-RUN" -->

- **Primary actor:** Visitor.
- **Supporting systems:** OpenAI chat and moderation services; the private
  tools service (MCP).
- **Goal:** Obtain an explainable match report for one resume and one job.
- **Trigger:** The visitor presses **Analyse**.
- **Preconditions:** The app is unlocked (when an access code is configured).
  The visitor has quota left today.
- **Minimal guarantee:** Nothing is stored; the visitor sees either a report or
  a plain-language message with a support ID.
- **Success guarantee:** A validated report is shown and ready to download.

**Main success scenario**

1. The visitor reads the privacy notice, uploads a resume file, and pastes a job
   description.
2. The visitor presses **Analyse**. The system admits the request by taking the
   visitor's single run slot and one of the service's concurrent slots, without
   using daily quota, and the timeline shows its first entry.
3. The system checks the file type, file size, and job-description length.
4. The system extracts the resume text within a time limit and checks page
   count, archive limits, and text length.
5. The system checks both texts for instruction smuggling and plausibility, and
   removes contact details.
6. The system checks both texts with content moderation.
7. The system consumes one analysis from the visitor's daily quota and the
   global daily count and starts the agent team.
8. The orchestrator delegates, in turn, to the Resume Parser, JD Analyst,
   Matcher, Coach, and Report Writer; each check stage, agent step, and tool
   call from step 3 onwards appears in the timeline.
9. The system validates the final report and computes the rubric totals.
10. The timeline shows "completed" and the report appears with download buttons.

**Alternate flows**

- 1a. The visitor uploads a DOCX or TXT resume instead of a PDF: same flow.
- 8a. An agent asks the tools service to normalise skill names: the call and
  its outcome appear in the timeline.
- 9a. The first final report fails validation: the system asks the Report
  Writer once more, if the analysis token budget allows, and continues if the
  second attempt validates.
- 10a. PDF generation fails: the on-screen report, JSON, and Markdown remain
  available with a note that PDF is unavailable.

**Error flows**

- 2a. Another request already admitted or running for this visitor, all of the
  service's concurrent slots taken, or the visitor's quota or the global daily
  cap already used up: rejected before the file is parsed or moderated, with
  the reason and, for quota, the reset time.
- 3a. Unsupported type, mismatched content, or file over 2 MB: rejected with a
  specific message.
- 3b. Job description outside 200–10,000 characters: rejected with a specific
  message.
- 4a. PDF over 5 pages, DOCX over its archive limits, unreadable file,
  extraction over its time limit, or text outside 300–20,000 characters:
  rejected with a specific message.
- 5a. Instruction smuggling detected: rejected, naming which input was affected.
  Every catalogue match is a rejection; there is no "warn and continue" mode, to
  keep the rule predictable.
- 5b. Resume or job description does not look like one: rejected as off-topic.
- 6a. Moderation flags either text: rejected without repeating the content.
- 6b. Moderation service unavailable: rejected with a try-later message.
- 7a. Daily quota or global daily cap used up by other runs since admission:
  rejected with the reason and, for quota, the reset time; nothing is consumed.
- 8b. Time, turn, or token limit reached: stopped with a limit message.
- 8c. Model or tools service unavailable: stopped with a try-later message.
- 9b. Second report attempt also invalid, or too little token budget left for
  it: failure message.
- Any unexpected error: generic message with support ID.

**Postconditions:** No resume, job description, or report text is written to
disk or logs. One structured log event records the outcome.

**Frequency/importance:** Core flow; every visit.

### Download and clear the report
<!-- sarathi:use-case id="UC-REPORT-DOWNLOAD" -->

- **Primary actor:** Visitor. **Precondition:** a report is on screen.
- **Main flow:** 1. The visitor chooses JSON, Markdown, or PDF. 2. The browser
  downloads the file. 3. The visitor presses **Start over**. 4. The report,
  timeline, and inputs are cleared from the session.
- **Alternate:** 1a. PDF is unavailable for this report: only JSON and Markdown
  are offered, with a note.
- **Error:** Session expired (tab closed or server restart): the report is gone;
  the visitor must analyse again.
- **Postcondition:** Nothing about the report remains in server memory after
  clearing or session end.

### Unlock a gated deployment
<!-- sarathi:use-case id="UC-ACCESS-UNLOCK" -->

- **Primary actor:** Visitor. **Precondition:** the owner configured a code.
- **Main flow:** 1. The visitor sees only the code prompt. 2. The visitor enters
  the code. 3. The system unlocks the app for that browser session.
- **Alternate:** No code configured: the app opens directly.
- **Error:** Wrong code: "incorrect code"; after 5 wrong attempts the visitor is
  locked out for 15 minutes.

### Deploy and update the service
<!-- sarathi:use-case id="UC-OPS-DEPLOY" -->

- **Primary actor:** Owner. **Supporting systems:** DNS provider, Let's Encrypt
  via the reverse proxy, Docker Compose on a Linux VPS.
- **Main flow:** 1. The owner points a DNS A record at the VPS. 2. The owner
  copies the example environment file and fills in the OpenAI key, domain, and
  optional access code. 3. The owner runs one compose command. 4. The proxy
  obtains a certificate and serves the app over HTTPS. 5. Health checks report
  healthy.
- **Alternate:** Update: pull new code and rerun the same command; in-memory
  limits reset.
- **Error:** Certificate issuance fails (DNS not yet propagated): the proxy
  retries; the README explains how to check logs.

### Diagnose a reported failure
<!-- sarathi:use-case id="UC-OPS-DIAGNOSE" -->

- **Primary actor:** Owner. **Trigger:** a visitor reports a support ID.
- **Main flow:** 1. The owner searches the app logs for the support ID. 2. The
  log event shows outcome category, duration, token usage, and stage, without
  resume or job-description text or contact details.
- **Error:** No matching event (logs rotated): the README states the retention.

## Functional Requirements

### Upload checks

<!-- sarathi:requirement id="FR-UPLOAD-TYPES" -->
- **Accepted formats.** The system shall accept a resume only when the file is a
  PDF, a DOCX (Office Open XML word-processing) document, or UTF-8 plain text.

<!-- sarathi:requirement id="FR-UPLOAD-SIGNATURE" -->
- **Content must match the name.** The system shall reject a file whose content
  signature does not match its file extension (for example a renamed
  executable with a `.pdf` extension).

<!-- sarathi:requirement id="FR-UPLOAD-SIZE" -->
- **Size cap.** The system shall reject a resume file larger than 2 MB.

<!-- sarathi:requirement id="FR-UPLOAD-PAGES" -->
- **Page cap.** The system shall reject a PDF resume with more than 5 pages.

<!-- sarathi:requirement id="FR-UPLOAD-ARCHIVE" -->
- **DOCX archive limits.** The system shall reject a DOCX resume whose archive
  has more than 500 entries, more than 20 MB of total uncompressed content, an
  encrypted entry, or an entry that is itself an archive.

<!-- sarathi:requirement id="FR-UPLOAD-PARSETIME" -->
- **Extraction deadline.** The system shall abandon text extraction that runs
  longer than the configured deadline (default 10 seconds), reject the file as
  unreadable, and keep serving other visitors and its health endpoints.

<!-- sarathi:requirement id="FR-UPLOAD-TEXTLEN" -->
- **Readable text bounds.** The system shall reject a resume whose extracted
  text has fewer than 300 or more than 20,000 characters.

### Job description checks

<!-- sarathi:requirement id="FR-INPUT-JDLEN" -->
- **Job description length.** The system shall reject a job description with
  fewer than 200 or more than 10,000 characters.

### Input guardrails

<!-- sarathi:requirement id="FR-GUARD-INJECTION" -->
- **Instruction smuggling.** The system shall reject a resume or job
  description that contains text matching the maintained catalogue of
  instruction-smuggling patterns, and the message shall say which input was
  rejected.

<!-- sarathi:requirement id="FR-GUARD-RESUMESHAPE" -->
- **Resume plausibility.** The system shall reject resume text that does not
  contain at least two recognisable resume sections (such as experience,
  education, skills, projects, or employment history).

<!-- sarathi:requirement id="FR-GUARD-JDSHAPE" -->
- **Job description plausibility.** The system shall reject job-description
  text that does not contain at least two recognisable job-posting cues (such
  as responsibilities, requirements, qualifications, or experience).

<!-- sarathi:requirement id="FR-GUARD-MODERATION" -->
- **Content moderation.** The system shall reject the request when OpenAI
  moderation flags either the resume text or the job-description text.

<!-- sarathi:requirement id="FR-GUARD-FAILCLOSED" -->
- **Moderation outage.** The system shall reject the request with a try-later
  message when the moderation check cannot be completed.

<!-- sarathi:requirement id="FR-GUARD-NOSPEND" -->
- **No spend on rejected input.** A request rejected by any upload, length,
  smuggling, plausibility, or moderation check shall make no chat-model call
  and shall not consume the visitor's daily quota.

### Privacy

<!-- sarathi:requirement id="FR-PRIVACY-REDACT" -->
- **Contact-detail redaction.** Before any text is sent to OpenAI, the system
  shall replace email addresses, phone numbers, web addresses, and street
  addresses in both inputs with labelled placeholders such as `[EMAIL]`.

<!-- sarathi:requirement id="FR-PRIVACY-NOSTORE" -->
- **No persistence.** The system shall not write uploaded files, extracted
  text, job descriptions, or report content to disk, logs, or any external
  service other than the OpenAI calls needed for the analysis.

<!-- sarathi:requirement id="FR-PRIVACY-NOTICE" -->
- **Privacy notice.** The page shall show, before the upload control, what is
  sent to OpenAI, what is redacted, and that nothing is stored.

<!-- sarathi:requirement id="FR-PRIVACY-CLEAR" -->
- **Start over.** The visitor shall be able to clear the current inputs,
  timeline, and report from the session with one action.

### Analysis content

<!-- sarathi:requirement id="FR-ANALYSIS-PROFILE" -->
- **Candidate profile.** The report shall include the candidate's extracted
  skills, experience entries, education entries, and projects.

<!-- sarathi:requirement id="FR-ANALYSIS-REQUIREMENTS" -->
- **Job requirements.** The report shall include the job's must-have
  requirements, nice-to-have requirements, and seniority level.

<!-- sarathi:requirement id="FR-ANALYSIS-RUBRIC" -->
- **Visible rubric.** The report shall list each rubric criterion with its
  maximum points, awarded points, and a one-sentence rationale, using the fixed
  criteria: must-have skills (40), relevant experience (25), nice-to-have
  skills (15), responsibilities and domain alignment (15), education and
  certifications (5).

<!-- sarathi:requirement id="FR-ANALYSIS-SCORE" -->
- **Score arithmetic.** The overall score shall be an integer from 0 to 100
  equal to the sum of the awarded rubric points, where the must-have and
  nice-to-have criteria are proportional to the share of those requirements
  matched.

<!-- sarathi:requirement id="FR-ANALYSIS-SKILLS" -->
- **Matched and missing skills.** The report shall list matched skills and
  missing must-have and nice-to-have skills using normalised skill names, so
  that synonyms such as "JS" and "JavaScript" count as the same skill.

<!-- sarathi:requirement id="FR-AGENTS-ROLES" -->
- **Named specialists.** Each analysis shall be carried out by an orchestrator
  that delegates to five named specialists — Resume Parser, JD Analyst,
  Matcher, Coach, and Report Writer — and each delegation shall be visible in
  the timeline.

### Coaching content

<!-- sarathi:requirement id="FR-COACH-BULLETS" -->
- **Improved bullets.** The report shall include 3 to 6 improved resume bullets,
  each naming the job requirement it targets.

<!-- sarathi:requirement id="FR-COACH-QUESTIONS" -->
- **Interview questions.** The report shall include 5 to 8 likely interview
  questions, each with a short reason it may be asked.

<!-- sarathi:requirement id="FR-COACH-LEARNING" -->
- **Learning plan.** The report shall include a learning-plan item with
  concrete actions for each missing must-have skill, up to 5 items.

### Progress

<!-- sarathi:requirement id="FR-PROGRESS-TIMELINE" -->
- **Live timeline.** While an analysis runs, the page shall append a timeline
  entry for each input-check stage (file checks, text extraction, guard
  checks, moderation), each agent message, each tool call, and each
  finishing stage (report validation, PDF rendering), showing the agent's or
  system's display name, the kind of step, and a summary of at most 200
  characters that never quotes the inputs.

<!-- sarathi:requirement id="FR-PROGRESS-STATUS" -->
- **Run status.** The page shall show the run state as running, completed, or
  failed, and disable the **Analyse** button while running.

### Report display and export

<!-- sarathi:requirement id="FR-REPORT-DISPLAY" -->
- **On-screen report.** After a successful analysis the page shall show the
  score, rubric, skills comparison, candidate profile, job requirements, and
  coaching sections.

<!-- sarathi:requirement id="FR-REPORT-JSON" -->
- **JSON download.** The visitor shall be able to download the report as a JSON
  document that validates against the published report schema, including a
  schema version.

<!-- sarathi:requirement id="FR-REPORT-MARKDOWN" -->
- **Markdown download.** The visitor shall be able to download the report as a
  Markdown document containing every on-screen section.

<!-- sarathi:requirement id="FR-REPORT-PDF" -->
- **PDF download.** The visitor shall be able to download the report as a PDF
  document containing every on-screen section.

<!-- sarathi:requirement id="FR-REPORT-PDFFALLBACK" -->
- **PDF fallback.** When PDF generation fails, the system shall still offer the
  on-screen report, JSON, and Markdown and state that PDF is unavailable.

<!-- sarathi:requirement id="FR-REPORT-SAFETEXT" -->
- **Inert report text.** Report text shown on screen or exported shall contain
  no active links, images, or HTML markup.

<!-- sarathi:requirement id="FR-REPORT-RETRY" -->
- **One retry.** When the final report fails schema validation, the system
  shall make exactly one further attempt before reporting failure, and shall
  skip that attempt and report failure when the remaining per-analysis token
  budget cannot cover it.

### Errors

<!-- sarathi:requirement id="FR-ERROR-SAFE" -->
- **Safe error messages.** Every failure shown to a visitor shall be a
  plain-language message with a support ID and shall not include exception
  text, stack traces, file paths, or configuration values.

### Usage and cost limits

The owner has accepted the default limits below; each is configurable by an
environment variable.

<!-- sarathi:requirement id="FR-COST-ADMISSION" -->
- **Early admission.** The system shall apply the per-visitor and global
  concurrency limits, and refuse a visitor whose daily quota or the global
  daily cap is already used up, before parsing the file or calling moderation.
  Admission shall not consume quota; the daily quota and global daily count
  shall be consumed only when the agent analysis starts.

<!-- sarathi:requirement id="FR-COST-DAILY" -->
- **Daily quota.** The system shall allow each visitor at most 5 started
  analyses per UTC day (default) and shall tell a visitor who exceeds it when
  the quota resets.

<!-- sarathi:requirement id="FR-COST-CONCURRENT" -->
- **One at a time.** The system shall reject a new request from a visitor who
  already has 1 request admitted or running (default).

<!-- sarathi:requirement id="FR-COST-BUSY" -->
- **Service busy.** The system shall reject a new request with a busy message
  when 3 requests (default) are already admitted or running across all
  visitors.

<!-- sarathi:requirement id="FR-COST-BUDGET" -->
- **Global daily cap.** The system shall reject new analyses for the rest of
  the UTC day once 200 started analyses (default) is reached.

<!-- sarathi:requirement id="FR-COST-STOP" -->
- **Per-analysis limits.** The system shall stop an analysis and show a limit
  message when it exceeds 180 seconds, 20 agent messages, or 150,000 model
  tokens (defaults), whichever comes first; the token count covers every model
  call of the analysis, including tool-result reflection and the report retry.

<!-- sarathi:requirement id="FR-COST-IDENTITY" -->
- **Unforgeable visitor identity.** The system shall identify a visitor for
  quotas, concurrency, and access-code lockout only from the client-address
  header that the reverse proxy sets (configurable name, default `X-Real-IP`),
  and the proxy shall overwrite any client-supplied `X-Real-IP` and
  `X-Forwarded-For` values, so forged headers change nothing.

### Access

<!-- sarathi:requirement id="FR-ACCESS-CODE" -->
- **Access code.** When an access code is configured, the system shall show
  only the code prompt until the visitor enters the correct code.

<!-- sarathi:requirement id="FR-ACCESS-LOCKOUT" -->
- **Code lockout.** After 5 incorrect codes from one visitor, the system shall
  refuse further code attempts from that visitor for 15 minutes.

### Operations

<!-- sarathi:requirement id="FR-OPS-HEALTH" -->
- **Health endpoints.** The application and the tools service shall each expose
  a health endpoint that returns success when the service can serve requests.

<!-- sarathi:requirement id="FR-OPS-LOGS" -->
- **Structured outcome log.** The system shall write one structured log event
  per analysis attempt containing the support ID, a pseudonymous visitor key,
  outcome category, stage, duration, and token counts.

## Non-Functional Requirements

### Performance and cost

<!-- sarathi:nfr id="NFR-PERF-DURATION" -->
- **Analysis duration.** At least 9 of 10 live analyses of a two-page resume and
  a job description of up to 1,000 words shall finish within 120 seconds with
  the default model (gpt-4o-mini).

<!-- sarathi:nfr id="NFR-PERF-FEEDBACK" -->
- **First feedback.** The first timeline entry shall appear within 15 seconds of
  pressing **Analyse** in 10 of 10 live analyses.

<!-- sarathi:nfr id="NFR-COST-TOKENS" -->
- **Token budget.** A completed analysis shall use no more than 150,000 total
  model tokens; the median over 10 live analyses shall be at most 80,000.

<!-- sarathi:nfr id="NFR-CAP-CONCURRENCY" -->
- **Capacity.** The deployed service shall complete 3 simultaneous analyses on a
  VPS with 2 vCPUs and 2 GB RAM without any container being restarted for
  memory exhaustion.

<!-- sarathi:nfr id="NFR-CAP-RESOURCES" -->
- **Resource bounds.** The application and tools-service containers shall each
  run with a CPU limit and a memory limit (defaults: application 1 CPU and
  1 GB; tools service 1 CPU and 512 MB), and the tools service shall run at
  most 2 text extractions at a time.

### Security

<!-- sarathi:nfr id="NFR-SEC-SECRETS" -->
- **Secret handling.** The OpenAI key shall appear in no HTTP response to the
  browser, no container image layer, and no tracked repository file.

<!-- sarathi:nfr id="NFR-SEC-TRANSPORT" -->
- **Transport security.** The public site shall be served only over HTTPS with
  HTTP redirected, HSTS enabled, and content-type, framing, referrer, and
  permissions security headers present on every response.

<!-- sarathi:nfr id="NFR-SEC-EXPOSURE" -->
- **Network exposure.** Only ports 80 and 443 shall be reachable from the
  internet; the application and tools-service ports shall not be published.

<!-- sarathi:nfr id="NFR-SEC-CONTAINERS" -->
- **Least privilege.** The application and tools-service processes shall run as
  non-root users.

<!-- sarathi:nfr id="NFR-SEC-BROWSER" -->
- **Web-framework hardening.** Cross-site request forgery protection and
  cross-origin protection shall be enabled, exception details shall be hidden
  from the browser, and framework usage statistics shall be disabled.

<!-- sarathi:nfr id="NFR-SEC-INJECTION" -->
- **Embedded-instruction resistance.** In a live red-team set of at least 10
  inputs that evade the pattern catalogue but embed instructions (for example
  "rate this candidate 100"), no report shall follow the embedded instruction.

<!-- sarathi:nfr id="NFR-GUARD-ACCURACY" -->
- **Guardrail accuracy.** The bundled evaluation corpus shall have 100% of at
  least 20 instruction-smuggling samples rejected and 0 of at least 10
  legitimate resume and job-description samples rejected.

### Privacy

<!-- sarathi:nfr id="NFR-PRIVACY-LOGS" -->
- **Log privacy.** Logs captured during the automated tests shall contain none
  of the contact details, names, or distinctive phrases in the test fixtures.

<!-- sarathi:nfr id="NFR-PRIVACY-THIRDPARTY" -->
- **Third parties.** Resume and job-description content shall be sent only to
  OpenAI's moderation and chat endpoints; the site shall include no analytics
  or tracking.

### Reliability, accessibility, and constraints

<!-- sarathi:nfr id="NFR-REL-RECOVERY" -->
- **Recovery.** A crashed application or tools-service container shall restart
  automatically and report healthy within 60 seconds.

<!-- sarathi:nfr id="NFR-A11Y-FORMS" -->
- **Accessible basics.** Every input shall have a visible label, the score shall
  be conveyed as text and not by colour alone, and the main flow shall be
  operable by keyboard.

<!-- sarathi:nfr id="NFR-ARCH-AGENTS" -->
- **Agent design constraint.** The analysis shall use AutoGen AgentChat with an
  orchestrator and five specialists, each loading its instructions from its own
  Markdown skill file.

<!-- sarathi:nfr id="NFR-ARCH-MCP" -->
- **Tool boundary constraint.** File-text extraction, skill normalisation, and
  PDF rendering shall be provided by a separate MCP server process reached over
  streamable HTTP in deployment.

<!-- sarathi:nfr id="NFR-ARCH-SIMPLE" -->
- **Simplicity constraint.** The system shall have no database, no user
  accounts, and no separate web API service besides the Streamlit application
  and the MCP tools service.

### Deployment, documentation, and testing

<!-- sarathi:nfr id="NFR-DEPLOY-COMPOSE" -->
- **One-command deployment.** On a Linux VPS with Docker and a DNS A record, the
  whole stack shall start with one `docker compose up -d` command and obtain an
  HTTPS certificate automatically.

<!-- sarathi:nfr id="NFR-DOCS-README" -->
- **Operator documentation.** The README shall cover local run, tests, VPS
  deployment, configuration variables, security notes, known limitations, and
  log retention.

<!-- sarathi:nfr id="NFR-TEST-OFFLINE" -->
- **Offline test suite.** The automated tests shall pass without an OpenAI key
  or internet access in under 5 minutes on a developer laptop.

## External Interfaces & Contracts

| Boundary | Contract source | What we rely on | Failure behaviour | How it is tested |
| --- | --- | --- | --- | --- |
| OpenAI Chat Completions (gpt-4o-mini, structured outputs, tool calling) | OpenAI API reference; AutoGen `OpenAIChatCompletionClient` 0.7.x | JSON-schema structured replies; function calls; token usage | Timeouts, rate limits, 5xx → try-later message | AutoGen's official test double `ReplayChatCompletionClient` for team behaviour; optional live test when `OPENAI_API_KEY` is set. Untested without the live run: real schema acceptance by the API, real tool-call formatting, latency, and cost. |
| OpenAI Moderation (`omni-moderation-latest`) | OpenAI moderation API reference | `flagged` per input | Unavailable → reject (fail closed) | Adapter tested with an injected client; optional live test. Real category behaviour is only checked live. |
| MCP tools service | This spec plus MCP specification (streamable HTTP transport) | Three tools: extract resume text (deadline-bounded, at most 2 at a time), normalise skills, render PDF; health endpoint | Tool error → specific or try-later message | Real server exercised in-process through FastMCP's official client, and a cross-process contract run from the application's MCP client. |
| Browser ↔ application | Streamlit web protocol via HTTPS reverse proxy | Page, websocket, file upload, downloads | Proxy or app down → browser error page | Streamlit's official `AppTest` harness; post-deploy smoke check. |
| Reverse proxy and certificates | Caddy documentation; Let's Encrypt ACME | Automatic HTTPS for the configured domain; overwrites client-supplied `X-Real-IP` and `X-Forwarded-For` with the connecting address | Issuance failure → proxy retries | Static test of the Caddyfile; post-deploy smoke check (no Docker locally). |
| Uploaded file formats | PDF (ISO 32000), Office Open XML (ECMA-376), UTF-8 | Text extraction only | Unreadable → rejection | Fixture files including malformed and hostile samples. |
| Report JSON download | Published report schema (version "1.0") | Stable field names for visitors who reuse the file | n/a | Schema validation of generated downloads. |

OpenAI data handling for API traffic is governed by OpenAI's published API data
policy (<https://platform.openai.com/docs/guides/your-data>); the privacy notice
links to it rather than restating retention periods.

## Acceptance Tests

### Upload and length checks

<!-- sarathi:acceptance id="AT-UPLOAD-TYPES" use-case="UC-ANALYSIS-RUN" verifies="FR-UPLOAD-TYPES" -->
- **Supported formats accepted, others refused.** Given valid PDF, DOCX, and
  TXT resumes, when each is analysed, then each reaches analysis; given a PNG
  image, then the visitor sees "unsupported file type".

<!-- sarathi:acceptance id="AT-UPLOAD-SIGNATURE" use-case="UC-ANALYSIS-RUN" verifies="FR-UPLOAD-SIGNATURE" -->
- **Renamed file refused.** Given a ZIP archive renamed to `resume.pdf`, when it
  is analysed, then the visitor sees that the content does not match the file
  type.

<!-- sarathi:acceptance id="AT-UPLOAD-SIZE" use-case="UC-ANALYSIS-RUN" verifies="FR-UPLOAD-SIZE" -->
- **Oversized file refused.** Given a 2.1 MB PDF, when it is analysed, then the
  visitor sees the 2 MB limit message.

<!-- sarathi:acceptance id="AT-UPLOAD-PAGES" use-case="UC-ANALYSIS-RUN" verifies="FR-UPLOAD-PAGES" -->
- **Long PDF refused.** Given a 6-page PDF, when it is analysed, then the visitor
  sees the 5-page limit message; a 5-page PDF is accepted.

<!-- sarathi:acceptance id="AT-UPLOAD-ARCHIVE" use-case="UC-ANALYSIS-RUN" verifies="FR-UPLOAD-ARCHIVE" -->
- **Hostile DOCX refused.** Given DOCX files with 501 entries, with parts
  expanding beyond 20 MB, with an encrypted entry, and with an embedded ZIP
  entry, when each is analysed, then each is refused with an unreadable-file
  message and no model call is made; a normal DOCX with a table is accepted.

<!-- sarathi:acceptance id="AT-UPLOAD-PARSETIME" use-case="UC-ANALYSIS-RUN" verifies="FR-UPLOAD-PARSETIME NFR-CAP-RESOURCES" -->
- **Slow file cut off, service stays up.** Given a file whose extraction does
  not finish within the deadline, when it is analysed, then the visitor sees
  an unreadable-file message within the deadline plus 5 seconds, the
  extraction work is stopped, the tools-service health endpoint answers
  success during and after it, and a valid resume submitted next is extracted
  normally; given 3 slow files at once, at most 2 are extracted concurrently.

<!-- sarathi:acceptance id="AT-UPLOAD-TEXTLEN" use-case="UC-ANALYSIS-RUN" verifies="FR-UPLOAD-TEXTLEN" -->
- **Unreadable or overlong text refused.** Given an image-only PDF (no text) and
  a TXT file of 20,001 characters, when each is analysed, then each is refused
  with a readable-text message; 300 and 20,000 characters are accepted.

<!-- sarathi:acceptance id="AT-INPUT-JDLEN" use-case="UC-ANALYSIS-RUN" verifies="FR-INPUT-JDLEN" -->
- **Job description bounds.** Given job descriptions of 199 and 10,001
  characters, when submitted, then each is refused with the length message; 200
  and 10,000 characters are accepted.

### Guardrails

<!-- sarathi:acceptance id="AT-GUARD-INJECTION" use-case="UC-ANALYSIS-RUN" verifies="FR-GUARD-INJECTION NFR-GUARD-ACCURACY" -->
- **Smuggled instructions refused.** Given each sample in the bundled
  instruction-smuggling corpus placed in the resume and then in the job
  description, when submitted, then every one is refused and the message names
  the affected input; every legitimate corpus sample is accepted.

<!-- sarathi:acceptance id="AT-GUARD-RESUMESHAPE" use-case="UC-ANALYSIS-RUN" verifies="FR-GUARD-RESUMESHAPE" -->
- **Non-resume refused.** Given a 2-page recipe saved as PDF, when analysed, then
  the visitor sees that the file does not look like a resume.

<!-- sarathi:acceptance id="AT-GUARD-JDSHAPE" use-case="UC-ANALYSIS-RUN" verifies="FR-GUARD-JDSHAPE" -->
- **Non-job-description refused.** Given a news article pasted as the job
  description, when submitted, then the visitor sees that it does not look like
  a job description.

<!-- sarathi:acceptance id="AT-GUARD-MODERATION" use-case="UC-ANALYSIS-RUN" verifies="FR-GUARD-MODERATION" -->
- **Flagged content refused.** Given moderation flags the job description, when
  submitted, then the visitor sees a content-policy message that does not quote
  the content.

<!-- sarathi:acceptance id="AT-GUARD-FAILCLOSED" use-case="UC-ANALYSIS-RUN" verifies="FR-GUARD-FAILCLOSED" -->
- **Moderation outage refused.** Given the moderation service times out, when a
  valid request is submitted, then the visitor sees a try-later message and no
  analysis starts.

<!-- sarathi:acceptance id="AT-GUARD-NOSPEND" use-case="UC-ANALYSIS-RUN" verifies="FR-GUARD-NOSPEND" -->
- **Rejections are free.** Given a visitor with 5 analyses left, when 3 requests
  are rejected by input checks, then no chat-model call was made and the page
  still shows 5 analyses left.

### Privacy

<!-- sarathi:acceptance id="AT-PRIVACY-REDACT" use-case="UC-ANALYSIS-RUN" verifies="FR-PRIVACY-REDACT" -->
- **Contact details never reach the model.** Given a resume and job description
  containing an email, phone number, URL, and street address, when analysed,
  then none of them appears in any text sent to the chat or moderation service
  and the placeholders do.

<!-- sarathi:acceptance id="AT-PRIVACY-NOSTORE" use-case="UC-ANALYSIS-RUN" verifies="FR-PRIVACY-NOSTORE NFR-PRIVACY-LOGS" -->
- **Nothing kept.** Given a complete analysis, a rejected analysis, and a failed
  analysis, when they finish, then no new file exists under the application's
  writable paths and captured logs contain no fixture text or contact details.

<!-- sarathi:acceptance id="AT-PRIVACY-NOTICE" use-case="UC-ANALYSIS-RUN" verifies="FR-PRIVACY-NOTICE" -->
- **Notice before upload.** Given a first visit, when the page loads, then the
  privacy notice appears above the upload control.

<!-- sarathi:acceptance id="AT-PRIVACY-THIRDPARTY" use-case="UC-ANALYSIS-RUN" verifies="NFR-PRIVACY-THIRDPARTY" -->
- **Only OpenAI receives content.** Given the deployed configuration, when the
  page and one analysis are observed, then content goes only to OpenAI's
  moderation and chat endpoints and the page loads no analytics or tracking.

### Analysis and coaching content

<!-- sarathi:acceptance id="AT-ANALYSIS-PROFILE" use-case="UC-ANALYSIS-RUN" verifies="FR-ANALYSIS-PROFILE" -->
- **Profile shown.** Given the sample resume, when analysed, then the report
  shows its skills, experience, education, and projects.

<!-- sarathi:acceptance id="AT-ANALYSIS-REQUIREMENTS" use-case="UC-ANALYSIS-RUN" verifies="FR-ANALYSIS-REQUIREMENTS" -->
- **Requirements shown.** Given the sample job description, when analysed, then
  the report shows must-have and nice-to-have requirements and seniority.

<!-- sarathi:acceptance id="AT-ANALYSIS-RUBRIC" use-case="UC-ANALYSIS-RUN" verifies="FR-ANALYSIS-RUBRIC" -->
- **Rubric shown.** Given a completed analysis, then the five fixed criteria
  appear with maximum points 40, 25, 15, 15, and 5, awarded points, and a
  rationale each.

<!-- sarathi:acceptance id="AT-ANALYSIS-SCORE" use-case="UC-ANALYSIS-RUN" verifies="FR-ANALYSIS-SCORE" -->
- **Score adds up.** Given a job with 4 must-have skills of which 3 are matched,
  when analysed, then the must-have criterion awards 30 of 40 and the overall
  score equals the sum of awarded points, even if the model proposed another
  total.

<!-- sarathi:acceptance id="AT-ANALYSIS-SKILLS" use-case="UC-ANALYSIS-RUN" verifies="FR-ANALYSIS-SKILLS" -->
- **Synonyms matched.** Given a resume listing "JS" and a job requiring
  "JavaScript", when analysed, then JavaScript appears as matched, not missing.

<!-- sarathi:acceptance id="AT-AGENTS-ROLES" use-case="UC-ANALYSIS-RUN" verifies="FR-AGENTS-ROLES NFR-ARCH-AGENTS" -->
- **Specialists visible.** Given a completed analysis, then the timeline shows
  the orchestrator delegating to the Resume Parser, JD Analyst, Matcher, Coach,
  and Report Writer, and each has its own skill file in the delivered source.

<!-- sarathi:acceptance id="AT-COACH-BULLETS" use-case="UC-ANALYSIS-RUN" verifies="FR-COACH-BULLETS" -->
- **Bullets targeted.** Given a completed analysis, then 3 to 6 improved bullets
  appear, each naming a job requirement.

<!-- sarathi:acceptance id="AT-COACH-QUESTIONS" use-case="UC-ANALYSIS-RUN" verifies="FR-COACH-QUESTIONS" -->
- **Questions listed.** Given a completed analysis, then 5 to 8 interview
  questions appear, each with a reason.

<!-- sarathi:acceptance id="AT-COACH-LEARNING" use-case="UC-ANALYSIS-RUN" verifies="FR-COACH-LEARNING" -->
- **Learning plan per gap.** Given two missing must-have skills, when analysed,
  then the learning plan has an item with actions for each of them.

### Progress and report

<!-- sarathi:acceptance id="AT-PROGRESS-TIMELINE" use-case="UC-ANALYSIS-RUN" verifies="FR-PROGRESS-TIMELINE" -->
- **Timeline grows live.** Given an analysis in progress, when a check stage
  starts or ends, an agent replies, or an agent or the system calls a tool,
  then a new entry with the agent or system name, step kind, and a summary of
  at most 200 characters that quotes no input text appears before the run
  finishes; the first entry appears before text extraction starts.

<!-- sarathi:acceptance id="AT-PROGRESS-STATUS" use-case="UC-ANALYSIS-RUN" verifies="FR-PROGRESS-STATUS" -->
- **Status visible.** Given an analysis in progress, then the state reads
  running and **Analyse** is disabled; afterwards it reads completed or failed.

<!-- sarathi:acceptance id="AT-REPORT-DISPLAY" use-case="UC-ANALYSIS-RUN" verifies="FR-REPORT-DISPLAY" -->
- **All sections shown.** Given a completed analysis, then the score, rubric,
  skills comparison, profile, requirements, and coaching sections are visible.

<!-- sarathi:acceptance id="AT-REPORT-SAFETEXT" use-case="UC-ANALYSIS-RUN" verifies="FR-REPORT-SAFETEXT" -->
- **No active content.** Given a model reply containing a Markdown image, a link,
  and a `<script>` tag, when the report is shown and exported, then none of them
  is rendered or preserved as active content.

<!-- sarathi:acceptance id="AT-REPORT-RETRY" use-case="UC-ANALYSIS-RUN" verifies="FR-REPORT-RETRY" -->
- **Single retry.** Given a first final report that violates the schema and a
  valid second one, then the report is shown; given two invalid attempts, then
  a failure message is shown and no third attempt is made; given an invalid
  first report and too little remaining token budget, then no retry is made
  and a failure message is shown.

<!-- sarathi:acceptance id="AT-ERROR-SAFE" use-case="UC-ANALYSIS-RUN" verifies="FR-ERROR-SAFE" -->
- **Errors stay friendly.** Given the tools service is down and, separately, an
  unexpected internal exception, when analysed, then the visitor sees a
  plain-language message with a support ID and no exception text or path.

<!-- sarathi:acceptance id="AT-REPORT-JSON" use-case="UC-REPORT-DOWNLOAD" verifies="FR-REPORT-JSON" -->
- **Valid JSON download.** Given a completed analysis, when JSON is downloaded,
  then it validates against the published schema and has schema version "1.0".

<!-- sarathi:acceptance id="AT-REPORT-MARKDOWN" use-case="UC-REPORT-DOWNLOAD" verifies="FR-REPORT-MARKDOWN" -->
- **Markdown download.** Given a completed analysis, when Markdown is
  downloaded, then it contains a heading for every on-screen section.

<!-- sarathi:acceptance id="AT-REPORT-PDF" use-case="UC-REPORT-DOWNLOAD" verifies="FR-REPORT-PDF" -->
- **PDF download.** Given a completed analysis, when PDF is downloaded, then it
  is a readable PDF whose text includes the score and every section heading.

<!-- sarathi:acceptance id="AT-REPORT-PDFFALLBACK" use-case="UC-REPORT-DOWNLOAD" verifies="FR-REPORT-PDFFALLBACK" -->
- **PDF failure tolerated.** Given PDF rendering fails, when the analysis
  completes, then the report, JSON, and Markdown remain available with a PDF
  unavailable note.

<!-- sarathi:acceptance id="AT-PRIVACY-CLEAR" use-case="UC-REPORT-DOWNLOAD" verifies="FR-PRIVACY-CLEAR" -->
- **Start over clears.** Given a report on screen, when **Start over** is
  pressed, then inputs, timeline, report, and download buttons disappear.

### Limits and access

<!-- sarathi:acceptance id="AT-COST-ADMISSION" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-ADMISSION FR-COST-CONCURRENT FR-COST-BUSY" -->
- **Admission before parsing, quota at start.** Given a visitor whose request
  is still in its input checks, when they submit another, then it is refused
  before any extraction or moderation call; given a request rejected by an
  input check, then the visitor's remaining quota is unchanged and their next
  request is admitted; given a visitor with no quota left, then the request is
  refused before extraction.

<!-- sarathi:acceptance id="AT-COST-FLOOD" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-ADMISSION FR-COST-BUSY" -->
- **Flood bounded.** Given 20 simultaneous requests from one visitor and 20
  from distinct visitors, when they arrive, then at most 1 per visitor and 3 in
  total reach extraction at any moment, every other request is refused as
  already running or busy, and quota is consumed only by requests whose agent
  analysis started.
<!-- sarathi:acceptance id="AT-COST-DAILY" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-DAILY" -->
- **Sixth analysis refused.** Given a visitor who started 5 analyses today, when
  a sixth is requested, then it is refused with the reset time (00:00 UTC).

<!-- sarathi:acceptance id="AT-COST-CONCURRENT" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-CONCURRENT" -->
- **Parallel run refused.** Given a visitor with an analysis running in one tab,
  when they start another in a second tab, then the second is refused.

<!-- sarathi:acceptance id="AT-COST-BUSY" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-BUSY" -->
- **Busy service.** Given 3 analyses running for other visitors, when a fourth
  visitor starts one, then they see a busy message and no quota is used.

<!-- sarathi:acceptance id="AT-COST-BUDGET" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-BUDGET" -->
- **Global cap.** Given the global daily cap is set to 2 and 2 analyses started
  today, when a different visitor starts one, then it is refused until the next
  UTC day.

<!-- sarathi:acceptance id="AT-COST-STOP" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-STOP NFR-COST-TOKENS" -->
- **Runaway analysis stopped.** Given an agent conversation that never reaches
  the Report Writer, when the message, time, or token limit is reached, then the
  run stops with a limit message; live runs stay within the token budget.

<!-- sarathi:acceptance id="AT-ACCESS-CODE" use-case="UC-ACCESS-UNLOCK" verifies="FR-ACCESS-CODE" -->
- **Code gate.** Given an access code is configured, when the page loads, then
  only the code prompt is shown; after the correct code the upload form
  appears; with no code configured the form appears directly.

<!-- sarathi:acceptance id="AT-ACCESS-LOCKOUT" use-case="UC-ACCESS-UNLOCK" verifies="FR-ACCESS-LOCKOUT" -->
- **Lockout.** Given 5 wrong codes, when a sixth code (even the correct one) is
  entered within 15 minutes, then it is refused with the lockout message.

<!-- sarathi:acceptance id="AT-COST-FORGEDHEADERS" use-case="UC-ANALYSIS-RUN" verifies="FR-COST-IDENTITY" -->
- **Forged headers change nothing.** Given a visitor who has used today's
  quota, has an analysis running, or is locked out of the access code, when
  they send requests with forged `X-Forwarded-For` and `X-Real-IP` values, then
  they are still refused, still counted as running, and still locked out; the
  deployed proxy configuration overwrites both headers.

### Operations and qualities

<!-- sarathi:acceptance id="AT-OPS-HEALTH" use-case="UC-OPS-DEPLOY" verifies="FR-OPS-HEALTH" -->
- **Health endpoints.** Given both services are running, when their health
  endpoints are requested, then each returns success.

<!-- sarathi:acceptance id="AT-OPS-LOGS" use-case="UC-OPS-DIAGNOSE" verifies="FR-OPS-LOGS" -->
- **Diagnosable by support ID.** Given a failed analysis whose message showed a
  support ID, when the logs are searched for that ID, then exactly one event
  shows its outcome category, stage, duration, and token counts.

<!-- sarathi:acceptance id="AT-PERF-DURATION" use-case="UC-ANALYSIS-RUN" verifies="NFR-PERF-DURATION NFR-PERF-FEEDBACK" -->
- **Timely results.** Given 10 live analyses of the sample resume and job
  description, then at least 9 finish within 120 seconds and all show the first
  timeline entry within 15 seconds.

<!-- sarathi:acceptance id="AT-SEC-INJECTIONLIVE" use-case="UC-ANALYSIS-RUN" verifies="NFR-SEC-INJECTION" -->
- **Embedded instructions ignored.** Given the live red-team set, when analysed,
  then no report contains the injected score, phrase, or behaviour.

<!-- sarathi:acceptance id="AT-A11Y-FORMS" use-case="UC-ANALYSIS-RUN" verifies="NFR-A11Y-FORMS" -->
- **Keyboard and labels.** Given the page, when navigated by keyboard only, then
  every input is labelled and reachable and the score is readable as text.

<!-- sarathi:acceptance id="AT-ARCH-MCP" use-case="UC-ANALYSIS-RUN" verifies="NFR-ARCH-MCP NFR-ARCH-SIMPLE" -->
- **Tools behind MCP.** Given the delivered system, when an analysis runs, then
  text extraction, skill normalisation, and PDF rendering are served by the
  separate MCP tools process and no database or extra API service exists.

<!-- sarathi:acceptance id="AT-SEC-EDGE" use-case="UC-OPS-DEPLOY" verifies="NFR-SEC-TRANSPORT NFR-SEC-EXPOSURE" -->
- **Hardened edge.** Given the deployed site, when probed from the internet,
  then HTTP redirects to HTTPS, the security headers are present, and only
  ports 80 and 443 answer.

<!-- sarathi:acceptance id="AT-SEC-CONFIG" use-case="UC-OPS-DEPLOY" verifies="NFR-SEC-SECRETS NFR-SEC-CONTAINERS NFR-SEC-BROWSER NFR-CAP-RESOURCES" -->
- **Hardened configuration.** Given the delivered deployment files, then the key
  is read only from the environment, secrets files are excluded from images and
  the repository, both services run as non-root with CPU and memory limits,
  and the web-framework hardening settings are on.

<!-- sarathi:acceptance id="AT-OPS-RECOVERY" use-case="UC-OPS-DEPLOY" verifies="NFR-REL-RECOVERY NFR-CAP-CONCURRENCY" -->
- **Recovers and copes.** Given the deployed stack, when the application process
  is killed, then it is healthy again within 60 seconds; when 3 analyses run at
  once, then all complete without a memory restart.

<!-- sarathi:acceptance id="AT-DEPLOY-COMPOSE" use-case="UC-OPS-DEPLOY" verifies="NFR-DEPLOY-COMPOSE NFR-DOCS-README" -->
- **Documented one-command deploy.** Given a fresh VPS and the README, when the
  owner follows it, then one compose command brings the site up on HTTPS.

<!-- sarathi:acceptance id="AT-TEST-OFFLINE" use-case="UC-OPS-DEPLOY" verifies="NFR-TEST-OFFLINE" -->
- **Offline tests.** Given no OpenAI key and no internet access, when the
  automated tests run, then they pass in under 5 minutes, with live tests
  reported as skipped.

## Journey Tests

<!-- sarathi:journey id="JT-ANALYSIS-FIRSTUSE" -->
- **First successful use.** On a gated deployment, a visitor enters the access
  code, reads the notice, uploads a PDF resume, pastes a job description,
  watches the timeline progress to completed, reviews every report section,
  downloads JSON, Markdown, and PDF, and presses **Start over**. Composes the
  access, notice, timeline, status, report content, download, and clear
  scenarios.

<!-- sarathi:journey id="JT-GUARD-HOSTILE" -->
- **Hostile visitor then honest retry.** A visitor submits a renamed archive, a
  resume with smuggled instructions, and an off-topic job description; each is
  refused with a specific message, no model call is made, and no quota is used;
  the visitor then submits valid inputs and receives a report. Order matters
  because quota must be unchanged by the earlier rejections.

<!-- sarathi:journey id="JT-COST-QUOTA" -->
- **Quota exhaustion.** One visitor completes five analyses, is refused a sixth
  with the reset time, while a second visitor can still analyse until the
  global cap is reached.

<!-- sarathi:journey id="JT-OPS-GOLIVE" -->
- **Go live on a VPS.** The owner sets DNS, fills in the environment file, runs
  one compose command, confirms HTTPS and security headers, confirms the tools
  service is not reachable from outside, runs one real analysis, and finds its
  support ID in logs without personal data. Performed manually after the first
  deployment because Docker is unavailable on the development machine.

## Assumptions & Open Questions

- **Review depth.** Standard review with security, privacy, and
  external-integration checks: the service is public, accepts files, handles
  personal data, and spends money on a third-party model, but holds no accounts,
  payments, or stored data. Escalate to High-assurance if accounts, stored
  resumes, payments, or agent actions on external systems are added.
- **Visitor identity.** A visitor is identified by the client address that the
  reverse proxy writes into its trusted header (overwriting any client value).
  Visitors behind one shared network address share a quota; visitors rotating
  addresses can exceed the per-visitor quota, which the global daily cap
  bounds.
- **Limits reset on restart.** Quotas and lockouts live in process memory and
  reset on restart or redeploy. Accepted for a single VPS.
- **Names are not redacted.** Personal names and employer names are sent to
  OpenAI because removing them would damage the analysis; the privacy notice
  says so.
- **English only.** Heuristic guardrails and prompts are tuned for English.
- **Heuristic limits.** Pattern-based smuggling detection can miss novel
  phrasing; delimiting inputs as data and instructing agents to ignore embedded
  instructions are the second line; an LLM-based classifier is deferred.
- **Default limits (owner-accepted 2026-09-30).** 5 analyses per visitor per
  UTC day, 1 concurrent request per visitor, 3 concurrent requests overall,
  200 analyses per UTC day overall, 150,000 tokens, 180 seconds, and 20 agent
  messages per analysis. Each is set by an environment variable.
- **Live checks.** Performance, embedded-instruction, capacity, and edge checks
  need a real OpenAI key or a real VPS and are run manually or as optional
  tests; they are not part of the offline suite.
- **Open question.** Should a DOCX page cap apply? DOCX has no reliable page
  count, so only the text-length bound applies; revisit if abuse appears.
- UI Mock Preference: Not needed. The page uses standard Streamlit components in
  a single column (notice, inputs, timeline, results, downloads); the layout
  above is sufficient intent, and the owner can review the first running build.

## Traceability

### Needs to features

| Need | Features |
| --- | --- |
| UN-SEEKER-FIT | FEAT-ANALYSIS-MATCH |
| UN-SEEKER-GAPS | FEAT-ANALYSIS-MATCH |
| UN-SEEKER-IMPROVE | FEAT-ANALYSIS-COACH |
| UN-SEEKER-TRUST | FEAT-ANALYSIS-MATCH, FEAT-PROGRESS-TIMELINE, FEAT-AGENTS-WORKFLOW |
| UN-SEEKER-KEEP | FEAT-REPORT-EXPORT |
| UN-SEEKER-PRIVACY | FEAT-PRIVACY-PROTECT |
| UN-OWNER-COST | FEAT-GUARD-INPUT, FEAT-COST-LIMITS, FEAT-ACCESS-GATE |
| UN-OWNER-SAFETY | FEAT-GUARD-INPUT, FEAT-ACCESS-GATE |
| UN-OWNER-OPERATE | FEAT-OPS-SERVICE |
| UN-REVIEWER-AGENTS | FEAT-PROGRESS-TIMELINE, FEAT-AGENTS-WORKFLOW |

### Features to use cases and requirements

| Feature | Use cases | Requirements |
| --- | --- | --- |
| FEAT-ANALYSIS-MATCH | UC-ANALYSIS-RUN | FR-ANALYSIS-PROFILE, FR-ANALYSIS-REQUIREMENTS, FR-ANALYSIS-RUBRIC, FR-ANALYSIS-SCORE, FR-ANALYSIS-SKILLS |
| FEAT-ANALYSIS-COACH | UC-ANALYSIS-RUN | FR-COACH-BULLETS, FR-COACH-QUESTIONS, FR-COACH-LEARNING |
| FEAT-PROGRESS-TIMELINE | UC-ANALYSIS-RUN | FR-PROGRESS-TIMELINE, FR-PROGRESS-STATUS, NFR-PERF-FEEDBACK |
| FEAT-REPORT-EXPORT | UC-ANALYSIS-RUN, UC-REPORT-DOWNLOAD | FR-REPORT-DISPLAY, FR-REPORT-JSON, FR-REPORT-MARKDOWN, FR-REPORT-PDF, FR-REPORT-PDFFALLBACK, FR-REPORT-SAFETEXT, FR-REPORT-RETRY, FR-ERROR-SAFE |
| FEAT-GUARD-INPUT | UC-ANALYSIS-RUN | FR-UPLOAD-TYPES, FR-UPLOAD-SIGNATURE, FR-UPLOAD-SIZE, FR-UPLOAD-PAGES, FR-UPLOAD-ARCHIVE, FR-UPLOAD-PARSETIME, FR-UPLOAD-TEXTLEN, FR-INPUT-JDLEN, FR-GUARD-INJECTION, FR-GUARD-RESUMESHAPE, FR-GUARD-JDSHAPE, FR-GUARD-MODERATION, FR-GUARD-FAILCLOSED, FR-GUARD-NOSPEND, NFR-GUARD-ACCURACY, NFR-SEC-INJECTION |
| FEAT-PRIVACY-PROTECT | UC-ANALYSIS-RUN, UC-REPORT-DOWNLOAD | FR-PRIVACY-REDACT, FR-PRIVACY-NOSTORE, FR-PRIVACY-NOTICE, FR-PRIVACY-CLEAR, NFR-PRIVACY-LOGS, NFR-PRIVACY-THIRDPARTY |
| FEAT-COST-LIMITS | UC-ANALYSIS-RUN | FR-COST-ADMISSION, FR-COST-DAILY, FR-COST-CONCURRENT, FR-COST-BUSY, FR-COST-BUDGET, FR-COST-STOP, FR-COST-IDENTITY, NFR-COST-TOKENS, NFR-PERF-DURATION |
| FEAT-ACCESS-GATE | UC-ACCESS-UNLOCK | FR-ACCESS-CODE, FR-ACCESS-LOCKOUT |
| FEAT-OPS-SERVICE | UC-OPS-DEPLOY, UC-OPS-DIAGNOSE | FR-OPS-HEALTH, FR-OPS-LOGS, NFR-SEC-SECRETS, NFR-SEC-TRANSPORT, NFR-SEC-EXPOSURE, NFR-SEC-CONTAINERS, NFR-SEC-BROWSER, NFR-REL-RECOVERY, NFR-CAP-CONCURRENCY, NFR-CAP-RESOURCES, NFR-DEPLOY-COMPOSE, NFR-DOCS-README, NFR-TEST-OFFLINE, NFR-A11Y-FORMS |
| FEAT-AGENTS-WORKFLOW | UC-ANALYSIS-RUN | FR-AGENTS-ROLES, NFR-ARCH-AGENTS, NFR-ARCH-MCP, NFR-ARCH-SIMPLE |

### Requirements to acceptance tests

| Requirement | Acceptance tests |
| --- | --- |
| FR-UPLOAD-TYPES | AT-UPLOAD-TYPES |
| FR-UPLOAD-SIGNATURE | AT-UPLOAD-SIGNATURE |
| FR-UPLOAD-SIZE | AT-UPLOAD-SIZE |
| FR-UPLOAD-PAGES | AT-UPLOAD-PAGES |
| FR-UPLOAD-ARCHIVE | AT-UPLOAD-ARCHIVE |
| FR-UPLOAD-PARSETIME | AT-UPLOAD-PARSETIME |
| FR-UPLOAD-TEXTLEN | AT-UPLOAD-TEXTLEN |
| FR-INPUT-JDLEN | AT-INPUT-JDLEN |
| FR-GUARD-INJECTION | AT-GUARD-INJECTION |
| FR-GUARD-RESUMESHAPE | AT-GUARD-RESUMESHAPE |
| FR-GUARD-JDSHAPE | AT-GUARD-JDSHAPE |
| FR-GUARD-MODERATION | AT-GUARD-MODERATION |
| FR-GUARD-FAILCLOSED | AT-GUARD-FAILCLOSED |
| FR-GUARD-NOSPEND | AT-GUARD-NOSPEND |
| FR-PRIVACY-REDACT | AT-PRIVACY-REDACT |
| FR-PRIVACY-NOSTORE | AT-PRIVACY-NOSTORE |
| FR-PRIVACY-NOTICE | AT-PRIVACY-NOTICE |
| FR-PRIVACY-CLEAR | AT-PRIVACY-CLEAR |
| FR-ANALYSIS-PROFILE | AT-ANALYSIS-PROFILE |
| FR-ANALYSIS-REQUIREMENTS | AT-ANALYSIS-REQUIREMENTS |
| FR-ANALYSIS-RUBRIC | AT-ANALYSIS-RUBRIC |
| FR-ANALYSIS-SCORE | AT-ANALYSIS-SCORE |
| FR-ANALYSIS-SKILLS | AT-ANALYSIS-SKILLS |
| FR-AGENTS-ROLES | AT-AGENTS-ROLES |
| FR-COACH-BULLETS | AT-COACH-BULLETS |
| FR-COACH-QUESTIONS | AT-COACH-QUESTIONS |
| FR-COACH-LEARNING | AT-COACH-LEARNING |
| FR-PROGRESS-TIMELINE | AT-PROGRESS-TIMELINE |
| FR-PROGRESS-STATUS | AT-PROGRESS-STATUS |
| FR-REPORT-DISPLAY | AT-REPORT-DISPLAY |
| FR-REPORT-JSON | AT-REPORT-JSON |
| FR-REPORT-MARKDOWN | AT-REPORT-MARKDOWN |
| FR-REPORT-PDF | AT-REPORT-PDF |
| FR-REPORT-PDFFALLBACK | AT-REPORT-PDFFALLBACK |
| FR-REPORT-SAFETEXT | AT-REPORT-SAFETEXT |
| FR-REPORT-RETRY | AT-REPORT-RETRY |
| FR-ERROR-SAFE | AT-ERROR-SAFE |
| FR-COST-ADMISSION | AT-COST-ADMISSION, AT-COST-FLOOD |
| FR-COST-DAILY | AT-COST-DAILY |
| FR-COST-CONCURRENT | AT-COST-CONCURRENT, AT-COST-ADMISSION |
| FR-COST-BUSY | AT-COST-BUSY, AT-COST-ADMISSION, AT-COST-FLOOD |
| FR-COST-BUDGET | AT-COST-BUDGET |
| FR-COST-STOP | AT-COST-STOP |
| FR-COST-IDENTITY | AT-COST-FORGEDHEADERS |
| FR-ACCESS-CODE | AT-ACCESS-CODE |
| FR-ACCESS-LOCKOUT | AT-ACCESS-LOCKOUT |
| FR-OPS-HEALTH | AT-OPS-HEALTH |
| FR-OPS-LOGS | AT-OPS-LOGS |

### Supplementary requirements to acceptance tests

| Requirement | Acceptance tests |
| --- | --- |
| NFR-PERF-DURATION | AT-PERF-DURATION |
| NFR-PERF-FEEDBACK | AT-PERF-DURATION |
| NFR-COST-TOKENS | AT-COST-STOP |
| NFR-CAP-CONCURRENCY | AT-OPS-RECOVERY |
| NFR-CAP-RESOURCES | AT-SEC-CONFIG, AT-UPLOAD-PARSETIME |
| NFR-SEC-SECRETS | AT-SEC-CONFIG |
| NFR-SEC-TRANSPORT | AT-SEC-EDGE |
| NFR-SEC-EXPOSURE | AT-SEC-EDGE |
| NFR-SEC-CONTAINERS | AT-SEC-CONFIG |
| NFR-SEC-BROWSER | AT-SEC-CONFIG |
| NFR-SEC-INJECTION | AT-SEC-INJECTIONLIVE |
| NFR-GUARD-ACCURACY | AT-GUARD-INJECTION |
| NFR-PRIVACY-LOGS | AT-PRIVACY-NOSTORE |
| NFR-PRIVACY-THIRDPARTY | AT-PRIVACY-THIRDPARTY |
| NFR-REL-RECOVERY | AT-OPS-RECOVERY |
| NFR-A11Y-FORMS | AT-A11Y-FORMS |
| NFR-ARCH-AGENTS | AT-AGENTS-ROLES |
| NFR-ARCH-MCP | AT-ARCH-MCP |
| NFR-ARCH-SIMPLE | AT-ARCH-MCP |
| NFR-DEPLOY-COMPOSE | AT-DEPLOY-COMPOSE |
| NFR-DOCS-README | AT-DEPLOY-COMPOSE |
| NFR-TEST-OFFLINE | AT-TEST-OFFLINE |

### Journeys to acceptance scenarios

| Journey | Composed acceptance tests | Use cases |
| --- | --- | --- |
| JT-ANALYSIS-FIRSTUSE | AT-ACCESS-CODE, AT-PRIVACY-NOTICE, AT-PROGRESS-TIMELINE, AT-PROGRESS-STATUS, AT-REPORT-DISPLAY, AT-REPORT-JSON, AT-REPORT-MARKDOWN, AT-REPORT-PDF, AT-PRIVACY-CLEAR | UC-ACCESS-UNLOCK, UC-ANALYSIS-RUN, UC-REPORT-DOWNLOAD |
| JT-GUARD-HOSTILE | AT-UPLOAD-SIGNATURE, AT-GUARD-INJECTION, AT-GUARD-JDSHAPE, AT-GUARD-NOSPEND, AT-REPORT-DISPLAY | UC-ANALYSIS-RUN |
| JT-COST-QUOTA | AT-COST-DAILY, AT-COST-BUDGET | UC-ANALYSIS-RUN |
| JT-OPS-GOLIVE | AT-DEPLOY-COMPOSE, AT-SEC-EDGE, AT-OPS-HEALTH, AT-OPS-LOGS, AT-PRIVACY-NOSTORE | UC-OPS-DEPLOY, UC-OPS-DIAGNOSE |
