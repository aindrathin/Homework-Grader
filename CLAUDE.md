# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Background

Homework Grader is a tool for an AP Computer Science A teacher. It helps run and test student programming assignments written in Java.

## Rules

- Ask clarifying questions before starting complex tasks.
- Never make assumptions when important information is missing.
- When multiple approaches exist, explain the tradeoffs.

## Tech stack

- The grader is written in Python 3.11+ (`pyproject.toml`, src layout: `src/homework_grader/`, tests in `tests/`).
- Student code is Java. The grader compiles and runs it with `javac`/`java` from the Eclipse Temurin JDK 21 (`C:\Program Files\Eclipse Adoptium\jdk-21.0.13.9-hotspot`, set as `JAVA_HOME` and on the system PATH).
- Dev tools: pytest for tests, ruff for linting and formatting.

## Commands

Run from the repo root in PowerShell:

- Set up: `py -3.11 -m venv .venv` then `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`
- All tests: `.\.venv\Scripts\python.exe -m pytest`
- One test: `.\.venv\Scripts\python.exe -m pytest tests/test_environment.py::test_compile_and_run_java`
- Lint: `.\.venv\Scripts\ruff.exe check .`
- Format: `.\.venv\Scripts\ruff.exe format .`

- Run the grader: `.\.venv\Scripts\python.exe -m homework_grader grade assignments\DiceRoller examples\submittedWork --details`
- Desktop window: `.\.venv\Scripts\python.exe -m homework_grader gui`
- Tests in `tests/test_grading.py` compile real Java and are skipped if no JDK is found.

## Architecture

Flow: Teams export → `submissions.py` → `grading.py` (uses `rewrite.py`) → `report.py` → CLI (`cli.py`) or tkinter window (`gui.py`).

- `submissions.py`: accepts a .zip or folder, finds `submittedWork/<student>/<version>/`, picks the version folder with the highest number, and maps each `.java` file to its class by the `public class` declaration (Teams renames resubmitted files like `Main 1.java`).
- `assignment.py`: loads `assignment.toml` (`main_class`, `timeout_seconds`, `required_classes`) and `tests/<name>/{input.txt, expected.txt, seed.txt}`. `reference/` holds the teacher's solution.
- `rewrite.py`: edits a temp copy of each file. It routes `Math.random()`, `new Random(...)` and one-arg `Collections.shuffle` to one shared `Random` seeded by `-Dgrader.seed`, and strips `package` lines. Comments and strings are skipped via `javasource.split_segments`. Line numbers are preserved.
- `grading.py`: per student, writes sources to a fresh temp dir, compiles once with `javac`, runs each test with stdin from `input.txt` and a timeout, and compares stdout to `expected.txt` exactly (only `\r\n` → `\n` is normalized). `generate_expected` runs `reference/` the same way to write expected files.

Design decisions from the teacher: exact output matching; only the latest version is graded; randomness is controlled by per-test seeds so students can reproduce an expected file with `new Random(seed)` + `nextDouble()`; student code runs only in a temp folder with a timeout (no other sandbox).

## Environment notes

- The repository is on Windows, inside a OneDrive-synced folder (`C:\Users\aindr\OneDrive\Documents\HomeworkGrader`). OneDrive sync can lock files or slow down folders with many files, such as `node_modules/` or `.venv/`.
- `.env` and `.env.*` files are gitignored. Keep secrets, such as API keys for a grading model, in those files.
