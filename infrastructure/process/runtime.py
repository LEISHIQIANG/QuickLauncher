"""Process execution adapters.

Thin compatibility shim that re-exports the four ``subprocess`` /
``os.startfile`` primitives the rest of the codebase uses.  Keeps
call sites uniform (``from infrastructure.process import runtime as
process_runtime``) and gives the capture path one place to grow if
Windows-specific behaviour needs to be centralised.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

subprocess_adapter = subprocess


def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(*args, **kwargs)


def call(*args: Any, **kwargs: Any) -> int:
    return subprocess.call(*args, **kwargs)


def popen(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
    return subprocess.Popen(*args, **kwargs)


def startfile(path: str | os.PathLike[str], *args: Any, **kwargs: Any) -> None:
    os.startfile(path, *args, **kwargs)


__all__ = [
    "subprocess_adapter",
    "run",
    "call",
    "popen",
    "startfile",
]
