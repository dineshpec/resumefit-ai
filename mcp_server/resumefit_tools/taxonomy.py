"""Map free-text skill names to canonical names from the bundled taxonomy."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from typing_extensions import TypedDict  # pydantic needs it for schemas on Python 3.11

MAX_SKILLS = 100
MAX_SKILL_CHARS = 80
UNKNOWN_CATEGORY = "other"
TAXONOMY_FILE = Path(__file__).with_name("taxonomy.json")


class NormalizedSkill(TypedDict):
    input: str
    canonical: str
    category: str


def _key(skill: str) -> str:
    return " ".join(skill.lower().split())


@cache
def _index() -> dict[str, tuple[str, str]]:
    """Lower-case name or synonym -> (canonical name, category); loaded once."""
    data = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))
    index: dict[str, tuple[str, str]] = {}
    for skill in data["skills"]:
        for alias in (skill["name"], *skill["synonyms"]):
            index[_key(alias)] = (skill["name"], skill["category"])
    return index


def normalize_skills(skills: list[str]) -> list[NormalizedSkill]:
    """Return one entry per input (at most 100), in input order."""
    results: list[NormalizedSkill] = []
    for raw in skills[:MAX_SKILLS]:
        skill = raw.strip()[:MAX_SKILL_CHARS]
        canonical, category = _index().get(_key(skill), (skill, UNKNOWN_CATEGORY))
        results.append({"input": skill, "canonical": canonical, "category": category})
    return results
