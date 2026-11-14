"""Tests for the text report printed by the command line."""

from homework_grader import grading
from homework_grader.grading import FAIL
from homework_grader.report import describe_test


def test_details_show_the_input_that_was_typed_in():
    t = grading.TestResult("seed-42", FAIL, 42, "a\n", "b\n", input="3\n5\n")
    assert "Input:\n3\n5\n" in describe_test(t)


def test_details_skip_input_when_there_is_none():
    t = grading.TestResult("only", FAIL, None, "a\n", "b\n")
    assert "Input:" not in describe_test(t)
