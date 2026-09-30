"""Application settings read once from the environment."""

import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, fields
from urllib.parse import urlsplit

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_HEADER_NAME = re.compile(r"[A-Za-z0-9-]+")
_SECRET_FIELDS = {"openai_api_key", "app_access_code", "visitor_hash_secret"}


class ConfigError(ValueError):
    """A setting is missing or invalid; the message names the variable, never its value."""


@dataclass(frozen=True, repr=False)
class Settings:
    openai_api_key: str
    openai_model: str
    app_access_code: str
    visitor_hash_secret: str
    daily_analyses_per_visitor: int
    concurrent_analyses_per_visitor: int
    global_daily_analyses: int
    max_concurrent_analyses: int
    analysis_timeout_s: int
    max_agent_messages: int
    max_total_tokens: int
    max_output_tokens_per_call: int
    mcp_url: str
    trust_proxy_headers: bool
    client_ip_header: str
    log_level: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        env = _Env(environ)
        api_key = env.text("OPENAI_API_KEY", "")
        if not api_key:
            raise ConfigError("OPENAI_API_KEY must be set")
        return cls(
            openai_api_key=api_key,
            openai_model=env.text("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini",
            app_access_code=env.text("APP_ACCESS_CODE", ""),
            visitor_hash_secret=env.text("VISITOR_HASH_SECRET", "")
            or secrets.token_hex(32),
            daily_analyses_per_visitor=env.positive_int(
                "DAILY_ANALYSES_PER_VISITOR", 5
            ),
            concurrent_analyses_per_visitor=env.positive_int(
                "CONCURRENT_ANALYSES_PER_VISITOR", 1
            ),
            global_daily_analyses=env.positive_int("GLOBAL_DAILY_ANALYSES", 200),
            max_concurrent_analyses=env.positive_int("MAX_CONCURRENT_ANALYSES", 3),
            analysis_timeout_s=env.positive_int("ANALYSIS_TIMEOUT_SECONDS", 180),
            max_agent_messages=env.positive_int("MAX_AGENT_MESSAGES", 20),
            max_total_tokens=env.positive_int("MAX_TOTAL_TOKENS", 150_000),
            max_output_tokens_per_call=env.positive_int(
                "MAX_OUTPUT_TOKENS_PER_CALL", 4_000
            ),
            mcp_url=env.http_url("MCP_URL", "http://mcp:8000/mcp"),
            trust_proxy_headers=env.flag("TRUST_PROXY_HEADERS", False),
            client_ip_header=env.header_name("CLIENT_IP_HEADER", "X-Real-IP"),
            log_level=env.log_level("LOG_LEVEL", "INFO"),
        )

    def __repr__(self) -> str:
        shown = []
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name in _SECRET_FIELDS:
                value = "***" if value else ""
            shown.append(f"{field.name}={value!r}")
        return f"Settings({', '.join(shown)})"


class _Env:
    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ

    def text(self, name: str, default: str) -> str:
        return self._environ.get(name, default).strip()

    def positive_int(self, name: str, default: int) -> int:
        raw = self.text(name, "")
        if not raw:
            return default
        if not (raw.isascii() and raw.isdigit()) or int(raw) < 1:
            raise ConfigError(f"{name} must be a positive integer")
        return int(raw)

    def flag(self, name: str, default: bool) -> bool:
        raw = self.text(name, "").lower()
        if not raw:
            return default
        if raw in _TRUE:
            return True
        if raw in _FALSE:
            return False
        raise ConfigError(f"{name} must be true or false")

    def http_url(self, name: str, default: str) -> str:
        raw = self.text(name, "") or default
        parts = urlsplit(raw)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ConfigError(f"{name} must be an http or https URL")
        return raw

    def header_name(self, name: str, default: str) -> str:
        raw = self.text(name, "") or default
        if not _HEADER_NAME.fullmatch(raw):
            raise ConfigError(f"{name} must be a single HTTP header name")
        return raw

    def log_level(self, name: str, default: str) -> str:
        raw = (self.text(name, "") or default).upper()
        if raw not in _LOG_LEVELS:
            raise ConfigError(f"{name} must be one of {', '.join(_LOG_LEVELS)}")
        return raw
