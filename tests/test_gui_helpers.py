"""Tests for the student-list labels and colors in the desktop window."""

from homework_grader import grading
from homework_grader.grading import COMPILE_ERROR, FAIL, GRADED, PASS, StudentResult
from homework_grader.gui import result_level, short_result


def student(*statuses: str, status: str = GRADED) -> StudentResult:
    tests = [grading.TestResult(f"t{i}", s, None, "", "") for i, s in enumerate(statuses)]
    return StudentResult("Sam", "Version 1", status, tests)


def test_one_test_shows_its_result():
    assert short_result(student(PASS), 1) == "passed"
    assert short_result(student(FAIL), 1) == "FAIL"
    assert short_result(student(status=COMPILE_ERROR), 1) == "COMPILE ERROR"


def test_several_tests_show_a_fraction():
    assert short_result(student(PASS, PASS, PASS), 3) == "3/3"
    assert short_result(student(PASS, FAIL, FAIL), 3) == "1/3"
    assert short_result(student(status=COMPILE_ERROR), 3) == "0/3  COMPILE ERROR"


def test_row_color_level():
    assert result_level(student(PASS, PASS)) == "all"
    assert result_level(student(PASS, FAIL)) == "some"
    assert result_level(student(FAIL, FAIL)) == "none"
    assert result_level(student(status=COMPILE_ERROR)) == "none"
