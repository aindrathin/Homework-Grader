"""A simple desktop window (tkinter, included with Python) for running the grader."""

from __future__ import annotations

import copy
import queue
import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .assignment import Assignment, load_assignment
from .compare import (
    DIFF,
    EXTRA_BLANK,
    FILLER,
    INPUT,
    MARKER,
    SAME,
    UNCHECKED,
    Cell,
    align,
    input_cells,
)
from .grading import (
    GRADED,
    StudentResult,
    TestResult,
    first_lines,
    generate_expected,
    grade_all,
    grade_submission,
    normalize,
    read_expected,
    read_input,
)
from .manual import ManualPasses, run_key
from .report import hint, show_whitespace, write_csv
from .saved_state import SavedEdits, SavedSession, StudentNotes, fingerprint
from .settings import load_settings, save_settings
from .submissions import Submission, find_submissions, open_submissions

ALL_PASSED_BG = "#c6efce"  # student list: every test passed
SOME_PASSED_BG = "#fff2a8"  # some tests passed
NONE_PASSED_BG = "#ffc7c7"  # no tests passed (including compile errors)
PASS_COLOR = "#1b7f3b"
FAIL_COLOR = "#b3261e"
DIFF_BG = "#ffc9c9"  # red: differing line
BLANK_BG = "#fff176"  # yellow: extra blank line
FILLER_BG = "#ececec"  # gray: no line on this side
MUTED = "#8a8a8a"
INPUT_COLOR = "#1f5fa8"  # blue: input typed into the program (also bold, underlined)
MONO = ("Consolas", 10)

# The repo's assignments/ folder (src/homework_grader/gui.py -> repo root).
ASSIGNMENTS_DIR = Path(__file__).resolve().parents[2] / "assignments"


def list_assignments(folder: Path = ASSIGNMENTS_DIR) -> dict[str, Path]:
    """Map each assignment name to its folder (any subfolder with an assignment.toml)."""
    if not folder.is_dir():
        return {}
    return {
        p.name: p
        for p in sorted(folder.iterdir(), key=lambda p: p.name.lower())
        if (p / "assignment.toml").is_file()
    }


def short_result(r: StudentResult, test_count: int) -> str:
    """Result shown next to a name in the student list.

    With more than one test this is the fraction passed, like "2/3"."""
    if r.status != GRADED:
        detail = r.status
    elif test_count == 1:
        detail = "passed" if r.all_passed else r.tests[0].status
    else:
        detail = ""
    if any(t.manual_pass for t in r.tests):
        detail = f"{detail} (manual)".lstrip()
    if test_count > 1:
        return f"{r.passed}/{test_count}  {detail}".rstrip()
    return detail


def result_level(r: StudentResult) -> str:
    """'all', 'some', or 'none' tests passed; picks the row color in the student list."""
    if r.all_passed:
        return "all"
    return "some" if r.passed > 0 else "none"


def file_label(sub: Submission, class_name: str) -> str:
    """How a student's file is named in the code pane's file list."""
    name = sub.files[class_name].name
    return name if name == f"{class_name}.java" else f"{name}  (class {class_name})"


def edited_submission(sub: Submission, edits: dict[str, str]) -> Submission:
    """A copy of ``sub`` that grades ``edits`` (class -> source) instead of the student's code."""
    edits = {c: text for c, text in edits.items() if c in sub.files}
    return replace(
        sub,
        notes=list(sub.notes),
        sources={**sub.sources, **edits},
        edited=sorted(edits),
    )


def info_text(r: StudentResult, t: TestResult | None) -> str:
    """Everything about a student that isn't the output itself."""
    parts = [f"{r.student}   ({r.version or 'no version folder'})   {r.summary}"]
    if t is not None:
        seed = f", seed {t.seed}" if t.seed is not None else ""
        line = f"Test {t.name}{seed}: {t.shown_status}"
        if t.compare_lines is not None:
            line += f"   (only the first {t.compare_lines} lines are checked)"
        parts.append(line)
        if t.manual_pass:
            parts.append(f"You marked this test as passing (the run itself was {t.status}).")
        if t.status == "FAIL" and t.expected is not None:
            h = hint(
                first_lines(t.expected, t.compare_lines), first_lines(t.actual, t.compare_lines)
            )
            if h:
                parts.append(f"Hint: {h}")
        if t.exit_code not in (None, 0):
            parts.append(f"Exit code {t.exit_code}")
        if t.stderr.strip():
            parts.append("Errors:\n" + t.stderr.strip()[:4000])
    if r.compile_output.strip():
        parts.append("Compiler output:\n" + r.compile_output.strip())
    if r.notes:
        parts.append("Notes:\n" + "\n".join(f"  - {n}" for n in r.notes))
    return "\n".join(parts)


class GraderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Homework Grader")
        self.geometry("1600x800")
        self.minsize(1100, 550)

        self.assignment_var = tk.StringVar()
        self.submissions_var = tk.StringVar()
        self.assignments: dict[str, Path] = {}
        self.status_var = tk.StringVar(value="Choose an assignment and the submissions.")
        self.results: dict[str, StudentResult] = {}
        self.order: list[str] = []
        self.shown_student: str | None = None
        self.assignment: Assignment | None = None  # the one last graded
        self.submissions: dict[str, Submission] = {}
        # Teacher's edits: student -> class -> source text (also saved, see saved_state.py).
        self.edits: dict[str, dict[str, str]] = {}
        self.saved_edits = SavedEdits()
        self.notes = StudentNotes()  # the teacher's notes on each student (saved)
        self.notes_student: str | None = None  # whose note is in the notes box
        self.notes_save_job: str | None = None  # pending autosave of the notes box
        self.session = SavedSession()  # the last grading run, restored on start
        self.graded_name: str | None = None  # assignment name of the current results
        self.graded_path: Path | None = None  # submissions of the current results
        self.stamp: str | None = None  # fingerprint of the assignment + submissions graded
        self.code_student: str | None = None  # whose code is in the code pane
        self.code_class: str | None = None  # which of their classes
        self.code_classes: list[str] = []  # the file list's classes, in order
        self.manual = ManualPasses()  # tests marked as passing by hand (saved)
        self.run_key: str | None = None  # which saved marks apply to the current results
        self.compared: tuple[str, str] | None = None  # (student, test) in the comparison
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        self._build()
        self._restore_choices()
        self.assignment_var.trace_add("write", lambda *_: self._save_choices())
        self.submissions_var.trace_add("write", lambda *_: self._save_choices())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)
        self.after(150, self._restore_session)

    def _on_close(self) -> None:
        """Save the code being edited and the note being typed, then close."""
        self._store_code_edit()
        self._store_note()
        self.destroy()

    # ---------------------------------------------------------- remembered choices
    def _restore_choices(self) -> None:
        """Put back the assignment and submissions chosen the last time the window was used."""
        saved = load_settings()
        if saved.get("assignment") in self.assignments:
            self.assignment_var.set(saved["assignment"])
        submissions = saved.get("submissions", "")
        if submissions and Path(submissions).exists():
            self.submissions_var.set(submissions)

    def _save_choices(self) -> None:
        save_settings(
            {
                "assignment": self.assignment_var.get(),
                "submissions": self.submissions_var.get().strip(),
            }
        )

    # ------------------------------------------------------------- saved session
    def _save_session(self) -> None:
        """Save the current results so reopening the window shows them without grading."""
        if self.stamp is None or self.graded_name is None or self.graded_path is None:
            return
        self.session.save(
            self.graded_name,
            self.graded_path,
            self.stamp,
            [self.submissions[s] for s in self.order if s in self.submissions],
            [self.results[s] for s in self.order if s in self.results],
        )

    def _restore_session(self) -> None:
        """Show the last grading run again, if its assignment and submissions haven't changed."""
        saved = self.session.load()
        if saved is None or self.busy or self.results:
            return
        name, path = saved["assignment"], saved["submissions"]
        folder = self.assignments.get(name)
        if folder is None or not path.exists():
            return
        try:
            assignment = load_assignment(folder)
            unchanged = fingerprint(assignment.root, path) == saved["fingerprint"]
        except Exception:
            return
        if not unchanged:
            self.status_var.set(
                f"{name} or its submissions changed since they were last graded. "
                "Press Run grader to grade them again."
            )
            return
        self.assignment_var.set(name)
        self.submissions_var.set(str(path))
        self.assignment = assignment
        self.graded_name, self.graded_path = name, path
        self.run_key = run_key(name, path)
        self.stamp = saved["fingerprint"]
        results: list[StudentResult] = saved["results"]
        self._on_students(saved["submissions_list"])
        for r in results:
            if r.student in self.submissions:
                self._update_student_row(r)
        self.progress.configure(value=len(results))
        full = sum(r.all_passed for r in results)
        self.status_var.set(
            f"Restored the last grading of {name}: {full} of {len(results)} students passed "
            "every test. Press Run grader to grade again."
        )

    def _picker_start_dir(self) -> str | None:
        """Where the file pickers open: next to the last submissions, if that still exists."""
        text = self.submissions_var.get().strip()
        if not text:
            return None
        folder = Path(text).parent  # the folder holding the last .zip or submissions folder
        return str(folder) if folder.is_dir() else None

    # ----------------------------------------------------------------- layout
    def _build(self) -> None:
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Assignment:").grid(row=0, column=0, sticky="w", pady=2)
        self.assignment_box = ttk.Combobox(top, textvariable=self.assignment_var, state="readonly")
        self.assignment_box.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Refresh", command=self._refresh_assignments).grid(
            row=0, column=2, sticky="w"
        )
        self._refresh_assignments()

        ttk.Label(top, text="Submissions (.zip or folder):").grid(
            row=1, column=0, sticky="w", pady=2
        )
        ttk.Entry(top, textvariable=self.submissions_var).grid(row=1, column=1, sticky="ew", padx=6)
        pick = ttk.Frame(top)
        pick.grid(row=1, column=2)
        ttk.Button(pick, text="Folder…", command=self._pick_folder).pack(side="left")
        ttk.Button(pick, text="Zip…", command=self._pick_zip).pack(side="left", padx=(4, 0))

        actions = ttk.Frame(self, padding=(10, 0))
        actions.pack(fill="x")
        self.run_button = ttk.Button(actions, text="Run grader", command=self._run)
        self.run_button.pack(side="left")
        self.expected_button = ttk.Button(
            actions, text="Generate expected output…", command=self._make_expected
        )
        self.expected_button.pack(side="left", padx=6)
        self.csv_button = ttk.Button(actions, text="Export CSV…", command=self._export_csv)
        self.csv_button.pack(side="left")
        self.progress = ttk.Progressbar(actions, length=200, mode="determinate")
        self.progress.pack(side="right")

        ttk.Label(self, textvariable=self.status_var, padding=(10, 6)).pack(fill="x")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left = ttk.PanedWindow(body, orient="vertical")
        body.add(left, weight=0)
        left.add(self._build_student_list(left), weight=1)
        left.add(self._build_notes(left), weight=0)

        right = ttk.PanedWindow(body, orient="vertical")
        body.add(right, weight=1)
        right.add(self._build_info(right), weight=0)
        right.add(self._build_compare(right), weight=1)
        # The student's code, in its own pane on the far right.
        body.add(self._build_code(body), weight=1)
        # Start the code pane at about 40% of the window, once the window has a size.
        self.after(50, lambda: body.sashpos(1, int(body.winfo_width() * 0.6)))

    def _build_student_list(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, width=300)
        # Students are top-level rows; with 2+ tests, each test is a row under its student.
        self.students = ttk.Treeview(
            frame, columns=("result",), show="tree headings", selectmode="browse"
        )
        self.students.heading("#0", text="Student", anchor="w")
        self.students.heading("result", text="Result", anchor="w")
        self.students.column("#0", width=190, anchor="w")
        self.students.column("result", width=110, anchor="w")
        self.students.tag_configure("all", background=ALL_PASSED_BG)
        self.students.tag_configure("some", background=SOME_PASSED_BG)
        self.students.tag_configure("none", background=NONE_PASSED_BG)
        self.students.tag_configure("test_pass", foreground=PASS_COLOR, background="#e9f7ec")
        self.students.tag_configure("test_fail", foreground=FAIL_COLOR, background="#fdeaea")
        self.students.tag_configure("shown", font=("Segoe UI", 9, "bold"))
        self.test_rows: dict[str, tuple[str, str]] = {}  # row id -> (student, test name)
        self.shown_test: str | None = None  # row id of the test in the comparison
        self.students.bind("<<TreeviewSelect>>", self._show_selected)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.students.yview)
        self.students.configure(yscrollcommand=scroll.set)
        self.students.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return frame

    def _build_info(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        self.info = tk.Text(frame, height=6, wrap="word", font=MONO, state="disabled")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.info.yview)
        self.info.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.info.pack(side="left", fill="both", expand=True)
        return frame

    def _build_notes(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(0, 6, 0, 0))
        self.notes_heading = ttk.Label(frame, font=("Segoe UI", 10, "bold"))
        self.notes_heading.pack(anchor="w")
        box = ttk.Frame(frame)
        box.pack(fill="both", expand=True, pady=(2, 0))
        self.notes_text = tk.Text(box, height=8, width=30, wrap="word", font=("Segoe UI", 10))
        scroll = ttk.Scrollbar(box, orient="vertical", command=self.notes_text.yview)
        self.notes_text.configure(yscrollcommand=scroll.set, undo=True)
        scroll.pack(side="right", fill="y")
        self.notes_text.pack(side="left", fill="both", expand=True)
        self.notes_text.bind("<<Modified>>", self._note_changed)
        self.notes_text.bind("<FocusOut>", lambda _e: self._store_note())
        self._show_note(None)
        return frame

    # ------------------------------------------------------------------- notes
    def _show_note(self, student: str | None) -> None:
        """Put ``student``'s saved note in the notes box (saving the one shown before)."""
        if student is not None and student == self.notes_student:
            return
        self._store_note()
        self.notes_student = student
        self.notes_text.configure(state="normal")
        self.notes_text.delete("1.0", "end")
        if student is None or self.graded_name is None:
            self.notes_student = None
            self.notes_heading.configure(text="Notes")
            self.notes_text.insert("1.0", "Choose a student to take notes.")
            self.notes_text.configure(state="disabled", foreground=MUTED)
        else:
            self.notes_heading.configure(text=f"Notes on {student}")
            self.notes_text.insert("1.0", self.notes.get(self.graded_name, student))
            self.notes_text.configure(foreground="black")
        self.notes_text.edit_reset()
        self.notes_text.edit_modified(False)

    def _note_changed(self, _event=None) -> None:
        """Save the note shortly after typing stops."""
        if not self.notes_text.edit_modified():
            return
        self.notes_text.edit_modified(False)
        if self.notes_save_job is not None:
            self.after_cancel(self.notes_save_job)
        self.notes_save_job = self.after(1000, self._store_note)

    def _store_note(self) -> None:
        if self.notes_save_job is not None:
            self.after_cancel(self.notes_save_job)
            self.notes_save_job = None
        if self.notes_student is None or self.graded_name is None:
            return
        text = self.notes_text.get("1.0", "end-1c")
        self.notes.set(self.graded_name, self.notes_student, text)

    def _build_compare(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(6, 4))
        self.test_heading = ttk.Label(header, font=("Segoe UI", 10, "bold"))
        self.test_heading.pack(side="left")
        self.mark_button = ttk.Button(
            header, text="Mark test as passing", command=self._toggle_manual_pass
        )
        self.mark_button.pack(side="left", padx=(10, 0))
        self.mark_button.configure(state="disabled")
        legend = ttk.Frame(header)
        legend.pack(side="right")
        for color, text in (
            (DIFF_BG, "different"),
            (BLANK_BG, "extra blank line"),
            (FILLER_BG, "no line here"),
        ):
            tk.Label(legend, bg=color, width=2, relief="solid", borderwidth=1).pack(
                side="left", padx=(10, 3)
            )
            ttk.Label(legend, text=text).pack(side="left")

        panes = ttk.Frame(frame)
        panes.pack(fill="both", expand=True)
        panes.columnconfigure(0, weight=1, uniform="side")
        panes.columnconfigure(1, weight=1, uniform="side")
        panes.rowconfigure(1, weight=1)
        ttk.Label(panes, text="Expected output", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(panes, text="Student output", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=1, sticky="w", padx=(6, 0)
        )

        self.vbar = ttk.Scrollbar(panes, orient="vertical", command=self._scroll_both)
        self.vbar.grid(row=1, column=2, sticky="ns")
        self.expected_text = self._output_text(panes, column=0)
        self.actual_text = self._output_text(panes, column=1)
        for text, other in (
            (self.expected_text, self.actual_text),
            (self.actual_text, self.expected_text),
        ):
            text.configure(yscrollcommand=lambda f, last, o=other: self._synced(f, last, o))
        return frame

    def _build_code(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=(8, 0, 0, 0))
        ttk.Label(frame, text="Student code", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        pick = ttk.Frame(frame)
        pick.pack(fill="x", pady=(4, 2))
        ttk.Label(pick, text="File:").pack(side="left")
        self.code_file_box = ttk.Combobox(pick, state="readonly")
        self.code_file_box.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.code_file_box.bind("<<ComboboxSelected>>", self._pick_code_file)
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=(2, 2))
        self.rerun_button = ttk.Button(
            bar, text="Rerun tests for this student", command=self._rerun_student
        )
        self.rerun_button.pack(side="left")
        self.revert_button = ttk.Button(bar, text="Revert file", command=self._revert_code)
        self.revert_button.pack(side="left", padx=6)
        self.code_state = ttk.Label(frame, foreground=MUTED, font=("Segoe UI", 9, "bold"))
        self.code_state.pack(anchor="w")
        ttk.Label(
            frame,
            text="Edits are saved by the grader; the student's file is never changed.",
            foreground=MUTED,
        ).pack(anchor="w", pady=(0, 4))

        box = ttk.Frame(frame)
        box.pack(fill="both", expand=True)
        self.code_lines = tk.Text(
            box,
            width=5,
            font=MONO,
            state="disabled",
            takefocus=0,
            foreground=MUTED,
            background="#f4f4f4",
            borderwidth=0,
            padx=4,
            cursor="arrow",
        )
        self.code = tk.Text(box, wrap="none", font=MONO, undo=True, maxundo=-1, tabs=("4c",))
        ybar = ttk.Scrollbar(box, orient="vertical", command=self.code.yview)
        xbar = ttk.Scrollbar(box, orient="horizontal", command=self.code.xview)
        self.code.configure(
            yscrollcommand=lambda f, last: self._code_scrolled(ybar, f, last),
            xscrollcommand=xbar.set,
        )
        xbar.pack(side="bottom", fill="x")
        ybar.pack(side="right", fill="y")
        self.code_lines.pack(side="left", fill="y")
        self.code.pack(side="left", fill="both", expand=True)
        self.code_lines.bind("<MouseWheel>", self._code_lines_wheel)
        self.code.bind("<<Modified>>", self._code_changed)
        self._show_code_message("Choose a student to see their code.")
        return frame

    def _output_text(self, parent, column: int) -> tk.Text:
        box = ttk.Frame(parent)
        box.grid(row=1, column=column, sticky="nsew", padx=(6 if column else 0, 0))
        text = tk.Text(box, wrap="none", font=MONO, state="disabled", undo=False)
        xbar = ttk.Scrollbar(box, orient="horizontal", command=text.xview)
        text.configure(xscrollcommand=xbar.set)
        xbar.pack(side="bottom", fill="x")
        text.pack(fill="both", expand=True)
        text.tag_configure("lineno", foreground=MUTED)
        text.tag_configure(DIFF, background=DIFF_BG)
        text.tag_configure(EXTRA_BLANK, background=BLANK_BG)
        text.tag_configure(FILLER, background=FILLER_BG)
        text.tag_configure(UNCHECKED, foreground=MUTED)
        text.tag_configure(MARKER, foreground=MUTED, font=(*MONO, "italic"))
        text.tag_configure(INPUT, foreground=INPUT_COLOR, font=(*MONO, "bold"), underline=True)
        text.tag_raise("lineno")
        text.bind("<MouseWheel>", self._wheel)
        return text

    # ------------------------------------------------------- synced scrolling
    def _scroll_both(self, *args) -> None:
        self.expected_text.yview(*args)
        self.actual_text.yview(*args)

    def _synced(self, first: str, last: str, other: tk.Text) -> None:
        self.vbar.set(first, last)
        if other.yview()[0] != float(first):
            other.yview_moveto(first)

    def _wheel(self, event) -> str:
        self._scroll_both("scroll", int(-event.delta / 120) * 3, "units")
        return "break"

    # ------------------------------------------------------------- code tab
    def _code_scrolled(self, bar: ttk.Scrollbar, first: str, last: str) -> None:
        bar.set(first, last)
        self.code_lines.yview_moveto(first)

    def _code_lines_wheel(self, event) -> str:
        self.code.yview_scroll(int(-event.delta / 120) * 3, "units")
        return "break"

    def _code_changed(self, _event=None) -> None:
        if not self.code.edit_modified():
            return
        self.code.edit_modified(False)
        self._number_code_lines()
        self._update_code_state()

    def _number_code_lines(self) -> None:
        count = int(self.code.index("end-1c").split(".")[0]) if self.code_class else 0
        self.code_lines.configure(state="normal")
        self.code_lines.delete("1.0", "end")
        self.code_lines.insert("1.0", "\n".join(f"{n:>4}" for n in range(1, count + 1)))
        self.code_lines.configure(state="disabled")
        self.code_lines.yview_moveto(self.code.yview()[0])

    def _original_code(self, student: str, class_name: str) -> str:
        return normalize(self.submissions[student].sources.get(class_name, ""))

    def _current_code(self) -> str:
        return self.code.get("1.0", "end-1c")

    def _store_code_edit(self) -> None:
        """Remember the code pane's text as an edit (or forget it if it matches the original)."""
        student, cls = self.code_student, self.code_class
        if student is None or cls is None:
            return
        text = self._current_code()
        edits = self.edits.setdefault(student, {})
        if text == self._original_code(student, cls):
            edits.pop(cls, None)
        else:
            edits[cls] = text
        if not edits:
            del self.edits[student]
        self._persist_edits(student)

    def _persist_edits(self, student: str) -> None:
        """Save ``student``'s edits (for the version graded) so they survive closing the window."""
        sub = self.submissions.get(student)
        if self.run_key is None or sub is None:
            return
        self.saved_edits.set(self.run_key, student, sub.version, self.edits.get(student, {}))

    def _update_code_state(self) -> None:
        student, cls = self.code_student, self.code_class
        if student is None or cls is None:
            self.code_state.configure(text="")
            self.revert_button.configure(state="disabled")
            return
        text = self._current_code()
        changed = text != self._original_code(student, cls)
        result = self.results.get(student)
        graded = (
            result is not None and cls in result.edited and result.edited_sources.get(cls) == text
        )
        if not changed:
            label = "Student's original code"
        elif graded:
            label = "Edited (these edits were graded)"
        else:
            label = "Edited, not rerun yet"
        self.code_state.configure(text=label, foreground=FAIL_COLOR if changed else MUTED)
        self.revert_button.configure(state="normal" if changed else "disabled")

    def _show_code_message(self, message: str) -> None:
        self.code_class = None
        self.code_classes = []
        self.code_file_box.configure(values=[])
        self.code_file_box.set("")
        self.code.configure(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", message)
        self.code.configure(state="disabled")
        self.code.edit_modified(False)
        self._number_code_lines()
        self._update_code_state()
        self.rerun_button.configure(state="disabled")

    def _load_code(self, student: str) -> None:
        """Show ``student``'s files in the code pane (keeping any edits to the one shown)."""
        if student == self.code_student:
            return
        self._store_code_edit()
        self.code_student = student
        sub = self.submissions.get(student)
        if sub is None or not sub.files:
            self._show_code_message("(No .java files were submitted.)")
            return
        main = self.assignment.main_class if self.assignment else None
        self.code_classes = sorted(sub.files, key=lambda c: (c != main, c.lower()))
        self.code_file_box.configure(values=[file_label(sub, c) for c in self.code_classes])
        self._show_code_file(self.code_classes[0])
        self.rerun_button.configure(state="disabled" if self.busy else "normal")

    def _show_code_file(self, class_name: str) -> None:
        student = self.code_student
        assert student is not None
        self.code_class = class_name
        self.code_file_box.set(file_label(self.submissions[student], class_name))
        text = self.edits.get(student, {}).get(class_name)
        if text is None:
            text = self._original_code(student, class_name)
        self.code.configure(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", text)
        self.code.edit_reset()
        self.code.edit_modified(False)
        self.code.mark_set("insert", "1.0")
        self.code.yview_moveto(0)
        self._number_code_lines()
        self._update_code_state()

    def _pick_code_file(self, _event=None) -> None:
        index = self.code_file_box.current()
        if index < 0 or self.code_student is None:
            return
        self._store_code_edit()
        self._show_code_file(self.code_classes[index])

    def _revert_code(self) -> None:
        student, cls = self.code_student, self.code_class
        if student is None or cls is None:
            return
        if not messagebox.askyesno(
            "Revert file",
            f"Throw away your edits to {self.submissions[student].files[cls].name} "
            "and show the student's original code?",
        ):
            return
        self.edits.get(student, {}).pop(cls, None)
        if not self.edits.get(student):
            self.edits.pop(student, None)
        self._persist_edits(student)
        self._show_code_file(cls)

    def _rerun_student(self) -> None:
        student = self.code_student
        if self.busy or student is None or self.assignment is None:
            return
        self._store_code_edit()
        sub = edited_submission(self.submissions[student], self.edits.get(student, {}))
        previous = self.results.get(student)
        expected_reads = previous.expected_reads if previous else None
        assignment = self.assignment
        self._set_busy(True, f"Rerunning the tests for {student}…")

        def work() -> None:
            try:
                self.events.put(("rerun", grade_submission(assignment, sub, expected_reads)))
            except Exception as e:
                self.events.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    # ----------------------------------------------------------------- pickers
    def _refresh_assignments(self) -> None:
        self.assignments = list_assignments()
        names = list(self.assignments)
        self.assignment_box.configure(values=names)
        if self.assignment_var.get() not in self.assignments:
            self.assignment_var.set(names[0] if names else "")
        if not names:
            self.status_var.set(f"No assignments found in {ASSIGNMENTS_DIR}")

    def _pick_zip(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose the Teams submissions .zip",
            filetypes=[("Zip files", "*.zip")],
            initialdir=self._picker_start_dir(),
        )
        if path:
            self.submissions_var.set(path)

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(
            title="Choose the extracted submissions folder", initialdir=self._picker_start_dir()
        )
        if path:
            self.submissions_var.set(path)

    # ----------------------------------------------------------------- actions
    def _load_assignment(self):
        folder = self.assignments.get(self.assignment_var.get())
        if folder is None:
            messagebox.showerror(
                "Assignment", f"Choose an assignment.\n\nLooked in {ASSIGNMENTS_DIR}"
            )
            return None
        try:
            return load_assignment(folder)
        except Exception as e:
            messagebox.showerror("Assignment problem", str(e))
            return None

    def _run(self) -> None:
        if self.busy:
            return
        assignment = self._load_assignment()
        if assignment is None:
            return
        subs_path = Path(self.submissions_var.get().strip())
        if not subs_path.exists():
            messagebox.showerror("Submissions", "Choose a submissions .zip file or folder.")
            return

        self._store_code_edit()
        self._store_note()
        self._show_note(None)
        self.assignment = assignment
        self.graded_name = self.assignment_var.get()
        self.graded_path = subs_path
        self.run_key = run_key(self.graded_name, subs_path)
        self.stamp = None
        self.session.clear()  # an unfinished run must not restore the old results
        self.results.clear()
        self.order.clear()
        self.submissions.clear()
        self.edits.clear()
        # Saved edits are graded too (only those made to the version being graded).
        saved_edits = copy.deepcopy(self.saved_edits.data.get(self.run_key, {}))
        self.code_student = None
        self._show_code_message("Choose a student to see their code.")
        self.students.delete(*self.students.get_children())
        self.test_rows.clear()
        self._clear_details()
        self._set_busy(True, "Reading submissions…")

        def work() -> None:
            try:
                try:
                    stamp = fingerprint(assignment.root, subs_path)
                except OSError:
                    stamp = None  # grade anyway; the run just won't be restored later
                with open_submissions(subs_path) as root:
                    subs = find_submissions(root, assignment.submission_folder)
                    self.events.put(("students", subs))
                    to_grade = [
                        edited_submission(
                            s, saved_edits.get(s.student, {}).get(s.version or "", {})
                        )
                        for s in subs
                    ]
                    results = grade_all(
                        assignment, to_grade, on_result=lambda r: self.events.put(("result", r))
                    )
                self.events.put(("done", (results, stamp)))
            except Exception as e:
                self.events.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _make_expected(self) -> None:
        if self.busy:
            return
        assignment = self._load_assignment()
        if assignment is None:
            return
        existing = [t.name for t in assignment.tests if t.expected_path.exists()]
        overwrite = False
        if existing:
            answer = messagebox.askyesnocancel(
                "Expected output",
                f"{len(existing)} test(s) already have expected.txt.\n\n"
                "Yes: replace them\nNo: only create missing ones\nCancel: do nothing",
            )
            if answer is None:
                return
            overwrite = answer
        self._set_busy(True, "Running the reference solution…")

        def work() -> None:
            try:
                messages = generate_expected(assignment, overwrite)
                self.events.put(("messages", messages))
            except Exception as e:
                self.events.put(("error", str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _export_csv(self) -> None:
        if not self.results:
            messagebox.showinfo("Export CSV", "Run the grader first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save results", defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if path:
            write_csv([self.results[s] for s in self.order if s in self.results], Path(path))
            self.status_var.set(f"Saved {path}")

    # ----------------------------------------------------------------- events
    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                getattr(self, f"_on_{kind}")(payload)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_students(self, subs) -> None:
        self.order = [s.student for s in subs]
        self.submissions = {s.student: s for s in subs}
        if self.run_key is not None:
            # Edits to an older version are dropped; the latest version's come back.
            self.saved_edits.keep_versions(self.run_key, {s.student: s.version for s in subs})
            self.edits = {}
            for s in subs:
                saved = self.saved_edits.get(self.run_key, s.student, s.version)
                saved = {c: text for c, text in saved.items() if c in s.files}
                if saved:
                    self.edits[s.student] = saved
        for s in subs:
            self.students.insert("", "end", iid=s.student, text=s.student, values=("waiting…",))
        self.progress.configure(maximum=max(1, len(subs)), value=0)
        self.status_var.set(f"Grading {len(subs)} students…")

    def _on_result(self, r: StudentResult) -> None:
        self._update_student_row(r)
        self.progress.step(1)
        if self.students.selection() == (r.student,):
            self._show_selected()

    def _on_rerun(self, r: StudentResult) -> None:
        self._update_student_row(r)
        self._save_session()
        self._set_busy(False, f"Reran {r.student}: {r.summary}")
        # Show the new result (this also rebuilds the test rows that were replaced).
        self.shown_student = None
        self.students.selection_set(r.student)
        self.students.see(r.student)
        self._show_selected()
        self._update_code_state()

    def _update_student_row(self, r: StudentResult) -> None:
        """Show ``r`` in the student list, replacing any earlier result's test rows."""
        if self.run_key is not None:
            self.manual.apply(self.run_key, r)
        self.results[r.student] = r
        old_rows = self.students.get_children(r.student)
        for row in old_rows:
            self.test_rows.pop(row, None)
            if row == self.shown_test:
                self.shown_test = None
        self.students.delete(*old_rows)
        count = len(self.assignment.tests) if self.assignment else len(r.tests)
        name = f"{r.student}  (edited)" if r.edited else r.student
        self.students.item(
            r.student, text=name, values=(short_result(r, count),), tags=(result_level(r),)
        )
        if count > 1:
            for i, t in enumerate(r.tests):
                row = f"{r.student}::test{i}"
                self.test_rows[row] = (r.student, t.name)
                self.students.insert(
                    r.student,
                    "end",
                    iid=row,
                    text=f"{'✓' if t.passed else '✗'}  {t.name}",
                    values=(t.shown_status,),
                    tags=("test_pass" if t.passed else "test_fail",),
                )

    def _on_done(self, payload: tuple[list[StudentResult], str | None]) -> None:
        results, self.stamp = payload
        self._save_session()
        full = sum(r.all_passed for r in results)
        self._set_busy(False, f"Done. {full} of {len(results)} students passed every test.")
        if results and not self.students.selection():
            first = next((r for r in results if not r.all_passed), results[0])
            self.students.selection_set(first.student)
            self.students.see(first.student)

    def _on_messages(self, messages: list[str]) -> None:
        self._clear_details()
        self._set_text(self.info, "\n".join(messages))
        self._set_busy(False, "Finished generating expected output.")

    def _on_error(self, message: str) -> None:
        self._set_busy(False, "Stopped because of an error.")
        messagebox.showerror("Error", message)

    # ----------------------------------------------------------------- details
    def _show_selected(self, _event=None) -> None:
        sel = self.students.selection()
        if not sel:
            return
        if sel[0] in self.test_rows:  # a test row under a student
            student, test_name = self.test_rows[sel[0]]
        elif sel[0] in self.results:  # a student row
            student, test_name = sel[0], None
        else:
            return
        r = self.results[student]
        test = next((t for t in r.tests if t.name == test_name), None)
        if test is None:
            # Clicked the student: start on their first failing test.
            test = next((t for t in r.tests if not t.passed), r.tests[0] if r.tests else None)
        self.shown_student = student
        self._load_code(student)
        self._show_note(student)
        self._expand_only(student)
        self._mark_shown_test(r, test)

        self._set_text(self.info, info_text(r, test))
        if test is None:
            self._show_without_output(r)
            return
        if test.expected is None:
            rows = align("", test.actual, actual_reads=test.input_reads)
            self._fill_outputs(
                [Cell("(no expected.txt for this test)", MARKER)],
                [row.actual for row in rows],
            )
            return
        expected_reads = r.expected_reads.get(test.name)
        rows = align(
            test.expected, test.actual, test.compare_lines, expected_reads, test.input_reads
        )
        left = [row.expected for row in rows]
        right = [row.actual for row in rows]
        if expected_reads is None:
            # Where the reference read its input isn't known: list the input above
            # the expected output, with blank space on the student side to stay lined up.
            header = input_cells(test.input)
            left = [*header, *left]
            right = [Cell(None, FILLER) for _ in header] + right
        self._fill_outputs(left, right)

    def _show_without_output(self, r: StudentResult) -> None:
        """The student's code never ran (e.g. compile error): expected output on the left."""
        tests = self.assignment.tests if self.assignment else []
        expected = (read_expected(tests[0].expected_path) if tests else None) or ""
        limit = self.assignment.compare_lines if self.assignment else None
        reads = r.expected_reads.get(tests[0].name) if tests else None
        # Aligning the expected output with itself gives its lines, input and gray parts.
        left = [row.expected for row in align(expected, expected, limit, reads, reads)]
        if reads is None and tests:
            left = [*input_cells(read_input(tests[0].input_path)), *left]
        self._fill_outputs(left, [Cell(f"(no output: {r.status})", MARKER)])

    def _expand_only(self, student: str) -> None:
        """Show the test rows of ``student`` and hide everyone else's."""
        for row in self.students.get_children():
            self.students.item(row, open=row == student)

    def _mark_shown_test(self, r: StudentResult, test: TestResult | None) -> None:
        """Bold the test row being compared, and name that test above the outputs."""
        self.compared = (r.student, test.name) if test is not None else None
        self._update_mark_button()
        if self.shown_test and self.students.exists(self.shown_test):
            tags = tuple(t for t in self.students.item(self.shown_test, "tags") if t != "shown")
            self.students.item(self.shown_test, tags=tags)
        self.shown_test = None
        if test is None or len(r.tests) < 2:
            self.test_heading.configure(text="")
            return
        for row, (student, name) in self.test_rows.items():
            if student == r.student and name == test.name:
                self.shown_test = row
                tags = (*self.students.item(row, "tags"), "shown")
                self.students.item(row, tags=tags)
        self.test_heading.configure(
            text=f"Test case: {test.name}  ({test.shown_status})",
            foreground=PASS_COLOR if test.passed else FAIL_COLOR,
        )

    # ------------------------------------------------------------ manual passes
    def _compared_test(self) -> TestResult | None:
        if self.compared is None:
            return None
        student, name = self.compared
        r = self.results.get(student)
        return next((t for t in r.tests if t.name == name), None) if r else None

    def _update_mark_button(self) -> None:
        t = self._compared_test()
        self.mark_button.configure(
            text="Unmark manual pass" if t is not None and t.manual else "Mark test as passing"
        )
        # A test that really passed has nothing to mark (unless an old mark is still on it).
        usable = t is not None and (t.manual or not t.passed)
        ok = not self.busy and self.run_key is not None and usable
        self.mark_button.configure(state="normal" if ok else "disabled")

    def _toggle_manual_pass(self) -> None:
        t = self._compared_test()
        if self.busy or t is None or self.run_key is None or self.compared is None:
            return
        student, name = self.compared
        r = self.results[student]
        self.manual.set(self.run_key, student, r.version, name, not t.manual)
        self._update_student_row(r)  # applies the saved marks and redraws the rows
        # Stay on the same test (its row was rebuilt; single-test students have none).
        row = next((k for k, v in self.test_rows.items() if v == (student, name)), student)
        self.shown_student = None
        self.students.selection_set(row)
        self._show_selected()
        done = "marked as passing" if t.manual else "no longer marked as passing"
        self.status_var.set(f"{student}, test {name}: {done}. {r.summary}")

    def _fill_outputs(self, left: list[Cell], right: list[Cell]) -> None:
        for text, cells in ((self.expected_text, left), (self.actual_text, right)):
            text.configure(state="normal")
            text.delete("1.0", "end")
            for cell in cells:
                number = f"{cell.number:>3}  " if cell.number is not None else "     "
                # The line's kind (its color) applies everywhere except on listed-input
                # lines, so their underline stays on the text.
                line_tags = () if cell.kind == INPUT else (cell.kind,)
                text.insert("end", number, ("lineno", *line_tags))
                body = "" if cell.text is None else cell.text
                if cell.kind in (SAME, DIFF, EXTRA_BLANK, UNCHECKED):
                    body = show_whitespace(body)  # same length, so input spans still fit
                # Typed-in input is bold, underlined and blue; printed output is plain.
                pos = 0
                for start, end in cell.inputs:
                    text.insert("end", body[pos:start], line_tags)
                    text.insert("end", body[start:end], (*line_tags, INPUT))
                    pos = end
                # Tagging the newline too colors the line all the way across.
                text.insert("end", body[pos:] + "\n", line_tags)
            text.configure(state="disabled")
        self.expected_text.yview_moveto(0)
        self.actual_text.yview_moveto(0)

    def _clear_details(self) -> None:
        self.shown_student = None
        self._set_text(self.info, "")
        self._fill_outputs([], [])
        self.shown_test = None
        self.test_heading.configure(text="")
        self.compared = None
        self._update_mark_button()

    @staticmethod
    def _set_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _set_busy(self, busy: bool, status: str) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.run_button, self.expected_button, self.csv_button):
            b.configure(state=state)
        can_rerun = not busy and self.code_class is not None
        self.rerun_button.configure(state="normal" if can_rerun else "disabled")
        self._update_mark_button()
        if busy:
            self.progress.configure(value=0)
        self.status_var.set(status)


def main() -> None:
    GraderApp().mainloop()


if __name__ == "__main__":
    main()
