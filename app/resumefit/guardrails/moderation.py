"""OpenAI moderation adapter that fails closed."""

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_MODERATION_MODEL = "omni-moderation-latest"


class ModerationUnavailable(Exception):
    """The moderation check could not be completed; the request must be refused."""


@dataclass(frozen=True)
class ModerationVerdict:
    flagged: bool


class ModeratorProtocol(Protocol):
    async def check(self, texts: list[str]) -> ModerationVerdict: ...


class _Moderations(Protocol):
    async def create(self, *, model: str, input: list[str]) -> Any: ...


class ModerationClient(Protocol):
    """The part of ``openai.AsyncOpenAI`` this adapter uses."""

    @property
    def moderations(self) -> _Moderations: ...


class OpenAIModerator:
    def __init__(
        self,
        client: ModerationClient,
        model: str = DEFAULT_MODERATION_MODEL,
        timeout_s: float = 10.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout_s = timeout_s

    async def check(self, texts: list[str]) -> ModerationVerdict:
        """Flag the request when any text is flagged; raise when no verdict is known."""
        try:
            async with asyncio.timeout(self._timeout_s):
                response = await self._client.moderations.create(
                    model=self._model, input=texts
                )
            flags = [bool(result.flagged) for result in response.results]
        except Exception as error:
            raise ModerationUnavailable("moderation check failed") from error
        if len(flags) != len(texts):
            raise ModerationUnavailable("moderation returned an incomplete verdict")
        return ModerationVerdict(flagged=any(flags))
