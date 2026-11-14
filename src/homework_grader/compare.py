"""Line up expected and student output, row by row, for the side-by-side view.

Each side is shown the way it would look in a console: the test's input appears
right where the program read it (usually just after a prompt), followed by the
Enter that ended it. Those input spans are listed in ``Cell.inputs`` so they can
be styled. Grading itself never looks at this; it compares the raw output.

Each row has an expected cell (left) and a student cell (right). A cell's ``kind`` says
how to color it:

- ``same``: the line matches.
- ``diff``: the line is different, missing, or extra (red).
- ``extra_blank``: the student printed a blank line that isn't in the expected output (yellow).
- ``filler``: nothing on this side; keeps the two sides lined up.
- ``unchecked`` / ``marker``: past ``compare_lines``, so not graded (gray).
- ``input``: a line of input.txt listed above the output, used only when it isn't
  known where that side read its input.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from itertools import zip_longest

SAME = "same"
DIFF = "diff"
EXTRA_BLANK = "extra_blank"
FILLER = "filler"
UNCHECKED = "unchecked"
MARKER = "marker"
INPUT = "input"

Span = tuple[int, int]  # [start, end) character positions within a line


@dataclass(frozen=True)
class Cell:
    text: str | None  # None: no line on this side
    kind: str
    number: int | None = None  # 1-based line number in that output
    inputs: tuple[Span, ...] = ()  # parts of ``text`` that were typed in, not printed


@dataclass(frozen=True)
class Row:
    expected: Cell
    actual: Cell


@dataclass(frozen=True)
class Line:
    """One line of the console view of an output."""

    text: str
    inputs: tuple[Span, ...]
    start: int  # position in the raw output where this line begins


def split_lines(text: str) -> list[str]:
    """Lines of ``text``; the newline that ends the last line doesn't start a new one."""
    if not text:
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def console_lines(output: str, reads: list[tuple[int, str]] | None = None) -> list[Line]:
    """``output`` split into lines, with each read's input put back where it was read.

    ``reads`` holds (position in ``output``, input text) pairs, in order.
    """
    # Build the console text piece by piece: (text, is_input, raw position).
    pieces: list[tuple[str, bool, int]] = []
    pos = 0
    for at, typed in reads or []:
        at = min(max(at, pos), len(output))
        if at > pos:
            pieces.append((output[pos:at], False, pos))
            pos = at
        if not typed.endswith("\n"):
            typed += "\n"  # the Enter that sent it
        pieces.append((typed, True, at))
    if pos < len(output):
        pieces.append((output[pos:], False, pos))

    lines: list[Line] = []
    text, spans, start = "", [], None
    for piece, typed, raw in pieces:
        offset = 0
        for part in piece.split("\n"):
            if start is None:
                start = raw + (0 if typed else offset)
            if part:
                if typed:
                    spans.append((len(text), len(text) + len(part)))
                text += part
            offset += len(part) + 1
            if offset <= len(piece):  # this part ended with a newline
                lines.append(Line(text, tuple(spans), start))
                text, spans, start = "", [], None
    if text or spans:
        lines.append(Line(text, tuple(spans), start if start is not None else len(output)))
    return lines


def input_cells(input_text: str | None) -> list[Cell]:
    """The test's input listed as cells, for a side where it isn't known when it was read."""
    lines = split_lines(input_text or "")
    if not lines:
        return []
    return [
        Cell("Input (typed into the program):", MARKER),
        *(Cell(line, INPUT, inputs=((0, len(line)),)) for line in lines),
        Cell("Output:", MARKER),
    ]


def _checked_count(output: str, lines: list[Line], compare_lines: int | None) -> int:
    """How many console lines fall within the first ``compare_lines`` lines of output."""
    if compare_lines is None:
        return len(lines)
    parts = output.split("\n")
    if len(parts) <= compare_lines:
        return len(lines)
    cutoff = len("\n".join(parts[:compare_lines])) + 1
    return sum(1 for line in lines if line.start < cutoff)


def align(
    expected: str,
    actual: str,
    compare_lines: int | None = None,
    expected_reads: list[tuple[int, str]] | None = None,
    actual_reads: list[tuple[int, str]] | None = None,
) -> list[Row]:
    exp = console_lines(expected, expected_reads)
    act = console_lines(actual, actual_reads)
    exp_checked = exp[: _checked_count(expected, exp, compare_lines)]
    act_checked = act[: _checked_count(actual, act, compare_lines)]

    def cell(line: Line, kind: str, number: int) -> Cell:
        return Cell(line.text, kind, number, line.inputs)

    rows: list[Row] = []
    matcher = difflib.SequenceMatcher(
        None, [x.text for x in exp_checked], [x.text for x in act_checked], autojunk=False
    )
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                rows.append(
                    Row(
                        cell(exp_checked[i1 + k], SAME, i1 + k + 1),
                        cell(act_checked[j1 + k], SAME, j1 + k + 1),
                    )
                )
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            i, j = i1 + k, j1 + k
            e = exp_checked[i] if i < i2 else None
            a = act_checked[j] if j < j2 else None
            left = Cell(None, FILLER) if e is None else cell(e, DIFF, i + 1)
            if a is None:
                right = Cell(None, FILLER)
            elif e is None and not a.text.strip():
                right = cell(a, EXTRA_BLANK, j + 1)
            else:
                right = cell(a, DIFF, j + 1)
            rows.append(Row(left, right))

    exp_rest, act_rest = exp[len(exp_checked) :], act[len(act_checked) :]
    if exp_rest or act_rest:
        note = f"(not checked after output line {compare_lines})"
        rows.append(Row(Cell(note, MARKER), Cell(note, MARKER)))
        start_e, start_a = len(exp_checked) + 1, len(act_checked) + 1
        for k, (e, a) in enumerate(zip_longest(exp_rest, act_rest)):
            rows.append(
                Row(
                    Cell(None, FILLER) if e is None else cell(e, UNCHECKED, start_e + k),
                    Cell(None, FILLER) if a is None else cell(a, UNCHECKED, start_a + k),
                )
            )
    return rows
