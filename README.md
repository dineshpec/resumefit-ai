# ResumeFit AI

ResumeFit AI compares a resume with a job description and returns a scored,
explainable match report with coaching advice. It was built for a multi-agent
AI assignment. The assignment asked for:

- **A multi-agent team (Microsoft AutoGen 0.7).** An orchestrator and five
  specialists (Resume Parser, JD Analyst, Matcher, Coach, Report Writer) run in
  a `SelectorGroupChat`. After each specialist turn, the orchestrator writes a
  `NEXT: <agent>` line naming who speaks next.
- **Skills.** Each agent's instructions are in a Markdown file in
  [`app/skills/`](app/skills). The files are loaded when the app starts.
- **MCP tools.** A separate FastMCP server has three tools: extract resume
  text, normalise skill names, and render the report to PDF. The agents call
  these tools over MCP streamable HTTP.
- **Structured output.** Each specialist returns a Pydantic model. The app
  checks the final report, calculates the score itself, and offers the report
  as JSON (schema `1.0`), Markdown, and PDF downloads.

Guardrails and cost limits run before any paid model call. For details, see
[`docs/spec.md`](docs/spec.md), [`docs/design.md`](docs/design.md), and
[`docs/plan.md`](docs/plan.md).

## Architecture

```text
                 Internet (only ports 80 and 443 are open)
                                   |
                                   v
 +---------------------------------------------------------------------+
 | caddy  (caddy:2-alpine)                                             |
 |   automatic HTTPS for DOMAIN, redirects HTTP to HTTPS               |
 |   adds security headers, limits request bodies to 5 MB              |
 |   sets X-Real-IP and X-Forwarded-For to the connecting address      |
 +---------------------------------------------------------------------+
                                   |  HTTP + WebSocket, "edge" network
                                   v
 +---------------------------------------------------------------------+
 | app  (Streamlit 1.64, port 8501, not published)                     |
 |   page -> admission -> file checks -> extraction (MCP) -> text      |
 |   guards -> contact redaction -> OpenAI moderation -> AutoGen team  |
 |   -> report validation + scoring -> Markdown/JSON -> PDF (MCP)      |
 |   holds the only secret (OPENAI_API_KEY); in-memory usage limits    |
 +---------------------------------------------------------------------+
          |  MCP streamable HTTP                     |  HTTPS
          |  "private" network (internal: true)      v
          v                                   OpenAI (moderation + chat)
 +---------------------------------------------------------------------+
 | mcp  (FastMCP 4, port 8000, not published, no internet access)      |
 |   extract_resume_text | normalize_skills | render_pdf | GET /health |
 |   parses untrusted files in a killable worker process (10 s limit)  |
 +---------------------------------------------------------------------+
```

The app and the tools service use different MCP libraries: autogen-ext 0.7.5
needs `mcp<2`, and FastMCP 4 needs `mcp` 2.x. So each service has its own
requirements file, virtual environment, and image. A contract test runs the two
services as separate processes and checks that they work together.

## Run locally on Windows

You need Python 3.11. Docker is not needed on your PC. Run these commands in
PowerShell from the repository root.

1. Create both virtual environments:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python -m pip install -r app\requirements-dev.txt
   py -3.11 -m venv .venv-mcp
   .\.venv-mcp\Scripts\python -m pip install -r mcp_server\requirements-dev.txt
   ```

2. Start the tools service in its own terminal. It keeps running:

   ```powershell
   Set-Location mcp_server
   ..\.venv-mcp\Scripts\python -m resumefit_tools --host 127.0.0.1 --port 8000
   ```

   Check it from another terminal: `curl.exe http://127.0.0.1:8000/health`
   should return `{"status":"ok"}`.

3. Start the page in a second terminal:

   ```powershell
   $env:OPENAI_API_KEY = "sk-..."          # your own key; never commit it
   $env:MCP_URL = "http://127.0.0.1:8000/mcp"
   .\.venv\Scripts\python -m streamlit run app\streamlit_app.py --server.address 127.0.0.1
   ```

   Open <http://127.0.0.1:8501>. When you run locally, `TRUST_PROXY_HEADERS`
   stays at its default of `false`. The app ignores proxy headers and treats
   you as the `local` visitor.

## Tests and quality gate

```powershell
.\.venv\Scripts\python scripts\check.py
```

The gate runs these checks: `ruff format --check`, `ruff check`, `mypy` for
both packages, the application test suite (`.venv`), and the tools-service
test suite (`.venv-mcp`). The gate removes `OPENAI_API_KEY` from the
environment, so it runs offline. It uses AutoGen's replay model client, a
real in-process FastMCP server, and a real tools-service process for the
contract test. The three `live` tests are reported as skipped. To run
individual suites:

```powershell
.\.venv\Scripts\python -m pytest app\tests -q
.\.venv-mcp\Scripts\python -m pytest mcp_server\tests -q
.\.venv\Scripts\python -m pytest app\tests\test_deployment_files.py app\tests\test_dockerignore.py -q
```

The optional live check calls OpenAI and costs about US$0.50. Run it yourself
before a release:
`$env:OPENAI_API_KEY = "sk-..."; .\.venv\Scripts\python -m pytest app\tests -m live -q`.
To also run the 10 timed live runs, set `RESUMEFIT_LIVE_RUNS=10`.

Docker is not installed on the development PC. The deployment files are
checked locally only by static tests (`test_deployment_files.py`,
`test_dockerignore.py`). The `docker` job in `.github/workflows/check.yml` is
the first place where Docker actually runs. It performs these steps:

- `docker compose config -q`
- `caddy validate`
- builds both images
- checks that each image runs as a non-root user and contains no `.env` file
  and no `tests/` folder
- starts `app` and `mcp` with a read-only root filesystem and waits until
  both are healthy
- checks that the tools service answers the app and cannot reach the internet
- checks that `mcp` runs read-only with a 512 MB memory limit, then has the
  app render a small PDF and extract it again through `/mcp`, so a real
  extraction worker runs under its 256 MB limit on Linux

## Configuration

Copy `.env.example` to `.env` and edit the copy. Compose passes `.env` only to
the `app` container. Caddy receives only `DOMAIN` and `ACME_EMAIL`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DOMAIN` | `resume.dineshlabs.in` | Public host name that Caddy serves and gets a certificate for. |
| `ACME_EMAIL` | — (required) | Contact email for the Let's Encrypt account. |
| `OPENAI_API_KEY` | — (required) | OpenAI key. Only the app container receives it. If it is missing, the page shows only a configuration error. |
| `APP_ACCESS_CODE` | empty (site is open) | Optional shared code. After 5 wrong attempts, the visitor is locked out for 15 minutes. |
| `VISITOR_HASH_SECRET` | random at each start | HMAC secret for pseudonymous visitor keys. Set it so that keys and quotas stay the same across restarts. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model used by every agent. |
| `DAILY_ANALYSES_PER_VISITOR` | `5` | Analyses each visitor can run per UTC day. |
| `CONCURRENT_ANALYSES_PER_VISITOR` | `1` | Analyses one visitor can run at the same time. |
| `GLOBAL_DAILY_ANALYSES` | `200` | Analyses per UTC day for the whole site. |
| `MAX_CONCURRENT_ANALYSES` | `3` | Analyses the whole site can run at the same time. |
| `ANALYSIS_TIMEOUT_SECONDS` | `180` | Time limit for the agent team. |
| `MAX_AGENT_MESSAGES` | `20` | Message limit for the agent team. |
| `MAX_TOTAL_TOKENS` | `150000` | Token budget for one analysis. It covers the team and the report retry. |
| `MAX_OUTPUT_TOKENS_PER_CALL` | `4000` | `max_tokens` for each model call. |
| `MCP_URL` | `http://mcp:8000/mcp` | Tools-service endpoint. Compose sets this value. |
| `TRUST_PROXY_HEADERS` | `false` locally, `true` in Compose | Whether to read the visitor address from `CLIENT_IP_HEADER`. Compose sets this value. |
| `CLIENT_IP_HEADER` | `X-Real-IP` | The only header the app trusts for the visitor address. Caddy overwrites it. Compose sets this value. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |

The tools service does not read `.env`. Its settings go in the `environment`
block of the `mcp` service in `docker-compose.yml`:

- `MCP_ALLOWED_HOSTS`: set to `mcp:8000,localhost:8000,127.0.0.1:8000`.
- `EXTRACTION_TIMEOUT_SECONDS`: default `10`.
- `MAX_CONCURRENT_EXTRACTIONS`: default `2`.

Resource limits in Compose:

| Service | CPUs | Memory | Other limits |
| --- | --- | --- | --- |
| `app` | 1.0 | 1 GB | 64 MB `/tmp` tmpfs, 512 processes and threads |
| `mcp` | 1.0 | 512 MB | 64 MB `/tmp` tmpfs, 128 processes and threads; each extraction worker is limited to 256 MB and the deadline |

Fixed input limits:

- Resume: PDF, DOCX, or UTF-8 text, at most 2 MB and 5 pages
- DOCX: at most 500 entries and 20 MB uncompressed
- Resume text: 300 to 20,000 characters
- Job description: 200 to 10,000 characters

## Deploy to a VPS

These steps assume a fresh Ubuntu 22.04 or 24.04 VPS with a public IPv4
address, SSH access, and at least 2 vCPUs and 2 GB of RAM. Run the commands
on the VPS.

1. **DNS.** At your DNS provider, create an `A` record for
   `resume.dineshlabs.in` that points to the VPS address. If the VPS has IPv6,
   also create an `AAAA` record, but only if Docker can route IPv6 to the
   containers (see the IPv6 note below). Wait until
   `dig +short resume.dineshlabs.in` returns the VPS address. Caddy cannot get
   a certificate until the record resolves.
2. **Firewall.** Allow only SSH, HTTP, and HTTPS:
   `sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw allow 443/udp && sudo ufw enable`.
   If your provider has a cloud firewall, open the same ports there.
3. **Install Docker Engine and the Compose plugin.** Follow
   <https://docs.docker.com/engine/install/ubuntu/>. For example:
   `curl -fsSL https://get.docker.com | sudo sh`. Then run
   `sudo usermod -aG docker $USER`, log out, and log back in. Check the
   install with `docker compose version`.
4. **Get the code:**
   `git clone <repository-url> resumefit-ai && cd resumefit-ai`.
5. **Configure:** run `cp .env.example .env && chmod 600 .env`, then edit
   `.env`:
   - Set `OPENAI_API_KEY`.
   - Set `ACME_EMAIL` to an address you read.
   - Set `VISITOR_HASH_SECRET` to the output of
     `python3 -c "import secrets; print(secrets.token_hex(32))"`.
   - Optionally, set `APP_ACCESS_CODE`.
   - Keep `DOMAIN=resume.dineshlabs.in`, or change it to your host name.

   Do not put a `$` character in the values. Compose treats `$` as the start
   of a variable. If a value needs a `$`, write `$$` instead.
6. **Start:** `docker compose up -d --build`. The first build takes a few
   minutes. Caddy starts after `app` is healthy, and `app` starts after `mcp`
   is healthy.
7. **Verify:**
   - `docker compose ps` shows all three services running, and `app` and
     `mcp` are marked `(healthy)`.
   - `docker compose logs caddy | grep -i certificate` shows that a
     certificate was obtained.
   - `curl -I https://resume.dineshlabs.in` returns `200` with the security
     headers.
   - Open the site in a browser and run one analysis.

**IPv6 note.** The `edge` network in `docker-compose.yml` has IPv6 enabled
(`enable_ipv6: true`, ULA subnet `fd00:dead:beef::/64`). Docker then forwards
IPv6 visitors to Caddy with their own address, so each one gets its own
visitor key and quota. Without it, Docker's userland proxy rewrites every IPv6
visitor to the bridge gateway address, and all of them share one identity.
This needs Docker Engine 27 or newer, where `ip6tables` is on by default. On an
older engine, add `"ip6tables": true` (and `"experimental": true` before 27)
to `/etc/docker/daemon.json` and run `sudo systemctl restart docker`. Check with
`docker network inspect resumefit_edge --format '{{.EnableIPv6}}'` (prints
`true`). If you cannot enable IPv6 in Docker, do not publish the `AAAA` record;
visitors then reach the site over IPv4 only.

**Operate:**

- Logs: `docker compose logs -f app` (also `mcp` or `caddy`).
- Restart: `docker compose restart app`.
- Stop: `docker compose down`. This keeps the `caddy_data` certificate volume.
- Update: `git pull && docker compose up -d --build`.
- Clean up old images: `docker image prune -f`.
- Roll back: `git checkout <previous-commit> && docker compose up -d --build`.
  There is no data to migrate.
- Backups: not needed. The service stores no data. The only volume holds
  Caddy's certificates, and Caddy gets them again if the volume is lost.
  Let's Encrypt has rate limits, so do not delete the volume often.

## Post-deploy smoke checklist

Run this checklist after the first deployment and after major changes. Record
the result of each item.

- [ ] `curl -I http://resume.dineshlabs.in` returns a redirect (`308`) to `https://`.
- [ ] `curl -I https://resume.dineshlabs.in` shows `Strict-Transport-Security`,
      `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
      `Permissions-Policy`, and `Content-Security-Policy` (with
      `frame-ancestors 'none'`). There is no `Server` header.
- [ ] From another machine, `nmap -Pn -p 1-10000 <vps-ip>` shows only 22, 80,
      and 443 open. Ports 8501 and 8000 are closed.
- [ ] `docker compose ps` shows `app` and `mcp` as `(healthy)`.
- [ ] Recovery: `sudo kill -9 $(docker inspect -f '{{.State.Pid}}' resumefit-app-1)`.
      `app` shows `(healthy)` again within 60 seconds. Repeat with
      `resumefit-mcp-1`. `docker compose kill` does not work for this test,
      because Docker does not restart a container that was stopped by hand.
- [ ] Load: start 3 analyses at the same time from different browsers or
      networks. All 3 finish, `docker stats` shows CPU at or below the limits,
      and `docker compose ps` shows no restarts.
- [ ] Forged headers: set `APP_ACCESS_CODE`, then enter a wrong code once from
      a normal browser. Enter a wrong code again with forged `X-Real-IP` and
      `X-Forwarded-For` request headers (for example, with a header-editing
      browser extension). Both `access_denied` log lines show the same
      `visitor` key.
- [ ] The browser network panel shows requests only to the site itself: no
      analytics and no third-party requests.
- [ ] Keyboard only: you can reach the access code, upload, job description,
      **Analyse**, **Start over**, and the downloads with Tab. Each one shows a
      visible focus indicator.
- [ ] `docker compose logs app | grep RF-` finds the support ID from a failed
      analysis. Searching for the email address or phone number from a test
      resume finds nothing.

## Security and privacy

- **Edge:** Caddy is the only service with published ports (80 and 443). It
  handles TLS, HSTS, and redirects from HTTP to HTTPS. On every response, it
  sets `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive
  `Permissions-Policy`, and a CSP with `frame-ancestors 'none'`,
  `object-src 'none'`, `base-uri 'self'`, and `form-action 'self'`. It
  removes the `Server` header and rejects request bodies larger than 5 MB.
  Caddy also overwrites `X-Real-IP` and `X-Forwarded-For` with the connecting
  address. The app trusts only `X-Real-IP`, so visitors cannot fake another
  identity to get around their quota.
- **Network isolation:** `mcp` is only on the `private` network
  (`internal: true`). It cannot reach the internet, and it cannot be reached
  from outside. `app` is on both networks and is reachable only through Caddy.
- **Containers:** `app` and `mcp` run as a non-root user (UID 10001) and use a
  read-only root filesystem with a 64 MB tmpfs for `/tmp` (`HOME=/tmp`). They
  drop all Linux capabilities and use `no-new-privileges`. They also have CPU,
  memory, and process limits, health checks, and `restart: unless-stopped`.
  Caddy keeps only `NET_BIND_SERVICE`.
- **Secrets:** The OpenAI key is read only from the environment and only by
  `app`. `.env` is in `.gitignore` and in both `.dockerignore` files, so it
  never enters the repository or an image. The CI job checks this.
- **Untrusted files:** Uploaded files are parsed only in the tools service,
  which holds no secrets and has no internet access. Parsing runs in a
  separate worker process that is stopped after 10 seconds. The service
  enforces limits on size, pages, and DOCX entries and expansion, and rejects
  encrypted or nested archives.
- **Guardrails before spending:** Every request goes through these steps in
  order:
  1. Admission: one analysis per visitor and three for the whole site.
  2. File and length checks.
  3. Detection of hidden instructions and plausibility checks for resumes and
     job descriptions.
  4. Redaction of contact details (email, phone, web address, street
     address).
  5. OpenAI moderation. If moderation fails, the request is rejected.

  Only after all of these steps does the request use up quota and start the
  agent team. The agents see only redacted text inside data markers. The app
  calculates the score itself and removes active content from every string.
- **Browser:** Streamlit's XSRF and CORS protection are on. Error details are
  hidden, and usage statistics are turned off. There is no analytics or
  tracking.
- **Privacy:** Resumes and job descriptions are processed in memory and never
  written to disk or to logs. Their content goes only to OpenAI's moderation
  and chat endpoints. Caddy writes no access log.

## Logs

- **App:** JSON lines on stdout. There are four events:
  - `app_started`
  - `access_denied`
  - `access_locked`
  - `analysis_finished`: support ID, pseudonymous visitor key, outcome,
    category, stage, duration, token counts, agent and tool counts
  Logs contain no resume or job-description text.
- **Tools service:** logs only the tool name, result code, and duration.
- **Retention:** Docker's `json-file` driver keeps at most 3 × 10 MB of logs
  per service. Older lines are deleted.
- **Find a failure:** a visitor can quote the support ID (`RF-XXXXXXXX`) that
  the page shows. To find the matching log line, run
  `docker compose logs app | grep RF-XXXXXXXX`.

## Report schema

The JSON download follows schema version `1.0` (`MatchReport` in
`app/resumefit/schemas.py`). To print the JSON Schema:

```powershell
.\.venv\Scripts\python -c "import json, sys; sys.path.insert(0, 'app'); from resumefit.schemas import MatchReport; print(json.dumps(MatchReport.model_json_schema(), indent=2))"
```

## Known limitations

- **Usage limits are kept in memory.** A restart resets the quotas. Visitors
  who share an address (for example, an office network) share one quota. A
  visitor who changes addresses can get around the per-visitor quota, but the
  site-wide daily limit and the limits on your OpenAI account still cap the
  cost. Only one app replica is supported.
- **Names are not redacted.** Names and employers are sent to OpenAI. The
  page's notice says so.
- **Content support is limited.** The checks are tuned for English. PDF export
  supports only Latin-1 characters, and other characters appear as `?`. DOCX
  files have no page limit; only the text-length limit applies.
- **Prompt injection is not fully prevented.** New phrasings can get past the
  pattern checks. They can affect only the parts of the score that the model
  judges, not the skill-coverage score.
- **There is no script Content Security Policy.** Streamlit needs inline
  resources, so the policy sets only `frame-ancestors`, `object-src`,
  `base-uri`, and `form-action`.
- **Docker restarts only crashed containers.** It does not restart a container
  that becomes unhealthy but keeps running. `docker compose ps` shows the
  health status.
- **The deployment has not been tested on a real server yet.** The images,
  Compose file, Caddy, and read-only Streamlit have been checked only by
  static tests and the CI `docker` job. The TLS certificate, WebSocket
  proxying through Caddy, and the smoke checklist can be confirmed only on
  the VPS.
