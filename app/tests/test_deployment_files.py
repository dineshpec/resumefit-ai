"""Static checks of the deployment files.

Docker is not available on the development machine, so these tests read the
Compose file, Dockerfiles, Caddyfile, environment example, and README as text or
YAML. Image builds and ``docker compose config`` run in the CI Docker job.
"""

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from resumefit.config import Settings

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker-compose.yml"
CADDYFILE = ROOT / "Caddyfile"
ENV_EXAMPLE = ROOT / ".env.example"
README = ROOT / "README.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"
DEPLOYMENT_ONLY_KEYS = {"DOMAIN", "ACME_EMAIL"}
HARDENED_SERVICES = ("app", "mcp")


def compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def service(name: str) -> dict[str, Any]:
    return compose()["services"][name]


def service_environment(name: str) -> dict[str, str]:
    environment = service(name).get("environment", {})
    if isinstance(environment, list):
        environment = dict(item.split("=", 1) for item in environment)
    return {key: str(value) for key, value in environment.items()}


def env_example() -> dict[str, str]:
    values = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def settings_variables() -> set[str]:
    """Every environment variable the application's settings read."""

    read: set[str] = set()

    class RecordingEnvironment(dict[str, str]):
        def get(self, key: str, default: Any = None) -> Any:
            read.add(key)
            return super().get(key, default)

    Settings.from_env(RecordingEnvironment(OPENAI_API_KEY="placeholder"))
    return read


def dockerfile_instructions(context: str) -> list[tuple[str, str]]:
    text = (ROOT / context / "Dockerfile").read_text(encoding="utf-8")
    text = re.sub(r"\\\n", " ", text)
    instructions = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keyword, _, arguments = line.partition(" ")
            instructions.append((keyword.upper(), arguments.strip()))
    return instructions


def final_stage(context: str) -> list[tuple[str, str]]:
    instructions = dockerfile_instructions(context)
    last_from = max(
        index for index, (keyword, _) in enumerate(instructions) if keyword == "FROM"
    )
    return instructions[last_from:]


def caddyfile() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


# Compose: exposure and networks


def test_only_the_three_planned_services_exist() -> None:
    assert set(compose()["services"]) == {"caddy", "app", "mcp"}


def test_only_caddy_publishes_ports_80_and_443() -> None:
    services = compose()["services"]
    for name in HARDENED_SERVICES:
        assert "ports" not in services[name], f"{name} must not publish ports"
    published = {str(port) for port in services["caddy"]["ports"]}
    assert published == {"80:80", "443:443", "443:443/udp"}


def test_app_and_mcp_expose_their_ports_only_inside_compose() -> None:
    assert [str(port) for port in service("app")["expose"]] == ["8501"]
    assert [str(port) for port in service("mcp")["expose"]] == ["8000"]


def test_tools_service_is_only_on_internal_network() -> None:
    networks = compose()["networks"]
    assert service("mcp")["networks"] == ["private"]
    assert networks["private"]["internal"] is True


def test_app_reaches_the_edge_and_the_tools_service() -> None:
    networks = compose()["networks"]
    assert sorted(service("app")["networks"]) == ["edge", "private"]
    assert sorted(service("caddy")["networks"]) == ["edge"]
    assert not (networks["edge"] or {}).get("internal", False)


# Compose: hardening, limits, recovery


@pytest.mark.parametrize("name", HARDENED_SERVICES)
def test_app_and_mcp_run_read_only_without_capabilities(name: str) -> None:
    definition = service(name)
    assert definition["read_only"] is True
    assert definition["cap_drop"] == ["ALL"]
    assert "cap_add" not in definition
    assert "no-new-privileges:true" in definition["security_opt"]
    assert any(str(mount).startswith("/tmp") for mount in definition["tmpfs"])
    assert service_environment(name)["HOME"] == "/tmp"


def test_caddy_keeps_only_the_capability_to_bind_web_ports() -> None:
    definition = service("caddy")
    assert definition["cap_drop"] == ["ALL"]
    assert definition["cap_add"] == ["NET_BIND_SERVICE"]
    assert "no-new-privileges:true" in definition["security_opt"]


def test_app_and_mcp_have_cpu_and_memory_limits() -> None:
    assert float(service("app")["cpus"]) == 1.0
    assert str(service("app")["mem_limit"]).lower() in {"1g", "1024m"}
    assert float(service("mcp")["cpus"]) == 1.0
    assert str(service("mcp")["mem_limit"]).lower() == "512m"


@pytest.mark.parametrize("name", ["caddy", "app", "mcp"])
def test_every_service_restarts_and_rotates_its_logs(name: str) -> None:
    definition = service(name)
    assert definition["restart"] == "unless-stopped"
    assert definition["logging"]["driver"] == "json-file"
    assert definition["logging"]["options"] == {"max-size": "10m", "max-file": "3"}


@pytest.mark.parametrize(
    ("name", "url"),
    [
        ("app", "http://127.0.0.1:8501/_stcore/health"),
        ("mcp", "http://127.0.0.1:8000/health"),
    ],
)
def test_app_and_mcp_health_checks_probe_their_health_routes(
    name: str, url: str
) -> None:
    check = service(name)["healthcheck"]
    command = " ".join(check["test"])
    assert check["test"][0] == "CMD"
    assert url in command
    assert check["interval"] == "15s"
    assert check["retries"] == 3


def test_start_order_waits_for_healthy_dependencies() -> None:
    assert service("app")["depends_on"]["mcp"]["condition"] == "service_healthy"
    assert service("caddy")["depends_on"]["app"]["condition"] == "service_healthy"


# Compose: configuration and secrets


def test_app_trusts_only_the_client_ip_header_caddy_overwrites() -> None:
    environment = service_environment("app")
    assert environment["TRUST_PROXY_HEADERS"] == "true"
    assert environment["CLIENT_IP_HEADER"] == "X-Real-IP"
    assert environment["MCP_URL"] == "http://mcp:8000/mcp"


def test_only_the_app_reads_the_secrets_file() -> None:
    assert service("app")["env_file"] in (".env", [".env"])
    assert "env_file" not in service("mcp")
    assert "env_file" not in service("caddy")


def test_tools_service_accepts_the_internal_host_name() -> None:
    hosts = service_environment("mcp")["MCP_ALLOWED_HOSTS"].split(",")
    assert "mcp:8000" in hosts


def test_caddy_gets_domain_and_acme_email_from_the_environment() -> None:
    environment = service_environment("caddy")
    assert "${DOMAIN" in environment["DOMAIN"]
    assert "${ACME_EMAIL" in environment["ACME_EMAIL"]
    volumes = [str(volume) for volume in service("caddy")["volumes"]]
    assert "./Caddyfile:/etc/caddy/Caddyfile:ro" in volumes
    assert {"caddy_data", "caddy_config"} <= set(compose()["volumes"])


def test_images_are_built_from_their_own_contexts() -> None:
    assert service("app")["build"] == "./app"
    assert service("mcp")["build"] == "./mcp_server"
    assert service("caddy")["image"] == "caddy:2-alpine"


def test_env_example_keys_match_settings_contract() -> None:
    assert set(env_example()) == settings_variables() | DEPLOYMENT_ONLY_KEYS


def test_env_example_contains_no_real_secret() -> None:
    values = env_example()
    for key in ("OPENAI_API_KEY", "APP_ACCESS_CODE", "VISITOR_HASH_SECRET"):
        assert values[key] == "", f"{key} must be empty in the example"
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert not re.search(r"sk-[A-Za-z0-9_-]{8,}", text)


def test_env_example_defaults_match_the_settings_defaults() -> None:
    values = env_example()
    defaults = Settings.from_env({"OPENAI_API_KEY": "placeholder"})
    assert int(values["DAILY_ANALYSES_PER_VISITOR"]) == (
        defaults.daily_analyses_per_visitor
    )
    assert int(values["GLOBAL_DAILY_ANALYSES"]) == defaults.global_daily_analyses
    assert int(values["MAX_CONCURRENT_ANALYSES"]) == defaults.max_concurrent_analyses
    assert int(values["MAX_TOTAL_TOKENS"]) == defaults.max_total_tokens
    assert values["DOMAIN"] == "resume.dineshlabs.in"


def test_git_ignores_the_secrets_file() -> None:
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in lines
    assert "!.env.example" in lines


# Dockerfiles


@pytest.mark.parametrize("context", ["app", "mcp_server"])
def test_both_images_run_as_non_root_user(context: str) -> None:
    stage = final_stage(context)
    keywords = [keyword for keyword, _ in stage]
    users = [arguments for keyword, arguments in stage if keyword == "USER"]
    assert users, "the final stage must set USER"
    assert users[-1].split(":")[0] not in {"root", "0"}
    assert keywords.index("USER") < keywords.index("CMD")


@pytest.mark.parametrize("context", ["app", "mcp_server"])
def test_images_use_the_pinned_slim_python_base(context: str) -> None:
    bases = [
        arguments.split()[0]
        for keyword, arguments in dockerfile_instructions(context)
        if keyword == "FROM"
    ]
    assert bases and all(base == "python:3.11-slim" for base in bases)


@pytest.mark.parametrize("context", ["app", "mcp_server"])
def test_images_install_only_runtime_requirements(context: str) -> None:
    runs = " ".join(
        arguments
        for keyword, arguments in dockerfile_instructions(context)
        if keyword == "RUN"
    )
    assert "requirements.txt" in runs
    assert "requirements-dev" not in runs
    assert "--no-cache-dir" in runs


@pytest.mark.parametrize(
    ("context", "command"),
    [
        ("app", ["streamlit", "run", "streamlit_app.py"]),
        ("mcp_server", ["python", "-m", "resumefit_tools.server"]),
    ],
)
def test_images_start_the_planned_entry_points(
    context: str, command: list[str]
) -> None:
    stage = dict(final_stage(context))
    assert stage["WORKDIR"] == "/app"
    assert yaml.safe_load(stage["CMD"]) == command


# Streamlit hardening read by the app image


def test_streamlit_config_keeps_web_framework_hardening() -> None:
    config = tomllib.loads(
        (ROOT / "app" / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    )
    assert config["server"]["port"] == 8501
    assert config["server"]["address"] == "0.0.0.0"
    assert config["server"]["headless"] is True
    assert config["server"]["enableXsrfProtection"] is True
    assert config["server"]["enableCORS"] is True
    assert config["server"]["fileWatcherType"] == "none"
    assert config["browser"]["gatherUsageStats"] is False
    assert config["client"]["showErrorDetails"] == "none"


# Caddy


def test_caddyfile_serves_the_configured_domain_with_acme_email() -> None:
    text = caddyfile()
    assert re.search(r"^\{\$DOMAIN\}\s*\{", text, re.MULTILINE)
    assert re.search(r"^\s*email\s+\{\$ACME_EMAIL\}\s*$", text, re.MULTILINE)


@pytest.mark.parametrize(
    "header",
    [
        'Strict-Transport-Security "max-age=31536000; includeSubDomains"',
        'X-Content-Type-Options "nosniff"',
        'X-Frame-Options "DENY"',
        'Referrer-Policy "strict-origin-when-cross-origin"',
        'Permissions-Policy "camera=(), microphone=(), geolocation=()"',
        "-Server",
    ],
)
def test_caddyfile_sets_every_security_header(header: str) -> None:
    assert header in caddyfile()


def test_caddyfile_forbids_framing_in_the_content_security_policy() -> None:
    policy = re.search(r'Content-Security-Policy\s+"([^"]+)"', caddyfile())
    assert policy is not None
    directives = {part.strip() for part in policy.group(1).split(";")}
    assert "frame-ancestors 'none'" in directives
    assert "object-src 'none'" in directives


def test_caddyfile_overwrites_client_ip_headers() -> None:
    text = caddyfile()
    proxy = re.search(
        r"reverse_proxy\s+app:8501\s*\{(?P<body>.*?)^\s*\}\s*$",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert proxy is not None
    body = proxy.group("body")
    assert re.search(r"header_up\s+X-Real-IP\s+\{remote_host\}", body)
    assert re.search(r"header_up\s+X-Forwarded-For\s+\{remote_host\}", body)


def test_caddyfile_limits_request_bodies_and_compresses() -> None:
    text = caddyfile()
    assert re.search(r"request_body\s*\{\s*max_size\s+5MB\s*\}", text)
    assert re.search(r"encode\s+zstd\s+gzip", text)


def test_caddyfile_adds_no_access_log_or_third_party_upstream() -> None:
    text = caddyfile()
    assert not re.search(r"^\s*log\b", text, re.MULTILINE)
    assert re.findall(r"reverse_proxy\s+(\S+)", text) == ["app:8501"]


# CI Docker job


def test_ci_validates_compose_and_builds_both_images() -> None:
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))
    commands = "\n".join(
        step.get("run", "") for step in workflow["jobs"]["docker"]["steps"]
    )
    assert "cp .env.example .env" in commands
    assert "docker compose config -q" in commands
    assert "docker compose build app mcp" in commands
    assert "id -u" in commands


# README


def readme_headings() -> list[str]:
    return [
        line.lstrip("#").strip().lower()
        for line in README.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    ]


@pytest.mark.parametrize(
    "section",
    [
        "architecture",
        "run locally",
        "tests",
        "configuration",
        "deploy",
        "smoke checklist",
        "security",
        "limitations",
        "logs",
        "report schema",
    ],
)
def test_readme_has_deploy_security_and_limitations_sections(section: str) -> None:
    assert any(section in heading for heading in readme_headings())


def test_readme_documents_every_environment_variable() -> None:
    text = README.read_text(encoding="utf-8")
    for key in env_example():
        assert f"`{key}`" in text, f"README must document {key}"
