"""Line up expected and student output, row by row, for the side-by-side view.

Each row has an expected cell (left) and a student cell (right). A cell's ``kind`` says
how to color it:

- ``same``: the line matches.
- ``diff``: the line is different, missing, or extra (red).
- ``extra_blank``: the student printed a blank line that isn't in the expected output (yellow).
- ``filler``: nothing on this side; keeps the two sides lined up.
- ``unchecked`` / ``marker``: past ``compare_lines``, so not graded (gray).
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


@dataclass(frozen=True)
class Cell:
    text: str | None  # None: no line on this side
    kind: str
    number: int | None = None  # 1-based line number in that output


@dataclass(frozen=True)
class Row:
    expected: Cell
    actual: Cell


def split_lines(text: str) -> list[str]:
    """Lines of ``text``; the newline that ends the last line doesn't start a new one."""
    if not text:
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def align(expected: str, actual: str, compare_lines: int | None = None) -> list[Row]:
    exp, act = split_lines(expected), split_lines(actual)
    exp_checked = exp if compare_lines is None else exp[:compare_lines]
    act_checked = act if compare_lines is None else act[:compare_lines]

    rows: list[Row] = []
    matcher = difflib.SequenceMatcher(None, exp_checked, act_checked, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                rows.append(
                    Row(
                        Cell(exp_checked[i1 + k], SAME, i1 + k + 1),
                        Cell(act_checked[j1 + k], SAME, j1 + k + 1),
                    )
                )
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            i, j = i1 + k, j1 + k
            e = exp_checked[i] if i < i2 else None
            a = act_checked[j] if j < j2 else None
            left = Cell(None, FILLER) if e is None else Cell(e, DIFF, i + 1)
            if a is None:
                right = Cell(None, FILLER)
            elif e is None and not a.strip():
                right = Cell(a, EXTRA_BLANK, j + 1)
            else:
                right = Cell(a, DIFF, j + 1)
            rows.append(Row(left, right))

    exp_rest, act_rest = exp[len(exp_checked) :], act[len(act_checked) :]
    if exp_rest or act_rest:
        note = f"(not checked after line {compare_lines})"
        rows.append(Row(Cell(note, MARKER), Cell(note, MARKER)))
        start_e, start_a = len(exp_checked) + 1, len(act_checked) + 1
        for k, (e, a) in enumerate(zip_longest(exp_rest, act_rest)):
            rows.append(
                Row(
                    Cell(None, FILLER) if e is None else Cell(e, UNCHECKED, start_e + k),
                    Cell(None, FILLER) if a is None else Cell(a, UNCHECKED, start_a + k),
                )
            )
    return rows
