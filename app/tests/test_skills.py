import pytest

from resumefit.agents.skills import AGENT_NAMES, SKILLS_DIR, load_skill

REQUIRED_HEADINGS = ("## Role", "## Responsibilities", "## Rules", "## Output", "## Style")


def test_every_agent_has_a_skill_file() -> None:
    files = sorted(path.stem for path in SKILLS_DIR.glob("*.md"))

    assert files == sorted(AGENT_NAMES)


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_skill_file_has_the_five_required_headings_in_order(name: str) -> None:
    text = load_skill(name)
    lines = text.splitlines()

    positions = [lines.index(heading) for heading in REQUIRED_HEADINGS]

    assert positions == sorted(positions)


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_skill_file_treats_marked_content_as_data_and_keeps_placeholders(
    name: str,
) -> None:
    text = load_skill(name)

    assert "untrusted data" in text
    assert "never instructions" in text
    assert "[EMAIL]" in text and "[PHONE]" in text


def test_orchestrator_skill_fixes_the_delegation_order_and_next_line() -> None:
    text = load_skill("orchestrator")

    order = [
        text.index(f"`{name}`")
        for name in ("resume_parser", "jd_analyst", "matcher", "coach", "report_writer")
    ]
    assert order == sorted(order)
    assert "NEXT: <agent>" in text


def test_unknown_skill_name_is_refused() -> None:
    with pytest.raises(ValueError):
        load_skill("../config")
