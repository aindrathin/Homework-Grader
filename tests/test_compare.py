"""Tests for lining up expected and student output in the side-by-side view."""

from homework_grader.compare import (
    DIFF,
    EXTRA_BLANK,
    FILLER,
    INPUT,
    MARKER,
    SAME,
    UNCHECKED,
    align,
    console_lines,
    input_cells,
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


def test_console_lines_put_input_after_its_prompt():
    # The program printed "Weight? " then read "20", printed "Score? " then read "78".
    lines = console_lines("Title\nWeight? Score? Done\n", [(14, "20\n"), (21, "78\n")])
    assert [x.text for x in lines] == ["Title", "Weight? 20", "Score? 78", "Done"]
    assert [x.inputs for x in lines] == [(), ((8, 10),), ((7, 9),), ()]
    assert [x.start for x in lines] == [0, 6, 14, 21]


def test_console_lines_input_without_newline_gets_one():
    lines = console_lines("Name? Hi\n", [(6, "Sam")])
    assert [x.text for x in lines] == ["Name? Sam", "Hi"]


def test_console_lines_input_at_the_very_end():
    lines = console_lines("Name? ", [(6, "Sam\n")])
    assert [(x.text, x.inputs) for x in lines] == [("Name? Sam", ((6, 9),))]


def test_align_compares_console_lines_and_keeps_input_spans():
    rows = align("Age? Bye\n", "Age?Bye\n", expected_reads=[(5, "9\n")], actual_reads=[(4, "9\n")])
    assert kinds(rows) == [(DIFF, DIFF), (SAME, SAME)]
    assert rows[0].expected.text == "Age? 9" and rows[0].expected.inputs == ((5, 6),)
    assert rows[0].actual.text == "Age?9" and rows[0].actual.inputs == ((4, 5),)


def test_compare_lines_counts_output_lines_not_console_lines():
    # Output line 1 holds two prompts; with the input shown it becomes three lines,
    # and all of them are still checked.
    out = "A? B? End\nfree text\n"
    reads = [(3, "1\n"), (6, "2\n")]
    rows = align(out, out, compare_lines=1, expected_reads=reads, actual_reads=reads)
    assert [r.expected.text for r in rows] == [
        "A? 1",
        "B? 2",
        "End",
        "(not checked after output line 1)",
        "free text",
    ]
    assert kinds(rows) == [(SAME, SAME)] * 3 + [(MARKER, MARKER), (UNCHECKED, UNCHECKED)]


def test_input_cells_list_the_input_when_read_positions_are_unknown():
    cells = input_cells("3\nhello\n")
    assert [c.kind for c in cells] == [MARKER, INPUT, INPUT, MARKER]
    assert [c.text for c in cells] == ["Input (typed into the program):", "3", "hello", "Output:"]
    assert cells[1].inputs == ((0, 1),)
    assert input_cells(None) == []
