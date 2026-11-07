# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Homework Grader is a new project with no source code yet. The repository holds only `README.md` and `.gitignore`. There are no build, lint, or test commands yet, and the tech stack hasn't been chosen. The `.gitignore` has entries for both Python (`.venv/`, `venv/`, `__pycache__/`) and Node (`node_modules/`, `dist/`, `build/`), so either one could be used.

When the first code is added, update this file with:
- How to install dependencies, build, lint, and run tests, including how to run a single test
- The high-level architecture: how grading inputs flow through the system and which parts work together

## Environment notes

- The repository is on Windows, inside a OneDrive-synced folder (`C:\Users\aindr\OneDrive\Documents\HomeworkGrader`). OneDrive sync can lock files or slow down folders with many files, such as `node_modules/` or `.venv/`.
- `.env` and `.env.*` files are gitignored. Keep secrets, such as API keys for a grading model, in those files.
