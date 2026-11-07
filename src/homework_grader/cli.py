"""Command-line interface.

python -m homework_grader grade ASSIGNMENT_DIR SUBMISSIONS [--csv results.csv] [--details]
python -m homework_grader make-expected ASSIGNMENT_DIR [--overwrite]
python -m homework_grader gui
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .assignment import AssignmentError, load_assignment
from .grading import JavaNotFoundError, generate_expected, grade_all
from .report import describe_student, format_table, write_csv
from .submissions import find_submissions, open_submissions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="homework_grader", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("grade", help="Grade every student's latest submission.")
    g.add_argument("assignment", type=Path, help="Assignment folder (has assignment.toml)")
    g.add_argument("submissions", type=Path, help="Teams .zip or extracted folder")
    g.add_argument("--csv", type=Path, help="Also save results to this CSV file")
    g.add_argument(
        "--details", action="store_true", help="Show diffs for students who missed a test"
    )
    g.add_argument("--workers", type=int, default=4, help="Students graded at once (default 4)")

    m = sub.add_parser("make-expected", help="Create expected.txt files from reference/.")
    m.add_argument("assignment", type=Path)
    m.add_argument("--overwrite", action="store_true", help="Replace existing expected.txt files")

    sub.add_parser("gui", help="Open the desktop window.")

    args = parser.parse_args(argv)
    try:
        if args.command == "grade":
            return _grade(args)
        if args.command == "make-expected":
            for msg in generate_expected(load_assignment(args.assignment), args.overwrite):
                print(msg)
            return 0
        from .gui import main as gui_main

        gui_main()
        return 0
    except (AssignmentError, JavaNotFoundError, FileNotFoundError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


def _grade(args: argparse.Namespace) -> int:
    assignment = load_assignment(args.assignment)
    with open_submissions(args.submissions) as root:
        submissions = find_submissions(root)
        if not submissions:
            print("No student folders found.", file=sys.stderr)
            return 1
        print(f"Grading {len(submissions)} students on {len(assignment.tests)} tests...")
        results = grade_all(assignment, submissions, workers=args.workers)

    print()
    print(format_table(results))
    if args.details:
        for r in results:
            if not r.all_passed:
                print("\n" + "=" * 70)
                print(describe_student(r))
    if args.csv:
        write_csv(results, args.csv)
        print(f"\nSaved {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
