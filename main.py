"""QuickLauncher executable entrypoint."""

from __future__ import annotations

import sys

from bootstrap.run_modes import ApplicationBootstrap


def main(argv: list[str] | None = None) -> int:
    """Parse the process mode and dispatch to its isolated bootstrap."""
    return ApplicationBootstrap().run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
