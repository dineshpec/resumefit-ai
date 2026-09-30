"""OpenAI client factories: one chat client and one moderation client per analysis."""

from autogen_core.models import ChatCompletionClient
from autogen_ext.models.openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI

from resumefit.config import Settings
from resumefit.guardrails.moderation import ModerationVerdict, OpenAIModerator

TEMPERATURE = 0.2
REQUEST_TIMEOUT_S = 60.0
MAX_RETRIES = 2
MODERATION_TIMEOUT_S = 10.0


def create_model_client(settings: Settings) -> ChatCompletionClient:
    """Chat client with the per-call output cap; the caller must ``close()`` it."""
    return OpenAIChatCompletionClient(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=TEMPERATURE,
        timeout=REQUEST_TIMEOUT_S,
        max_retries=MAX_RETRIES,
        max_tokens=settings.max_output_tokens_per_call,
    )


class PerCallModerator:
    """Moderates with a fresh OpenAI client per check, closed before returning.

    Each analysis runs in its own event loop, so no HTTP client is shared between
    loops or Streamlit sessions.
    """

    def __init__(self, api_key: str, timeout_s: float = MODERATION_TIMEOUT_S) -> None:
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def check(self, texts: list[str]) -> ModerationVerdict:
        async with AsyncOpenAI(
            api_key=self._api_key, timeout=self._timeout_s, max_retries=MAX_RETRIES
        ) as client:
            return await OpenAIModerator(client, timeout_s=self._timeout_s).check(texts)


def create_moderator(settings: Settings) -> PerCallModerator:
    return PerCallModerator(settings.openai_api_key)
