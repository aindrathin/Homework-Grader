# Homework Grader

Runs and tests AP Computer Science A student Java assignments. It compiles each
student's latest Teams submission, types in test input, and checks the output
against expected output files, character for character.

## Requirements

- Python 3.11+
- A JDK (Eclipse Temurin 21 recommended) with `java` and `javac` on PATH

## Setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

## Running the grader

Do the Setup steps once. After that, open PowerShell in the `HomeworkGrader` folder each time
you want to grade.

### Desktop window

Start it with:

```powershell
.\.venv\Scripts\python.exe -m homework_grader gui
```

You can also double-click `.venv\Scripts\homework-grader-gui.exe`, which opens the window without
a PowerShell window. You can pin a shortcut to it on your desktop or taskbar.

To grade an assignment:

1. Download the submissions from Teams as a .zip. You don't need to extract it.
2. Pick the assignment from the dropdown. The list shows every folder in `assignments\` that
   has an `assignment.toml`. After adding a new assignment, click **Refresh**.
3. Click **Zip…** to choose the .zip, or **Folder…** to choose a folder you already extracted.
4. If the assignment has no `expected.txt` files yet, click **Generate expected output**.
5. Click **Run grader**. The progress bar fills in as students finish, and several students
   are graded at once.
6. Click a student's row to see notes, compiler errors, and line-by-line differences for each
   test. Green rows passed every test, red rows missed at least one test, and orange rows
   couldn't be tested at all.
7. Click **Export CSV** to save the results to a spreadsheet.

### Command line

```powershell
# Create expected.txt files from the solution in reference\ (add --overwrite to replace them)
.\.venv\Scripts\python.exe -m homework_grader make-expected assignments\DiceRoller

# Grade a Teams .zip or an extracted folder
.\.venv\Scripts\python.exe -m homework_grader grade assignments\DiceRoller submissions.zip
```

Options for `grade`:

| Option | What it does |
|---|---|
| `--details` | Shows differences and errors for every student who missed a test |
| `--csv results.csv` | Saves the results table to a CSV file |
| `--workers 4` | Sets how many students are graded at once (default 4) |

To try it on the sample class:

```powershell
.\.venv\Scripts\python.exe -m homework_grader grade assignments\DiceRoller examples\submittedWork --details
```

### What happens during a run

For each student, the grader:

1. Finds the student's latest version folder.
2. Copies their `.java` files into a new temporary folder outside OneDrive. The originals are
   never changed.
3. Seeds random-number calls in that copy (see [Random numbers](#random-numbers)).
4. Compiles all the files with `javac`.
5. Runs the `main_class` once for each test. It types in `input.txt` and stops the program if
   it runs longer than `timeout_seconds` (10 seconds by default).
6. Compares the output with `expected.txt`.
7. Deletes the temporary folder.

### Reading the results

Each test gets one of these results:

| Result | Meaning |
|---|---|
| `PASS` | Output matched `expected.txt` exactly |
| `FAIL` | The program finished, but its output was different |
| `TIMEOUT` | The program ran longer than the time limit, for example an infinite loop or waiting for more input |
| `RUNTIME ERROR` | The program crashed, for example with an exception or because it ran out of input |
| `NO EXPECTED FILE` | The test folder has no `expected.txt` |

A student whose code couldn't be tested gets one of these results instead:

| Result | Meaning |
|---|---|
| `COMPILE ERROR` | The code doesn't compile. The details show the `javac` errors. |
| `MISSING FILES` | A class in `main_class` or `required_classes` wasn't submitted |
| `NO SUBMISSION` | The latest version folder has no `.java` files |
| `GRADER ERROR` | Something went wrong inside the grader. The details show the cause. |

Notes in the details show what the grader did, for example which version it graded, which
renamed files it used, and which random-number calls it seeded.

## Setting up an assignment

Create a folder inside `assignments\`:

```
MyAssignment/
    assignment.toml      main_class = "Main"  (also: timeout_seconds, required_classes)
    reference/           your solution's .java files
    tests/
        test1/
            input.txt    what gets typed in (optional)
            seed.txt     random seed for this test (optional)
            expected.txt exact expected output
```

You can write `expected.txt` yourself, or put your solution in `reference/` and use
**Generate expected output** (or `make-expected`) to create it.

The program's input is not echoed in the output, so `expected.txt` contains prompts like
`Enter a number: ` followed directly by the next printed text.

See `assignments/DiceRoller` and `examples/submittedWork` for a working example.

## Random numbers

The grader edits a temporary copy of each student's code (never the original) so that
`Math.random()`, `new Random()`, and `Collections.shuffle(list)` all use one generator
seeded with the test's `seed.txt`. Students can reproduce an expected file by hand:

```java
Random r = new Random(42);          // the seed shown for that test
int roll = (int) (r.nextDouble() * 6) + 1;   // same as (int) (Math.random() * 6) + 1
```

The same seed only gives the same numbers if the student makes the same random calls in
the same order. `r.nextInt(6)` gives different numbers than `(int) (Math.random() * 6)`,
so assignment instructions should say exactly which formula to use.

## Teams submissions

The grader expects `submittedWork/<student>/<version folder>/*.java`. It grades only the
version folder with the highest number, and recognizes files Teams renamed (such as
`Main 1.java`) by the class declared inside them.

## Safety

Student programs run in a temporary folder with a time limit and a 256 MB memory limit.
They are not otherwise sandboxed, so they can still read and write files your account can.
