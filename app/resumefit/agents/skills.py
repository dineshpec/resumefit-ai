"""Agent roster and skill-file loading."""

from functools import cache
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

ORCHESTRATOR = "orchestrator"
AGENT_ORDER: tuple[str, ...] = (
    "resume_parser",
    "jd_analyst",
    "matcher",
    "coach",
    "report_writer",
)
AGENT_NAMES: tuple[str, ...] = (ORCHESTRATOR, *AGENT_ORDER)
DISPLAY_NAMES: dict[str, str] = {
    "orchestrator": "Orchestrator",
    "resume_parser": "Resume Parser",
    "jd_analyst": "JD Analyst",
    "matcher": "Matcher",
    "coach": "Coach",
    "report_writer": "Report Writer",
}


@cache
def load_skill(name: str) -> str:
    """Return the full text of an agent's skill file (``app/skills/<name>.md``)."""
    if name not in AGENT_NAMES:
        raise ValueError(f"unknown agent {name!r}")
    return (SKILLS_DIR / f"{name}.md").read_text(encoding="utf-8")
