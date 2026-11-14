"""Remembers the desktop window's choices (last assignment and submissions) between runs.

Stored as JSON in the user's app-data folder (``%APPDATA%\\HomeworkGrader\\settings.json``
on Windows), not in the repo, so it isn't committed or shared."""

from __future__ import annotations

import json
import os
from pathlib import Path


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    folder = Path(base) / "HomeworkGrader" if base else Path.home() / ".homework_grader"
    return folder / "settings.json"


def load_settings(path: Path | None = None) -> dict[str, str]:
    """The saved settings, or {} if there are none or the file can't be read."""
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def save_settings(settings: dict[str, str], path: Path | None = None) -> None:
    """Write the settings; failures are ignored (remembering choices is only a convenience)."""
    path = path or settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass
