"""Compile each submission in a temporary folder, run every test, and compare output exactly.

Comparison is exact, character for character, after one normalization: Windows
line endings (``\\r\\n``) are treated as ``\\n`` so expected files written on any
computer compare the same way.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .assignment import Assignment, TestCase
from .javasource import read_java
from .rewrite import HELPER_CLASS, HELPER_SOURCE, rewrite_source
from .submissions import Submission, collect_java_files

COMPILE_TIMEOUT_SECONDS = 120
MAX_OUTPUT_BYTES = 1_000_000
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Test statuses
PASS = "PASS"
FAIL = "FAIL"
TIMEOUT = "TIMEOUT"
RUNTIME_ERROR = "RUNTIME ERROR"
NO_EXPECTED = "NO EXPECTED FILE"

# Submission statuses
GRADED = "GRADED"
COMPILE_ERROR = "COMPILE ERROR"
MISSING_CLASSES = "MISSING FILES"
NO_FILES = "NO SUBMISSION"
GRADER_ERROR = "GRADER ERROR"


class JavaNotFoundError(Exception):
    pass


@dataclass
class TestResult:
    name: str
    status: str
    seed: int | None
    expected: str | None
    actual: str
    stderr: str = ""
    exit_code: int | None = None

    @property
    def passed(self) -> bool:
        return self.status == PASS


@dataclass
class StudentResult:
    student: str
    version: str | None
    status: str
    tests: list[TestResult] = field(default_factory=list)
    compile_output: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(t.passed for t in self.tests)

    @property
    def summary(self) -> str:
        if self.status != GRADED:
            return self.status
        return f"{self.passed}/{len(self.tests)} passed"

    @property
    def all_passed(self) -> bool:
        return self.status == GRADED and self.passed == len(self.tests)


def find_java_tool(name: str) -> str:
    """Locate ``java`` or ``javac``: PATH first, then JAVA_HOME, then common install folders."""
    found = shutil.which(name)
    if found:
        return found
    exe = name + (".exe" if sys.platform == "win32" else "")
    homes = [os.environ.get("JAVA_HOME", "")]
    for pattern in (
        r"C:\Program Files\Eclipse Adoptium\*",
        r"C:\Program Files\Java\*",
        r"C:\Program Files\Microsoft\jdk*",
        r"C:\Program Files\Zulu\*",
    ):
        homes.extend(sorted(glob.glob(pattern), reverse=True))
    for home in homes:
        candidate = Path(home) / "bin" / exe
        if home and candidate.is_file():
            return str(candidate)
    raise JavaNotFoundError(f"Could not find '{name}'. Install a JDK and add it to PATH.")


def normalize(text: str) -> str:
    return text.replace("\r\n", "\n")


def read_expected(path: Path) -> str | None:
    if not path.is_file():
        return None
    return normalize(path.read_bytes().decode("utf-8-sig", errors="replace"))


# ---------------------------------------------------------------------------
# Preparing, compiling, running
# ---------------------------------------------------------------------------


def prepare_sources(files: dict[str, Path], src_dir: Path) -> list[str]:
    """Write rewritten copies of ``files`` as ``<Class>.java`` in ``src_dir``; return notes."""
    src_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    own_random = "Random" in files
    for class_name, path in files.items():
        result = rewrite_source(read_java(path), seed_random_class=not own_random)
        (src_dir / f"{class_name}.java").write_text(result.source, encoding="utf-8")
        notes.extend(f"{class_name}.java: {n}" for n in result.notes)
    (src_dir / f"{HELPER_CLASS}.java").write_text(HELPER_SOURCE, encoding="utf-8")
    return notes


def compile_sources(src_dir: Path, classes_dir: Path) -> tuple[bool, str]:
    classes_dir.mkdir(parents=True, exist_ok=True)
    sources = sorted(str(p) for p in src_dir.glob("*.java"))
    cmd = [
        find_java_tool("javac"),
        "-encoding",
        "UTF-8",
        "-nowarn",
        "-d",
        str(classes_dir),
        *sources,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=COMPILE_TIMEOUT_SECONDS,
            cwd=src_dir,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, "javac took too long and was stopped."
    output = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    # Show paths relative to the temp folder so messages read "Main.java:5: error: ..."
    output = output.replace(str(src_dir) + os.sep, "")
    return proc.returncode == 0, normalize(output)


def run_test(
    classes_dir: Path, run_dir: Path, main_class: str, test: TestCase, timeout: float
) -> TestResult:
    """Run one test and compare its output with expected.txt."""
    run_dir.mkdir(parents=True, exist_ok=True)
    out_path = run_dir / f"{test.name}.out"
    err_path = run_dir / f"{test.name}.err"
    cmd = [
        find_java_tool("java"),
        "-Xmx256m",
        "-Dfile.encoding=UTF-8",
        "-Dstdout.encoding=UTF-8",
        "-Dstderr.encoding=UTF-8",
    ]
    if test.seed is not None:
        cmd.append(f"-Dgrader.seed={test.seed}")
    cmd += ["-cp", str(classes_dir), main_class]

    exit_code: int | None = None
    timed_out = False
    stdin = open(test.input_path, "rb") if test.input_path else subprocess.DEVNULL  # noqa: SIM115
    try:
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            try:
                proc = subprocess.run(
                    cmd,
                    stdin=stdin,
                    stdout=out,
                    stderr=err,
                    cwd=run_dir,
                    timeout=timeout,
                    creationflags=_NO_WINDOW,
                )
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        if stdin is not subprocess.DEVNULL:
            stdin.close()

    actual = _read_capped(out_path)
    stderr = _read_capped(err_path)
    expected = read_expected(test.expected_path)

    if timed_out:
        status = TIMEOUT
    elif exit_code != 0:
        status = RUNTIME_ERROR
    elif expected is None:
        status = NO_EXPECTED
    else:
        status = PASS if actual == expected else FAIL
    return TestResult(test.name, status, test.seed, expected, actual, stderr, exit_code)


def _read_capped(path: Path) -> str:
    with open(path, "rb") as f:
        data = f.read(MAX_OUTPUT_BYTES + 1)
    text = normalize(data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"))
    if len(data) > MAX_OUTPUT_BYTES:
        text += "\n[... output cut off after 1 MB ...]"
    return text


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def grade_submission(assignment: Assignment, submission: Submission) -> StudentResult:
    result = StudentResult(
        submission.student, submission.version, GRADED, notes=list(submission.notes)
    )
    if not submission.files:
        result.status = NO_FILES
        return result
    missing = [c for c in assignment.required_classes if c not in submission.files]
    if missing:
        result.status = MISSING_CLASSES
        result.notes.append("Missing: " + ", ".join(f"{c}.java" for c in missing))
        return result

    workdir = Path(tempfile.mkdtemp(prefix="hwgrader_"))
    try:
        result.notes += prepare_sources(submission.files, workdir / "src")
        ok, output = compile_sources(workdir / "src", workdir / "classes")
        result.compile_output = output
        if not ok:
            result.status = COMPILE_ERROR
            return result
        for test in assignment.tests:
            result.tests.append(
                run_test(
                    workdir / "classes",
                    workdir / "run",
                    assignment.main_class,
                    test,
                    assignment.timeout_seconds,
                )
            )
    except Exception as e:  # keep grading the other students
        result.status = GRADER_ERROR
        result.notes.append(f"Grader error: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return result


def grade_all(
    assignment: Assignment,
    submissions: Iterable[Submission],
    on_result: Callable[[StudentResult], None] | None = None,
    workers: int = 4,
) -> list[StudentResult]:
    """Grade every submission (several at once); results keep the submissions' order."""
    find_java_tool("javac")  # fail fast with a clear message
    find_java_tool("java")
    submissions = list(submissions)

    def work(sub: Submission) -> StudentResult:
        r = grade_submission(assignment, sub)
        if on_result:
            on_result(r)
        return r

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(work, submissions))


def generate_expected(assignment: Assignment, overwrite: bool = False) -> list[str]:
    """Run the reference solution on every test and write expected.txt files.

    Returns one message per test. Existing expected.txt files are kept unless
    ``overwrite`` is True.
    """
    ref = assignment.reference_dir
    if not ref.is_dir():
        return [f"No reference folder at {ref}. Put the solution's .java files there."]
    notes: list[str] = []
    files = collect_java_files(ref, notes)
    missing = [c for c in assignment.required_classes if c not in files]
    if missing:
        return [f"Reference solution is missing: {', '.join(missing)}"]

    messages: list[str] = []
    workdir = Path(tempfile.mkdtemp(prefix="hwgrader_ref_"))
    try:
        prepare_sources(files, workdir / "src")
        ok, output = compile_sources(workdir / "src", workdir / "classes")
        if not ok:
            return ["Reference solution does not compile:\n" + output]
        for test in assignment.tests:
            if test.expected_path.exists() and not overwrite:
                messages.append(f"{test.name}: kept existing expected.txt")
                continue
            r = run_test(
                workdir / "classes",
                workdir / "run",
                assignment.main_class,
                test,
                assignment.timeout_seconds,
            )
            if r.status in (TIMEOUT, RUNTIME_ERROR):
                messages.append(f"{test.name}: reference solution failed ({r.status})\n{r.stderr}")
                continue
            test.expected_path.write_bytes(r.actual.encode("utf-8"))
            seed = f" (seed {test.seed})" if test.seed is not None else ""
            messages.append(f"{test.name}: wrote expected.txt{seed}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return messages
