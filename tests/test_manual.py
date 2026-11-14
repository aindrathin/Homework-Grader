"""Tests for tests the teacher marks as passing by hand."""

import json
from pathlib import Path

from homework_grader import grading
from homework_grader.grading import FAIL, GRADED, PASS, TIMEOUT, StudentResult
from homework_grader.gui import short_result
from homework_grader.manual import ManualPasses, run_key
from homework_grader.report import format_table, write_csv


def student(*statuses: str, version: str = "Version 1") -> StudentResult:
    tests = [grading.TestResult(f"t{i}", s, None, "", "") for i, s in enumerate(statuses)]
    return StudentResult("Sam", version, GRADED, tests)


def test_manual_pass_counts_and_is_labeled():
    r = student(PASS, FAIL)
    r.tests[1].manual = True
    assert r.tests[1].passed
    assert r.tests[1].shown_status == "PASS (manual)"
    assert r.passed == 2
    assert r.all_passed
    assert r.summary == "2/2 passed (manual)"
    assert short_result(r, 2) == "2/2  (manual)"


def test_single_test_manual_pass_in_student_list():
    r = student(TIMEOUT)
    r.tests[0].manual = True
    assert short_result(r, 1) == "passed (manual)"


def test_mark_on_a_real_pass_is_not_labeled():
    r = student(PASS)
    r.tests[0].manual = True
    assert r.tests[0].shown_status == PASS
    assert r.summary == "1/1 passed"


def test_csv_and_table_show_manual_passes(tmp_path):
    r = student(FAIL, FAIL)
    r.tests[0].manual = True
    path = tmp_path / "out.csv"
    write_csv([r], path)
    text = path.read_text(encoding="utf-8-sig")
    assert "PASS (manual)" in text
    assert "1/2 passed (manual)" in text
    assert "PASS (manual)" in format_table([r])


def test_marks_are_saved_and_applied(tmp_path):
    path = tmp_path / "manual.json"
    key = run_key("DiceRoller", tmp_path)
    ManualPasses(path).set(key, "Sam", "Version 1", "t1", True)

    r = student(PASS, FAIL)
    ManualPasses(path).apply(key, r)  # a fresh load, like reopening the window
    assert [t.manual for t in r.tests] == [False, True]
    assert r.all_passed


def test_marks_belong_to_one_version_and_run(tmp_path):
    path = tmp_path / "manual.json"
    key = run_key("DiceRoller", tmp_path)
    passes = ManualPasses(path)
    passes.set(key, "Sam", "Version 1", "t0", True)

    newer = student(FAIL, version="Version 2")
    passes.apply(key, newer)
    assert not newer.tests[0].manual

    other_run = student(FAIL)
    passes.apply(run_key("Song", tmp_path), other_run)
    assert not other_run.tests[0].manual


def test_unmarking_removes_the_entry(tmp_path):
    path = tmp_path / "manual.json"
    passes = ManualPasses(path)
    passes.set("k", "Sam", "Version 1", "t0", True)
    passes.set("k", "Sam", "Version 1", "t0", False)
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_bad_or_missing_file_means_no_marks(tmp_path):
    assert ManualPasses(tmp_path / "none.json").get("k", "Sam", "V1") == set()
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert ManualPasses(bad).get("k", "Sam", "V1") == set()


def test_run_key_uses_the_full_path():
    assert run_key("Song", Path("examples")) == f"Song|{Path('examples').resolve()}"
