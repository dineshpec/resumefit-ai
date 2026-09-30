"""JSON-lines logging with an allow-list, support IDs, and pseudonymous visitor keys.

Log events carry only allow-listed fields whose values are numbers, booleans, or
short tokens, so resume or job-description text cannot reach the logs. Records
from other libraries are reduced to their logger name and exception class.
"""

import hashlib
import hmac
import json
import logging
import math
import re
import secrets
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TextIO

from resumefit.config import Settings

LOGGER_NAME = "resumefit"
PROXY_UNKNOWN = "proxy-unknown"

EVENTS = frozenset(
    {"analysis_finished", "access_denied", "access_locked", "app_started"}
)
FIELDS = frozenset(
    {
        "support_id",
        "visitor",
        "outcome",
        "category",
        "stage",
        "duration_ms",
        "prompt_tokens",
        "completion_tokens",
        "agent_messages",
        "tool_calls",
        "file_type",
        "retry_used",
        "retry_skipped",
        "pdf_ok",
        "error_type",
    }
)
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}")
_CROCKFORD_BASE32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_FIELDS_ATTRIBUTE = "resumefit_fields"

_logger = logging.getLogger(LOGGER_NAME)


class _JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, UTC)
        entry: dict[str, object] = {
            "ts": created.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{created.microsecond // 1000:03d}Z",
            "level": record.levelname,
        }
        fields = getattr(record, _FIELDS_ATTRIBUTE, None)
        if isinstance(fields, dict):
            entry.update(fields)
        else:
            entry.update(event="library_log", logger=record.name)
            if record.exc_info and record.exc_info[0] is not None:
                entry["error_type"] = record.exc_info[0].__name__
        return json.dumps(entry, ensure_ascii=True, separators=(",", ":"))


class _JsonLinesHandler(logging.StreamHandler[TextIO]):
    """Marker type so repeated configuration replaces rather than duplicates the handler."""


def configure_logging(level: str, stream: TextIO | None = None) -> None:
    """Send JSON lines to stdout: application events at ``level``, libraries at WARNING."""
    handler = _JsonLinesHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(_JsonLinesFormatter())
    root = logging.getLogger()
    for existing in [h for h in root.handlers if isinstance(h, _JsonLinesHandler)]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.WARNING)
    _logger.setLevel(level)


def log_event(name: str, *, level: int = logging.INFO, **fields: object) -> None:
    """Write one allow-listed event; raise ``ValueError`` for anything that could carry content."""
    if name not in EVENTS:
        raise ValueError(f"unknown log event {name!r}")
    for field_name, value in fields.items():
        if field_name not in FIELDS:
            raise ValueError(f"log field {field_name!r} is not allow-listed")
        if not _is_safe_value(value):
            raise ValueError(
                f"log field {field_name!r} must be a number, boolean, or short token"
            )
    _logger.log(level, name, extra={_FIELDS_ATTRIBUTE: {"event": name, **fields}})


def new_support_id() -> str:
    return "RF-" + "".join(secrets.choice(_CROCKFORD_BASE32) for _ in range(8))


def visitor_key(ip: str, secret: str) -> str:
    """Pseudonymous visitor key: the first 16 hex characters of HMAC-SHA256(secret, ip)."""
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()[:16]


def client_identity(
    headers: Mapping[str, str], remote_ip: str | None, settings: Settings
) -> str:
    """The visitor's address, read only from the one header the reverse proxy overwrites.

    Behind the proxy, a missing, empty, or conflicting header gives the shared
    ``proxy-unknown`` identity so omitting it cannot mint fresh identities. Every
    other header, including ``X-Forwarded-For``, is ignored.
    """
    if not settings.trust_proxy_headers:
        return remote_ip or "local"
    wanted = settings.client_ip_header.lower()
    values = {
        value.strip() for name, value in headers.items() if name.lower() == wanted
    }
    if len(values) != 1:
        return PROXY_UNKNOWN
    return values.pop() or PROXY_UNKNOWN


def _is_safe_value(value: object) -> bool:
    if value is None or isinstance(value, bool | int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None
