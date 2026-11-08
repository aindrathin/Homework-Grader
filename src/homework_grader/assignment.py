"""Load an assignment folder: its settings, test cases, and optional reference solution.

Layout::

    MyAssignment/
        assignment.toml          main_class = "DiceRoller"   (required)
                                 timeout_seconds = 10        (optional)
                                 required_classes = ["DiceRoller", "Die"]  (optional)
                                 compare_lines = 29   (optional: check only the first
                                                       29 lines of output)
        reference/               the teacher's solution (.java), used to generate expected output
        tests/
            <test name>/
                input.txt        typed into the program (optional)
                expected.txt     exact expected output
                seed.txt         random seed for this test (optional)
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 10.0


class AssignmentError(Exception):
    """The assignment folder is missing something or has invalid settings."""


@dataclass
class TestCase:
    name: str
    folder: Path
    input_path: Path | None
    expected_path: Path
    seed: int | None


@dataclass
class Assignment:
    name: str
    root: Path
    main_class: str
    timeout_seconds: float
    required_classes: list[str]
    tests: list[TestCase]
    compare_lines: int | None = None  # None: compare all output

    @property
    def reference_dir(self) -> Path:
        return self.root / "reference"


def load_assignment(root: Path) -> Assignment:
    root = Path(root)
    config_path = root / "assignment.toml"
    if not config_path.is_file():
        raise AssignmentError(f"No assignment.toml in {root}")
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8-sig"))
    except tomllib.TOMLDecodeError as e:
        raise AssignmentError(f"assignment.toml is not valid: {e}") from e

    main_class = config.get("main_class")
    if not isinstance(main_class, str) or not main_class:
        raise AssignmentError('assignment.toml must set main_class, e.g. main_class = "Main"')
    timeout = float(config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    required = list(config.get("required_classes", []))
    if main_class not in required:
        required.insert(0, main_class)
    compare_lines = config.get("compare_lines")
    if compare_lines is not None and (
        not isinstance(compare_lines, int) or isinstance(compare_lines, bool) or compare_lines < 1
    ):
        raise AssignmentError("compare_lines in assignment.toml must be a whole number above 0")

    return Assignment(
        name=root.name,
        root=root,
        main_class=main_class,
        timeout_seconds=timeout,
        required_classes=required,
        tests=_load_tests(root / "tests"),
        compare_lines=compare_lines,
    )


def _load_tests(tests_dir: Path) -> list[TestCase]:
    if not tests_dir.is_dir():
        raise AssignmentError(f"No tests folder at {tests_dir}")
    tests = []
    for folder in sorted((p for p in tests_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
        input_path = folder / "input.txt"
        seed_path = folder / "seed.txt"
        seed = None
        if seed_path.is_file():
            text = seed_path.read_text(encoding="utf-8-sig").strip()
            try:
                seed = int(text)
            except ValueError as e:
                msg = f"{seed_path} must contain a whole number, got {text!r}"
                raise AssignmentError(msg) from e
        tests.append(
            TestCase(
                name=folder.name,
                folder=folder,
                input_path=input_path if input_path.is_file() else None,
                expected_path=folder / "expected.txt",
                seed=seed,
            )
        )
    if not tests:
        raise AssignmentError(f"No test folders in {tests_dir}")
    return tests
