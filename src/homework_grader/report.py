"""Turn grading results into CSV files, console tables, and readable diffs."""

from __future__ import annotations

import csv
import difflib
from pathlib import Path

from .grading import StudentResult, TestResult, first_lines


def test_names(results: list[StudentResult]) -> list[str]:
    names: list[str] = []
    for r in results:
        for t in r.tests:
            if t.name not in names:
                names.append(t.name)
    return names


def write_csv(results: list[StudentResult], path: Path) -> None:
    names = test_names(results)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads UTF-8
        w = csv.writer(f)
        w.writerow(["Student", "Version", "Result", "Passed", "Total", *names, "Notes"])
        for r in results:
            by_name = {t.name: t.status for t in r.tests}
            w.writerow(
                [
                    r.student,
                    r.version or "",
                    r.summary,
                    r.passed,
                    len(r.tests),
                    *(by_name.get(n, "") for n in names),
                    " | ".join(r.notes),
                ]
            )


def format_table(results: list[StudentResult]) -> str:
    names = test_names(results)
    rows = [["Student", "Version", "Result", *names]]
    for r in results:
        by_name = {t.name: t.status for t in r.tests}
        rows.append([r.student, r.version or "", r.summary, *(by_name.get(n, "-") for n in names)])
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(cell.ljust(w) for cell, w in zip(row, widths, strict=True)) for row in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(line.rstrip() for line in lines)


def show_whitespace(line: str) -> str:
    """Show trailing spaces as · and tabs as → so whitespace differences can be seen."""
    body = line.rstrip(" \t")
    return body + line[len(body) :].replace(" ", "·").replace("\t", "→")


def hint(expected: str, actual: str) -> str | None:
    """A short explanation for common near-misses, or None."""

    def squash(s: str) -> str:
        return "\n".join(line.rstrip() for line in s.rstrip("\n").split("\n"))

    if squash(expected) == squash(actual):
        if expected.rstrip("\n") == actual.rstrip("\n"):
            return "Only the newlines at the very end differ."
        return "Only whitespace differs (spaces at line ends or blank lines at the end)."
    if expected.lower() == actual.lower():
        return "Only capitalization differs."
    return None


def diff_text(expected: str, actual: str) -> str:
    diff = difflib.unified_diff(
        [show_whitespace(x) for x in expected.split("\n")],
        [show_whitespace(x) for x in actual.split("\n")],
        fromfile="expected",
        tofile="student output",
        lineterm="",
        n=2,
    )
    return "\n".join(diff)


def describe_test(t: TestResult) -> str:
    seed = f", seed {t.seed}" if t.seed is not None else ""
    parts = [f"--- {t.name}{seed}: {t.status}"]
    if t.compare_lines is not None:
        parts.append(f"Only the first {t.compare_lines} lines of output are checked.")
    if t.status == "FAIL" and t.expected is not None:
        expected = first_lines(t.expected, t.compare_lines)
        actual = first_lines(t.actual, t.compare_lines)
        if h := hint(expected, actual):
            parts.append(f"Hint: {h}")
        parts.append(diff_text(expected, actual))
        if actual != t.actual:
            parts.append("Not checked (rest of the student output):\n" + t.actual[len(actual) :])
    elif not t.passed:
        if t.exit_code not in (None, 0):
            parts.append(f"Exit code {t.exit_code}")
        parts.append("Output:\n" + (t.actual or "(none)"))
    if t.stderr.strip():
        parts.append("Errors:\n" + t.stderr.strip()[:4000])
    return "\n".join(parts)


def describe_student(r: StudentResult) -> str:
    parts = [f"{r.student}  ({r.version or 'no version folder'})  {r.summary}"]
    if r.notes:
        parts.append("Notes:\n" + "\n".join(f"  - {n}" for n in r.notes))
    if r.compile_output.strip():
        parts.append("Compiler output:\n" + r.compile_output.strip())
    parts.extend(describe_test(t) for t in r.tests)
    return "\n\n".join(parts)
