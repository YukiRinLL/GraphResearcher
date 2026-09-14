"""Run one benchmark wrapper with an explicit repository import path."""

from __future__ import annotations

import runpy
import sys
import os
from pathlib import Path

from dotenv import dotenv_values


def main() -> None:
    arguments = sys.argv[1:]
    env_file = None
    if "--env-file" in arguments:
        index = arguments.index("--env-file")
        if index + 1 >= len(arguments):
            raise SystemExit("--env-file requires a path")
        env_file = Path(arguments[index + 1]).resolve()
        arguments = arguments[:index] + arguments[index + 2:]
    if not arguments:
        raise SystemExit("a target script is required")
    script = Path(arguments[0]).resolve()
    remaining = arguments[1:]
    if env_file is not None:
        for key, value in dotenv_values(env_file).items():
            if value is not None:
                os.environ[str(key)] = str(value)
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.path.insert(0, str(script.parent))
    sys.argv = [str(script), *remaining]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
