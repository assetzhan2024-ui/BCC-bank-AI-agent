from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import __version__


def agent_version(project_root: Path) -> str:
    configured = os.getenv("AGENT_VERSION", "").strip()
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=project_root,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        version_file = project_root / "VERSION"
        return version_file.read_text(encoding="utf-8").strip() if version_file.exists() else __version__
