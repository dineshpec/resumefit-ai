"""Local quality gate: formatting, lint, types, and both offline test suites.

Run from any Python 3.11 with ``python scripts/check.py``. Each package is checked
with its own virtual environment: ``.venv`` (application, also provides Ruff) and
``.venv-mcp`` (tools service). The OpenAI key is removed from the environment so
the suites stay offline and live tests are reported as skipped.
"""

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Step:
    label: str
    venv: str
    args: tuple[str, ...]


def venv_python(venv: str) -> Path:
    if os.name == "nt":
        return ROOT / venv / "Scripts" / "python.exe"
    return ROOT / venv / "bin" / "python"


def planned_steps() -> list[Step]:
    steps = [
        Step("ruff format", ".venv", ("-m", "ruff", "format", "--check", ".")),
        Step("ruff check", ".venv", ("-m", "ruff", "check", ".")),
        Step("mypy app", ".venv", ("-m", "mypy", "app/resumefit")),
        Step("pytest app", ".venv", ("-m", "pytest", "app/tests", "-q")),
    ]
    if (ROOT / "mcp_server" / "resumefit_tools").is_dir():
        steps.append(
            Step(
                "mypy tools", ".venv-mcp", ("-m", "mypy", "mcp_server/resumefit_tools")
            )
        )
    if (ROOT / "mcp_server" / "tests").is_dir():
        steps.append(
            Step(
                "pytest tools", ".venv-mcp", ("-m", "pytest", "mcp_server/tests", "-q")
            )
        )
    return steps


def run(step: Step, env: dict[str, str]) -> bool:
    python = venv_python(step.venv)
    print(f"\n==> {step.label}", flush=True)
    if not python.exists():
        print(
            f"missing interpreter {python.relative_to(ROOT)}; create {step.venv} first"
        )
        return False
    return subprocess.run([str(python), *step.args], cwd=ROOT, env=env).returncode == 0


def main() -> int:
    env = {key: value for key, value in os.environ.items() if key != "OPENAI_API_KEY"}
    results = []
    for step in planned_steps():
        started = time.perf_counter()
        passed = run(step, env)
        results.append((step.label, passed, time.perf_counter() - started))

    print("\nSummary")
    for label, passed, seconds in results:
        print(f"  {'PASS' if passed else 'FAIL'}  {label:<14} {seconds:6.1f} s")
    failed = [label for label, passed, _ in results if not passed]
    print("Gate failed: " + ", ".join(failed) if failed else "Gate passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
