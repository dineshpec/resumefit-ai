from datetime import UTC, datetime

import pytest

from resumefit.config import Settings
from resumefit.limits import AccessGate, AdmissionLease, Refusal, UsageLimiter
from resumefit.observability import PROXY_UNKNOWN, client_identity, visitor_key

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
PROXY_SET_ADDRESS = "203.0.113.7"
SECRET = "test-secret"


def settings(trust_proxy_headers=True, client_ip_header="X-Real-IP"):
    return Settings.from_env(
        {
            "OPENAI_API_KEY": "sk-test-not-a-real-key",
            "TRUST_PROXY_HEADERS": str(trust_proxy_headers),
            "CLIENT_IP_HEADER": client_ip_header,
            "VISITOR_HASH_SECRET": SECRET,
        }
    )


FORGERIES = [
    {},
    {"X-Forwarded-For": "198.51.100.1"},
    {"x-forwarded-for": "198.51.100.2, 203.0.113.7"},
    {"Forwarded": "for=198.51.100.3"},
    {"FORWARDED": "for=198.51.100.4;proto=https"},
    {"X-Client-IP": "198.51.100.5"},
    {"x-client-ip": "198.51.100.6", "X-FORWARDED-FOR": "198.51.100.7"},
]


def key_for(headers, remote_ip="10.0.0.2", config=None):
    config = config or settings()
    return visitor_key(
        client_identity(headers, remote_ip, config), config.visitor_hash_secret
    )


@pytest.mark.parametrize("forged", FORGERIES)
@pytest.mark.parametrize("trusted_name", ["X-Real-IP", "x-real-ip", "X-REAL-IP"])
def test_forged_forwarded_for_does_not_change_visitor_key(forged, trusted_name):
    expected = key_for({"X-Real-IP": PROXY_SET_ADDRESS})

    assert key_for({trusted_name: PROXY_SET_ADDRESS, **forged}) == expected


def test_trusted_header_value_is_stripped():
    assert (
        client_identity({"X-Real-IP": f"  {PROXY_SET_ADDRESS} "}, None, settings())
        == PROXY_SET_ADDRESS
    )


@pytest.mark.parametrize(
    "headers", [{}, {"X-Forwarded-For": "198.51.100.1"}, {"X-Real-IP": "   "}]
)
def test_missing_trusted_header_resolves_to_the_shared_unknown_identity(headers):
    assert client_identity(headers, "10.0.0.2", settings()) == PROXY_UNKNOWN


def test_conflicting_copies_of_the_trusted_header_resolve_to_the_shared_unknown_identity():
    headers = {"X-Real-IP": PROXY_SET_ADDRESS, "x-real-ip": "198.51.100.9"}

    assert client_identity(headers, "10.0.0.2", settings()) == PROXY_UNKNOWN


def test_configured_header_name_is_the_only_one_read():
    config = settings(client_ip_header="CF-Connecting-IP")
    headers = {"CF-Connecting-IP": PROXY_SET_ADDRESS, "X-Real-IP": "198.51.100.1"}

    assert client_identity(headers, None, config) == PROXY_SET_ADDRESS


def test_headers_are_ignored_when_proxy_headers_are_not_trusted():
    config = settings(trust_proxy_headers=False)
    headers = {"X-Real-IP": PROXY_SET_ADDRESS, "X-Forwarded-For": "198.51.100.1"}

    assert client_identity(headers, "10.0.0.2", config) == "10.0.0.2"
    assert client_identity(headers, None, config) == "local"


def test_quota_exhausted_visitor_stays_refused_with_forged_headers():
    usage = UsageLimiter(per_visitor_daily=1, global_daily=200, max_concurrent=3)
    lease = usage.try_admit(key_for({"X-Real-IP": PROXY_SET_ADDRESS}), NOW)
    assert isinstance(lease, AdmissionLease)
    assert lease.start(NOW) is None
    lease.release()

    for forged in FORGERIES:
        visitor = key_for({"X-Real-IP": PROXY_SET_ADDRESS, **forged})
        assert usage.try_admit(visitor, NOW) == Refusal(
            "quota", datetime(2026, 3, 11, tzinfo=UTC)
        )


def test_running_visitor_stays_already_running_with_forged_headers():
    usage = UsageLimiter(per_visitor_daily=5, global_daily=200, max_concurrent=3)
    lease = usage.try_admit(key_for({"X-Real-IP": PROXY_SET_ADDRESS}), NOW)
    assert isinstance(lease, AdmissionLease)

    for forged in FORGERIES:
        visitor = key_for({"X-Real-IP": PROXY_SET_ADDRESS, **forged})
        assert usage.try_admit(visitor, NOW) == Refusal("already_running", None)


def test_locked_out_visitor_stays_locked_with_forged_headers():
    gate = AccessGate("open-sesame")
    for _ in range(5):
        gate.attempt(key_for({"X-Real-IP": PROXY_SET_ADDRESS}), "wrong", NOW)

    for forged in FORGERIES:
        visitor = key_for({"X-Real-IP": PROXY_SET_ADDRESS, **forged})
        assert gate.attempt(visitor, "open-sesame", NOW) == "locked"
