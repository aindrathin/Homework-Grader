"""Tests for lining up expected and student output in the side-by-side view."""

from homework_grader.compare import (
    DIFF,
    EXTRA_BLANK,
    FILLER,
    MARKER,
    SAME,
    UNCHECKED,
    align,
    split_lines,
)


def kinds(rows):
    return [(r.expected.kind, r.actual.kind) for r in rows]


def test_split_lines():
    assert split_lines("") == []
    assert split_lines("a\nb\n") == ["a", "b"]
    assert split_lines("a\nb") == ["a", "b"]
    assert split_lines("a\n\n") == ["a", ""]


def test_identical_output_is_all_same():
    rows = align("a\nb\n", "a\nb\n")
    assert kinds(rows) == [(SAME, SAME), (SAME, SAME)]
    assert [(r.expected.number, r.actual.number) for r in rows] == [(1, 1), (2, 2)]


def test_changed_line_is_red_on_both_sides():
    rows = align("a\nb\nc\n", "a\nX\nc\n")
    assert kinds(rows) == [(SAME, SAME), (DIFF, DIFF), (SAME, SAME)]


def test_extra_blank_line_is_yellow():
    rows = align("a\nb\n", "a\n\nb\n")
    assert kinds(rows) == [(SAME, SAME), (FILLER, EXTRA_BLANK), (SAME, SAME)]
    assert rows[2].actual.number == 3  # student's own line numbers


def test_extra_blank_line_at_the_end_is_yellow():
    rows = align("a\n", "a\n\n")
    assert kinds(rows) == [(SAME, SAME), (FILLER, EXTRA_BLANK)]


def test_extra_line_with_text_is_red():
    rows = align("a\nb\n", "a\nhello\nb\n")
    assert kinds(rows) == [(SAME, SAME), (FILLER, DIFF), (SAME, SAME)]


def test_missing_line_is_red_on_expected_side():
    rows = align("a\nb\nc\n", "a\nc\n")
    assert kinds(rows) == [(SAME, SAME), (DIFF, FILLER), (SAME, SAME)]


def test_missing_blank_line_is_red():
    rows = align("a\n\nb\n", "a\nb\n")
    assert kinds(rows) == [(SAME, SAME), (DIFF, FILLER), (SAME, SAME)]


def test_lines_after_compare_lines_are_gray():
    rows = align("a\nb\npig\n", "a\nb\ncow\nmoo\n", compare_lines=2)
    assert kinds(rows) == [
        (SAME, SAME),
        (SAME, SAME),
        (MARKER, MARKER),
        (UNCHECKED, UNCHECKED),
        (FILLER, UNCHECKED),
    ]
    assert rows[4].actual.number == 4


def test_no_marker_when_nothing_after_compare_lines():
    assert MARKER not in {k for row in kinds(align("a\n", "a\n", compare_lines=5)) for k in row}
