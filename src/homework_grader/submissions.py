"""Find each student's latest submission in a Microsoft Teams export.

Expected layout (inside a .zip or an extracted folder)::

    submittedWork/
        <Student Name>/
            <Version 1>/  Main.java ...
            <Version 2>/  Main 1.java Helper.java ...   <- only the latest version is used

Some exports hold every assignment for each student, one folder per assignment::

    <Student Name>/
        Assignment_ Song/
            Version 1/  Song.java
        Assignment_ Space Needle/ ...

For these, pass the assignment's folder name (``submission_folder`` in
assignment.toml) and only that folder is read for each student.

Teams may append a number to a file name when a student resubmits (for example
``Main 1.java`` or ``Main (1).java``). Files are matched to classes by the
``public class`` declaration inside them, not by their file name.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .javasource import code_only, read_java

SUBMITTED_WORK = "submittedwork"
_IGNORED_DIRS = {"__macosx"}
_MODIFIERS = (
    r"(?:(?:public|protected|private|abstract|final|sealed|non-sealed|strictfp|static)\s+)*"
)
_PUBLIC_TYPE = re.compile(
    r"\bpublic\s+" + _MODIFIERS + r"(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)"
)
_TOP_LEVEL_TYPE = re.compile(
    r"^" + _MODIFIERS + r"(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)", re.M
)
_TEAMS_SUFFIX = re.compile(r"(?:\s*\((\d+)\)|\s+(\d+)|_(\d+))$")
_LAST_NUMBER = re.compile(r"(\d+)(?!.*\d)")


@dataclass
class Submission:
    student: str
    version: str | None
    files: dict[str, Path]  # class name -> source file
    notes: list[str] = field(default_factory=list)
    # Class name -> source text. Read while the files exist (a .zip is only extracted
    # for a moment), and graded instead of the file when present.
    sources: dict[str, str] = field(default_factory=dict)
    edited: list[str] = field(default_factory=list)  # classes the teacher changed in ``sources``


@contextmanager
def open_submissions(path: Path) -> Iterator[Path]:
    """Yield a folder to read submissions from; a .zip is extracted to a temp folder."""
    path = Path(path)
    if path.is_file() and path.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="hwgrader_zip_"))
        try:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(tmp)  # extractall drops absolute paths and ".." parts
            yield tmp
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    elif path.is_dir():
        yield path
    else:
        raise FileNotFoundError(f"Submissions must be a .zip file or a folder: {path}")


def locate_submitted_work(root: Path) -> Path:
    """Return the ``submittedWork`` folder under ``root``, or ``root`` itself if none."""
    if root.name.lower() == SUBMITTED_WORK:
        return root
    candidates = [p for p in root.rglob("*") if p.is_dir() and p.name.lower() == SUBMITTED_WORK]
    if candidates:
        return min(candidates, key=lambda p: len(p.parts))
    return root


def find_submissions(root: Path, submission_folder: str | None = None) -> list[Submission]:
    """Return one Submission per student folder, using each student's latest version.

    If ``submission_folder`` is given, each student's versions are read from the
    subfolder with that name (case is ignored); students without it get no files.
    """
    work = locate_submitted_work(Path(root))
    result = []
    for student_dir in sorted(_subdirs(work), key=lambda p: p.name.lower()):
        notes: list[str] = []
        if submission_folder:
            folder = _find_child(student_dir, submission_folder)
            if folder is None:
                notes.append(f"No '{submission_folder}' folder.")
                result.append(Submission(student_dir.name, None, {}, notes))
                continue
        else:
            folder = student_dir
        versions = _subdirs(folder)
        if versions:
            latest = max(versions, key=_version_key)
            version: str | None = latest.name
            if len(versions) > 1:
                notes.append(f"{len(versions)} versions submitted; graded '{latest.name}'.")
        else:
            latest, version = folder, None
        files = collect_java_files(latest, notes)
        if not files:
            notes.append("No .java files in the latest submission.")
        sources = {name: read_java(path) for name, path in files.items()}
        result.append(Submission(student_dir.name, version, files, notes, sources))
    return result


def collect_java_files(folder: Path, notes: list[str]) -> dict[str, Path]:
    """Map class name -> file for every .java file under ``folder``."""
    chosen: dict[str, tuple[int, Path]] = {}
    for path in sorted(folder.rglob("*.java")):
        name = class_name_for(path)
        copy_number = _teams_copy_number(path.stem, name)
        if name in chosen:
            prev_number, prev = chosen[name]
            keep = path if copy_number > prev_number else prev
            notes.append(f"Both '{prev.name}' and '{path.name}' define {name}; used '{keep.name}'.")
            if keep is prev:
                continue
        elif path.stem != name:
            notes.append(f"'{path.name}' used as {name}.java.")
        chosen[name] = (copy_number, path)
    return {name: path for name, (_, path) in chosen.items()}


def class_name_for(path: Path) -> str:
    """Name of the public (or first top-level) type in a file; falls back to the file name."""
    code = code_only(read_java(path))
    m = _PUBLIC_TYPE.search(code) or _TOP_LEVEL_TYPE.search(code)
    if m:
        return m.group(1)
    return _TEAMS_SUFFIX.sub("", path.stem) or path.stem


def _teams_copy_number(stem: str, class_name: str) -> int:
    if stem == class_name:
        return 0
    m = _TEAMS_SUFFIX.search(stem)
    return int(next(g for g in m.groups() if g)) if m else 0


def _subdirs(folder: Path) -> list[Path]:
    return [
        p
        for p in folder.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name.lower() not in _IGNORED_DIRS
    ]


def _find_child(folder: Path, name: str) -> Path | None:
    wanted = name.strip().lower()
    return next((p for p in _subdirs(folder) if p.name.strip().lower() == wanted), None)


def _version_key(folder: Path) -> tuple[int, str]:
    m = _LAST_NUMBER.search(folder.name)
    return (int(m.group(1)) if m else -1, folder.name.lower())
