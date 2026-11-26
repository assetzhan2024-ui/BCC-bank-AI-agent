from __future__ import annotations

import os
import subprocess
from pathlib import Path

from . import __version__


def agent_version(project_root: Path) -> str:
    """Commit/tag first (required by the task), then AGENT_VERSION, then VERSION file."""
    git = _git_version(project_root)
    if git:
        return git
    configured = os.getenv("AGENT_VERSION", "").strip()
    if configured:
        return f"{configured} (вне Git-репозитория)"
    version_file = project_root / "VERSION"
    value = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else __version__
    return f"{value} (вне Git-репозитория)"


def _git_version(project_root: Path) -> str:
    try:
        described = _git(project_root, "describe", "--tags", "--always", "--dirty")
        commit = _git(project_root, "rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return ""
    if not commit:
        return ""
    dirty = " (есть незакоммиченные изменения)" if described.endswith("-dirty") else ""
    tag = described.removesuffix("-dirty")
    if tag and not commit.startswith(tag):
        return f"{tag}, commit {commit[:12]}{dirty}"
    return f"commit {commit[:12]}{dirty}"


def _git(project_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=project_root,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=5,
    ).strip()
