import json
from pathlib import Path

from resumefit_tools.taxonomy import MAX_SKILL_CHARS, MAX_SKILLS, normalize_skills

TAXONOMY_FILE = (
    Path(__file__).resolve().parents[1] / "resumefit_tools" / "taxonomy.json"
)


def canonical_names(skills: list[str]) -> list[str]:
    return [entry["canonical"] for entry in normalize_skills(skills)]


def test_js_normalizes_to_javascript() -> None:
    assert canonical_names(["JS", "js", "ReactJS", "k8s", "Postgres"]) == [
        "JavaScript",
        "JavaScript",
        "React",
        "Kubernetes",
        "PostgreSQL",
    ]


def test_matching_ignores_case_and_surrounding_whitespace() -> None:
    assert normalize_skills(["  PYTHON3 ", "Node.JS"]) == [
        {"input": "PYTHON3", "canonical": "Python", "category": "language"},
        {"input": "Node.JS", "canonical": "Node.js", "category": "framework"},
    ]


def test_unknown_skill_keeps_trimmed_text_with_category_other() -> None:
    assert normalize_skills(["  Underwater basket weaving  "]) == [
        {
            "input": "Underwater basket weaving",
            "canonical": "Underwater basket weaving",
            "category": "other",
        }
    ]


def test_order_and_length_are_preserved() -> None:
    skills = ["Docker", "unknown-thing", "aws", "Docker"]

    assert canonical_names(skills) == ["Docker", "unknown-thing", "AWS", "Docker"]


def test_more_than_one_hundred_skills_are_truncated_to_one_hundred() -> None:
    assert (
        len(normalize_skills([f"skill {n}" for n in range(MAX_SKILLS + 1)]))
        == MAX_SKILLS
    )


def test_each_skill_is_trimmed_to_eighty_characters() -> None:
    [entry] = normalize_skills(["x" * 200])

    assert entry["input"] == "x" * MAX_SKILL_CHARS
    assert entry["canonical"] == "x" * MAX_SKILL_CHARS


def test_taxonomy_has_about_150_skills_and_no_ambiguous_synonym() -> None:
    skills = json.loads(TAXONOMY_FILE.read_text(encoding="utf-8"))["skills"]
    owners: dict[str, set[str]] = {}
    for skill in skills:
        for key in {skill["name"].lower(), *skill["synonyms"]}:
            owners.setdefault(key, set()).add(skill["name"])

    assert 140 <= len(skills) <= 200
    assert len({skill["name"] for skill in skills}) == len(skills)
    assert all(
        synonym == synonym.lower() for skill in skills for synonym in skill["synonyms"]
    )
    assert {key: names for key, names in owners.items() if len(names) > 1} == {}
