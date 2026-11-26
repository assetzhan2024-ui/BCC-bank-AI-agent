"""Backward-compatible entry point.

Supports the old ``python agent.py input.md report.md`` command. Prefer the
explicit CLI: ``python main.py --input input.md --output report.md``.
"""

import sys

from requirements_validator.cli import main


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if len(arguments) == 2 and not any(value.startswith("-") for value in arguments):
        arguments = ["--input", arguments[0], "--output", arguments[1]]
    raise SystemExit(main(arguments))
