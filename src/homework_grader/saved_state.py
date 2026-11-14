"""What the desktop window keeps between runs besides manual passes (see ``manual.py``).

Three files in the grader's app-data folder:

- ``edits.json``: the teacher's code edits, by grading run (assignment + submissions),
  student, and version::

      {"<run key>": {"<student>": {"<version>": {"<class>": "source text"}}}}

  Edits belong to one version, like manual passes: a newer submission is graded without
  them, and the old version's edits are dropped (``SavedEdits.keep_versions``).
- ``notes.json``: the teacher's notes on each student, by assignment name::

      {"<assignment>": {"<student>": "note text"}}

  Notes don't depend on the version or on which export was graded.
- ``session.json``: the last grading run (submissions and results), so reopening the
  window shows it without grading again. It is only restored when the assignment folder
  and the submissions are unchanged (``fingerprint``).

Saving never raises: if a file can't be written, the window keeps working for this session.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from .grading import StudentResult, TestResult
from .settings import app_data_dir
from .submissions import Submission

SESSION_FORMAT = 1


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_json(path: Path, data: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        tmp.replace(path)  # never leave a half-written file behind
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ edits
class SavedEdits:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "edits.json"
        loaded = _load_json(self.path)
        self.data: dict[str, dict[str, dict[str, dict[str, str]]]] = (
            loaded if isinstance(loaded, dict) else {}
        )

    def get(self, key: str, student: str, version: str | None) -> dict[str, str]:
        """The saved edits (class -> source) for one version of a student's work."""
        try:
            found = self.data[key][student][version or ""]
        except (KeyError, TypeError):
            return {}
        if not isinstance(found, dict):
            return {}
        return {c: t for c, t in found.items() if isinstance(c, str) and isinstance(t, str)}

    def set(self, key: str, student: str, version: str | None, edits: dict[str, str]) -> None:
        """Replace one version's edits (``{}`` removes them), and save if anything changed."""
        if self.get(key, student, version) == edits:
            return
        versions = self.data.setdefault(key, {}).setdefault(student, {})
        if edits:
            versions[version or ""] = dict(edits)
        else:
            versions.pop(version or "", None)
            self._prune(key, student)
        self._save()

    def keep_versions(self, key: str, latest: dict[str, str | None]) -> None:
        """Drop edits to versions other than each student's latest (``latest``: student ->
        version). Students not in ``latest`` are left alone."""
        changed = False
        for student, version in latest.items():
            versions = self.data.get(key, {}).get(student)
            if not versions:
                continue
            for v in [v for v in versions if v != (version or "")]:
                del versions[v]
                changed = True
            self._prune(key, student)
        if changed:
            self._save()

    def _prune(self, key: str, student: str) -> None:
        if not self.data.get(key, {}).get(student):
            self.data.get(key, {}).pop(student, None)
        if key in self.data and not self.data[key]:
            del self.data[key]

    def _save(self) -> None:
        _save_json(self.path, self.data)


# ------------------------------------------------------------------ notes
class StudentNotes:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "notes.json"
        loaded = _load_json(self.path)
        self.data: dict[str, dict[str, str]] = loaded if isinstance(loaded, dict) else {}

    def get(self, assignment: str, student: str) -> str:
        found = self.data.get(assignment, {})
        text = found.get(student, "") if isinstance(found, dict) else ""
        return text if isinstance(text, str) else ""

    def set(self, assignment: str, student: str, text: str) -> None:
        """Save one student's note; blank notes are removed."""
        if not text.strip():
            text = ""
        if text == self.get(assignment, student):
            return
        notes = self.data.setdefault(assignment, {})
        if text:
            notes[student] = text
        else:
            notes.pop(student, None)
            if not notes:
                del self.data[assignment]
        _save_json(self.path, self.data)


# ---------------------------------------------------------------- session
def fingerprint(assignment_root: Path, submissions: Path) -> str:
    """Changes when any file in the assignment folder changes, or the submissions do.

    Assignment files are hashed by content (they're small). Submissions are checked by
    each file's size and modification time, which is enough to notice a new export."""
    h = hashlib.sha256()
    for p in sorted(assignment_root.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(assignment_root).as_posix().encode())
            h.update(p.read_bytes())
    files = [submissions] if submissions.is_file() else sorted(submissions.rglob("*"))
    for p in files:
        if p.is_file():
            st = p.stat()
            h.update(f"{p.relative_to(submissions.parent).as_posix()}|{st.st_size}|".encode())
            h.update(str(st.st_mtime_ns).encode())
    return h.hexdigest()


def _submission_to_json(s: Submission) -> dict:
    return {
        "student": s.student,
        "version": s.version,
        "files": {c: str(p) for c, p in s.files.items()},
        "notes": s.notes,
        "sources": s.sources,
    }


def _submission_from_json(d: dict) -> Submission:
    return Submission(
        student=d["student"],
        version=d["version"],
        files={c: Path(p) for c, p in d["files"].items()},
        notes=list(d["notes"]),
        sources=dict(d["sources"]),
    )


def _reads(value) -> list[tuple[int, str]] | None:
    return None if value is None else [(int(pos), str(text)) for pos, text in value]


def _result_from_json(d: dict) -> StudentResult:
    test_fields = {f.name for f in fields(TestResult)}
    tests = []
    for t in d["tests"]:
        t = {k: v for k, v in t.items() if k in test_fields}
        t["input_reads"] = _reads(t.get("input_reads"))
        t["manual"] = False  # manual passes come from manual_passes.json
        tests.append(TestResult(**t))
    result_fields = {f.name for f in fields(StudentResult)}
    r = {k: v for k, v in d.items() if k in result_fields}
    r["tests"] = tests
    r["expected_reads"] = {name: _reads(v) for name, v in d.get("expected_reads", {}).items()}
    return StudentResult(**r)


class SavedSession:
    """The last grading run: which assignment and submissions, and every student's result."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "session.json"

    def save(
        self,
        assignment: str,
        submissions: Path,
        stamp: str,
        subs: list[Submission],
        results: list[StudentResult],
    ) -> None:
        _save_json(
            self.path,
            {
                "format": SESSION_FORMAT,
                "assignment": assignment,
                "submissions": str(submissions),
                "fingerprint": stamp,
                "submissions_list": [_submission_to_json(s) for s in subs],
                "results": [asdict(r) for r in results],
            },
        )

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass

    def load(self) -> dict | None:
        """The saved run as {"assignment", "submissions" (Path), "fingerprint",
        "submissions_list", "results"}, or None if there is none or it can't be read."""
        data = _load_json(self.path)
        if not isinstance(data, dict) or data.get("format") != SESSION_FORMAT:
            return None
        try:
            return {
                "assignment": str(data["assignment"]),
                "submissions": Path(data["submissions"]),
                "fingerprint": str(data["fingerprint"]),
                "submissions_list": [_submission_from_json(s) for s in data["submissions_list"]],
                "results": [_result_from_json(r) for r in data["results"]],
            }
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
