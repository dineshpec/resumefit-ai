"""Test-only start-up hook that records what spawned worker children import.

`test_server.py` puts this folder first on `PYTHONPATH` and names an output folder
in `RESUMEFIT_SPAWN_PROBE_DIR` when it starts the tools service. Every
`multiprocessing` spawn child of that service then writes `child-<pid>.log`: a
`started` line, then each watched module as it is imported. Writes are
synchronous, so the log is complete before the child sends its result. Other
processes (the server itself, pytest) are left untouched.
"""

import os
import sys
from typing import Any

WATCHED_MODULES = frozenset(
    {
        "fastmcp",
        "uvicorn",
        "starlette",
        "resumefit_tools.server",
        "resumefit_tools.worker",
        "resumefit_tools.extraction",
    }
)

_probe_dir = os.environ.get("RESUMEFIT_SPAWN_PROBE_DIR")

if _probe_dir and "--multiprocessing-fork" in sys.argv:
    _log_path = os.path.join(_probe_dir, f"child-{os.getpid()}.log")

    def _record(line: str) -> None:
        with open(_log_path, "a", encoding="utf-8") as log:
            log.write(line + "\n")

    def _audit(event: str, arguments: tuple[Any, ...]) -> None:
        if event == "import" and arguments and arguments[0] in WATCHED_MODULES:
            _record(str(arguments[0]))

    _record("started")
    sys.addaudithook(_audit)
