"""Importable extraction targets for the worker tests (the child process imports them)."""

import os
import time
from typing import Any

from resumefit_tools.extraction import extract_text

SLOW_FILENAME = "slow.pdf"


def never_returns(filename: str, data: bytes) -> dict[str, Any]:
    while True:
        time.sleep(0.05)


def hangs_on_slow_file(filename: str, data: bytes) -> dict[str, Any]:
    if filename == SLOW_FILENAME:
        return never_returns(filename, data)
    return extract_text(filename, data)


def raises_error(filename: str, data: bytes) -> dict[str, Any]:
    raise RuntimeError("parser exploded")


def exits_abruptly(filename: str, data: bytes) -> dict[str, Any]:
    os._exit(3)
