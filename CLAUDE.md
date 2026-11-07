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

## Project status

Only a package skeleton and environment smoke tests (`tests/test_environment.py`) exist so far. The grading design hasn't been decided. When the first grading code is added, document the high-level architecture here: how grading inputs flow through the system and which parts work together.

## Environment notes

- The repository is on Windows, inside a OneDrive-synced folder (`C:\Users\aindr\OneDrive\Documents\HomeworkGrader`). OneDrive sync can lock files or slow down folders with many files, such as `node_modules/` or `.venv/`.
- `.env` and `.env.*` files are gitignored. Keep secrets, such as API keys for a grading model, in those files.
