"""Tests the teacher marked as passing by hand, saved between runs of the window.

Saved as JSON in the grader's app-data folder (``manual_passes.json``), organized as::

    {"<assignment>|<submissions path>": {"<student>": {"<version>": ["test name", ...]}}}

A mark belongs to one version of a student's work, so a newer submission is graded
without it. Marks stay when the same version is graded again."""

from __future__ import annotations

import json
from pathlib import Path

from .grading import StudentResult
from .settings import app_data_dir


def manual_passes_path() -> Path:
    return app_data_dir() / "manual_passes.json"


def run_key(assignment: str, submissions: Path) -> str:
    """Which grading run marks belong to: the assignment and the submissions it graded."""
    try:
        where = str(submissions.resolve())
    except OSError:
        where = str(submissions)
    return f"{assignment}|{where}"


class ManualPasses:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or manual_passes_path()
        self.data: dict[str, dict[str, dict[str, list[str]]]] = {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            self.data = loaded

    def get(self, key: str, student: str, version: str | None) -> set[str]:
        try:
            return set(self.data[key][student][version or ""])
        except (KeyError, TypeError):
            return set()

    def set(self, key: str, student: str, version: str | None, test: str, on: bool) -> None:
        """Mark (``on``) or unmark one test, and save."""
        versions = self.data.setdefault(key, {}).setdefault(student, {})
        tests = set(versions.get(version or "", []))
        if on:
            tests.add(test)
        else:
            tests.discard(test)
        if tests:
            versions[version or ""] = sorted(tests)
        else:
            versions.pop(version or "", None)
            if not versions:
                del self.data[key][student]
                if not self.data[key]:
                    del self.data[key]
        self._save()

    def apply(self, key: str, r: StudentResult) -> None:
        """Set each test's ``manual`` flag in ``r`` from the saved marks."""
        marked = self.get(key, r.student, r.version)
        for t in r.tests:
            t.manual = t.name in marked

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        except OSError:
            pass  # the mark still applies for this session
