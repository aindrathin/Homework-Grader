# Homework Grader

Runs and tests AP Computer Science A student Java assignments.

## Requirements

- Python 3.11+
- A JDK (Eclipse Temurin 21 recommended) with `java` and `javac` on PATH

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```
