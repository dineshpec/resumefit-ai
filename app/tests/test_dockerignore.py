"""Build-context checks: secrets, virtual environments, tests, and caches never
reach an image, and every Dockerfile ``COPY`` source is inside its own context.

The matcher follows the ``.dockerignore`` rules Docker applies: patterns are
relative to the context root, ``*`` and ``?`` stay within one path segment, ``**``
spans segments, a pattern that matches a directory excludes everything below it,
and the last matching pattern wins (``!`` re-includes).
"""

import re
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTEXTS = ("app", "mcp_server")

MUST_BE_EXCLUDED = [
    ".env",
    ".env.local",
    ".env.production",
    ".venv/pyvenv.cfg",
    ".venv-mcp/Lib/site.py",
    "tests/test_something.py",
    "tests/fixtures/sample.txt",
    "__pycache__/module.cpython-311.pyc",
    "package/__pycache__/module.cpython-311.pyc",
    "package/module.pyc",
    ".pytest_cache/v/cache/nodeids",
    ".mypy_cache/3.11/cache.json",
    ".ruff_cache/content",
    "requirements-dev.txt",
]


def _segment_regex(pattern: str) -> str:
    regex = ""
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            regex += "(?:.*/)?"
            index += 3
        elif pattern.startswith("**", index):
            regex += ".*"
            index += 2
        elif pattern[index] == "*":
            regex += "[^/]*"
            index += 1
        elif pattern[index] == "?":
            regex += "[^/]"
            index += 1
        elif pattern[index] == "[" and "]" in pattern[index + 1 :]:
            end = pattern.index("]", index + 1)
            members = pattern[index + 1 : end]
            if members.startswith("^"):
                members = "^" + re.escape(members[1:])
            else:
                members = re.escape(members)
            regex += f"[{members}]"
            index = end + 1
        else:
            regex += re.escape(pattern[index])
            index += 1
    return regex


def ignore_rules(context: str) -> list[tuple[bool, re.Pattern[str]]]:
    rules = []
    text = (ROOT / context / ".dockerignore").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        include = line.startswith("!")
        pattern = line[1:] if include else line
        pattern = str(PurePosixPath(pattern.strip("/")))
        rules.append((include, re.compile(_segment_regex(pattern))))
    return rules


def is_ignored(context: str, path: str) -> bool:
    parts = PurePosixPath(path).parts
    candidates = ["/".join(parts[: length + 1]) for length in range(len(parts))]
    ignored = False
    for include, regex in ignore_rules(context):
        if any(regex.fullmatch(candidate) for candidate in candidates):
            ignored = not include
    return ignored


def copy_sources(context: str) -> list[str]:
    text = (ROOT / context / "Dockerfile").read_text(encoding="utf-8")
    text = re.sub(r"\\\n", " ", text)
    sources = []
    for line in text.splitlines():
        words = line.split()
        if not words or words[0].upper() not in {"COPY", "ADD"}:
            continue
        options = [word for word in words[1:] if word.startswith("--")]
        if any(option.startswith("--from") for option in options):
            continue
        arguments = [word for word in words[1:] if not word.startswith("--")]
        sources.extend(arguments[:-1])
    return sources


def test_matcher_follows_dockerignore_semantics() -> None:
    assert re.fullmatch(_segment_regex("**/__pycache__"), "a/b/__pycache__")
    assert re.fullmatch(_segment_regex("**/__pycache__"), "__pycache__")
    assert re.fullmatch(_segment_regex("*.txt"), "notes.txt")
    assert not re.fullmatch(_segment_regex("*.txt"), "docs/notes.txt")
    assert re.fullmatch(_segment_regex("**/*.py[cod]"), "a/module.pyc")
    assert not re.fullmatch(_segment_regex("**/*.py[cod]"), "a/module.py")


@pytest.mark.parametrize("context", CONTEXTS)
@pytest.mark.parametrize("path", MUST_BE_EXCLUDED)
def test_each_build_context_dockerignore_excludes_env_venv_and_tests(
    context: str, path: str
) -> None:
    assert is_ignored(context, path), f"{context}: {path} would enter the image"


@pytest.mark.parametrize("context", CONTEXTS)
def test_each_build_context_keeps_the_runtime_requirements(context: str) -> None:
    assert not is_ignored(context, "requirements.txt")


@pytest.mark.parametrize("context", CONTEXTS)
def test_each_dockerfile_copies_only_existing_unignored_paths_in_its_context(
    context: str,
) -> None:
    sources = copy_sources(context)
    assert sources, "the Dockerfile must copy its sources explicitly"
    for source in sources:
        assert not source.startswith(("/", "..")), source
        assert "*" not in source and source not in {".", "./"}, source
        assert ".env" not in PurePosixPath(source).name, source
        assert (ROOT / context / source).exists(), source
        assert not is_ignored(context, source), source


def test_app_image_copies_every_runtime_file_the_page_needs() -> None:
    assert set(copy_sources("app")) == {
        "requirements.txt",
        "resumefit",
        "skills",
        ".streamlit",
        "streamlit_app.py",
    }


def test_tools_image_copies_only_the_tools_package() -> None:
    assert set(copy_sources("mcp_server")) == {"requirements.txt", "resumefit_tools"}


@pytest.mark.parametrize("context", CONTEXTS)
def test_copied_package_contains_no_ignored_runtime_file(context: str) -> None:
    package = "resumefit" if context == "app" else "resumefit_tools"
    for path in (ROOT / context / package).rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            relative = path.relative_to(ROOT / context).as_posix()
            assert not is_ignored(context, relative), relative
