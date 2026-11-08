"""Tests for assignment settings and output comparison helpers."""

import pytest

from homework_grader.assignment import AssignmentError, load_assignment
from homework_grader.grading import first_lines


def test_first_lines():
    assert first_lines("a\nb\nc\n", 2) == "a\nb\n"
    assert first_lines("a\nb\n", 2) == "a\nb\n"
    assert first_lines("a\nb", 2) == "a\nb"
    assert first_lines("a\n", 5) == "a\n"
    assert first_lines("a\nb\nc\n", None) == "a\nb\nc\n"


@pytest.mark.parametrize("value", ["0", "-1", '"29"', "2.5", "true"])
def test_bad_compare_lines_is_rejected(tmp_path, value):
    (tmp_path / "tests" / "t").mkdir(parents=True)
    (tmp_path / "assignment.toml").write_text(f'main_class = "Main"\ncompare_lines = {value}\n')
    with pytest.raises(AssignmentError):
        load_assignment(tmp_path)
