import asyncio
from types import SimpleNamespace

import pytest

from resumefit.guardrails.moderation import (
    ModerationUnavailable,
    ModerationVerdict,
    OpenAIModerator,
)


class FakeModerations:
    def __init__(self, flags=(), error=None, delay_s=0.0):
        self.flags = flags
        self.error = error
        self.delay_s = delay_s
        self.calls = []

    async def create(self, *, model, input):
        self.calls.append({"model": model, "input": input})
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            results=[SimpleNamespace(flagged=flag) for flag in self.flags]
        )


def moderator_with(moderations, timeout_s=10.0):
    return OpenAIModerator(
        SimpleNamespace(moderations=moderations), timeout_s=timeout_s
    )


async def test_flagged_job_description_gives_flagged_verdict():
    moderations = FakeModerations(flags=(False, True))

    verdict = await moderator_with(moderations).check(["resume", "job description"])

    assert verdict == ModerationVerdict(flagged=True)
    assert moderations.calls == [
        {"model": "omni-moderation-latest", "input": ["resume", "job description"]}
    ]


async def test_clean_texts_give_unflagged_verdict():
    moderations = FakeModerations(flags=(False, False))

    verdict = await moderator_with(moderations).check(["resume", "job description"])

    assert verdict == ModerationVerdict(flagged=False)


async def test_timeout_raises_moderation_unavailable():
    moderations = FakeModerations(flags=(False,), delay_s=1.0)

    with pytest.raises(ModerationUnavailable):
        await moderator_with(moderations, timeout_s=0.05).check(["resume"])


async def test_api_error_raises_moderation_unavailable():
    moderations = FakeModerations(error=ConnectionError("HTTP 503 from upstream"))

    with pytest.raises(ModerationUnavailable) as caught:
        await moderator_with(moderations).check(["resume"])

    assert "503" not in str(caught.value)


async def test_response_missing_a_result_raises_moderation_unavailable():
    moderations = FakeModerations(flags=(False,))

    with pytest.raises(ModerationUnavailable):
        await moderator_with(moderations).check(["resume", "job description"])
