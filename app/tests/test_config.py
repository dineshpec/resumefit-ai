import pytest

from resumefit.config import ConfigError, Settings

KEY = "sk-test-not-a-real-key-000000"


def settings_from(**overrides):
    return Settings.from_env({"OPENAI_API_KEY": KEY, **overrides})


def test_defaults_are_the_owner_accepted_values():
    settings = settings_from()

    assert settings.openai_api_key == KEY
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.app_access_code == ""
    assert settings.daily_analyses_per_visitor == 5
    assert settings.concurrent_analyses_per_visitor == 1
    assert settings.global_daily_analyses == 200
    assert settings.max_concurrent_analyses == 3
    assert settings.analysis_timeout_s == 180
    assert settings.max_agent_messages == 20
    assert settings.max_total_tokens == 150_000
    assert settings.max_output_tokens_per_call == 4_000
    assert settings.mcp_url == "http://mcp:8000/mcp"
    assert settings.trust_proxy_headers is False
    assert settings.client_ip_header == "X-Real-IP"
    assert settings.log_level == "INFO"


def test_every_variable_can_be_overridden():
    settings = settings_from(
        OPENAI_MODEL="gpt-4o",
        APP_ACCESS_CODE="open-sesame",
        VISITOR_HASH_SECRET="fixed-secret",
        DAILY_ANALYSES_PER_VISITOR="7",
        CONCURRENT_ANALYSES_PER_VISITOR="2",
        GLOBAL_DAILY_ANALYSES="50",
        MAX_CONCURRENT_ANALYSES="4",
        ANALYSIS_TIMEOUT_SECONDS="90",
        MAX_AGENT_MESSAGES="12",
        MAX_TOTAL_TOKENS="80000",
        MAX_OUTPUT_TOKENS_PER_CALL="2000",
        MCP_URL="http://localhost:8000/mcp",
        TRUST_PROXY_HEADERS="true",
        CLIENT_IP_HEADER="CF-Connecting-IP",
        LOG_LEVEL="debug",
    )

    assert settings.openai_model == "gpt-4o"
    assert settings.app_access_code == "open-sesame"
    assert settings.visitor_hash_secret == "fixed-secret"
    assert settings.daily_analyses_per_visitor == 7
    assert settings.concurrent_analyses_per_visitor == 2
    assert settings.global_daily_analyses == 50
    assert settings.max_concurrent_analyses == 4
    assert settings.analysis_timeout_s == 90
    assert settings.max_agent_messages == 12
    assert settings.max_total_tokens == 80_000
    assert settings.max_output_tokens_per_call == 2_000
    assert settings.mcp_url == "http://localhost:8000/mcp"
    assert settings.trust_proxy_headers is True
    assert settings.client_ip_header == "CF-Connecting-IP"
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    "environ", [{}, {"OPENAI_API_KEY": ""}, {"OPENAI_API_KEY": "  "}]
)
def test_missing_openai_key_is_a_start_up_error(environ):
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        Settings.from_env(environ)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DAILY_ANALYSES_PER_VISITOR", "five"),
        ("GLOBAL_DAILY_ANALYSES", "0"),
        ("MAX_CONCURRENT_ANALYSES", "-1"),
        ("MAX_TOTAL_TOKENS", "1.5"),
        ("TRUST_PROXY_HEADERS", "maybe"),
        ("LOG_LEVEL", "VERBOSE"),
        ("MCP_URL", "ftp://mcp:8000/mcp"),
        ("CLIENT_IP_HEADER", "X Real IP"),
    ],
)
def test_invalid_values_are_rejected_naming_only_the_variable(name, value):
    with pytest.raises(ConfigError) as caught:
        settings_from(**{name: value})

    assert name in str(caught.value)
    assert value not in str(caught.value)


@pytest.mark.parametrize(
    ("value", "expected"), [("1", True), ("YES", True), ("false", False), ("0", False)]
)
def test_boolean_flags_accept_common_spellings(value, expected):
    assert settings_from(TRUST_PROXY_HEADERS=value).trust_proxy_headers is expected


def test_empty_hash_secret_gets_a_random_secret_per_start():
    first = settings_from(VISITOR_HASH_SECRET="")
    second = settings_from()

    assert len(first.visitor_hash_secret) >= 32
    assert first.visitor_hash_secret != second.visitor_hash_secret


def test_repr_masks_every_secret():
    settings = settings_from(
        APP_ACCESS_CODE="open-sesame", VISITOR_HASH_SECRET="fixed-secret"
    )

    text = repr(settings) + str(settings)

    assert KEY not in text
    assert "open-sesame" not in text
    assert "fixed-secret" not in text
    assert "gpt-4o-mini" in text
