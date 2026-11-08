"""A simple desktop window (tkinter, included with Python) for running the grader."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .assignment import Assignment, load_assignment
from .compare import DIFF, EXTRA_BLANK, FILLER, MARKER, SAME, UNCHECKED, Cell, align, split_lines
from .grading import (
    GRADED,
    StudentResult,
    TestResult,
    first_lines,
    generate_expected,
    grade_all,
    read_expected,
)
from .report import hint, show_whitespace, write_csv
from .submissions import find_submissions, open_submissions

ALL_PASSED_BG = "#c6efce"  # student list: every test passed
SOME_PASSED_BG = "#fff2a8"  # some tests passed
NONE_PASSED_BG = "#ffc7c7"  # no tests passed (including compile errors)
PASS_COLOR = "#1b7f3b"
FAIL_COLOR = "#b3261e"
DIFF_BG = "#ffc9c9"  # red: differing line
BLANK_BG = "#fff176"  # yellow: extra blank line
FILLER_BG = "#ececec"  # gray: no line on this side
MUTED = "#8a8a8a"
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
    if test_count > 1:
        return f"{r.passed}/{test_count}  {detail}".rstrip()
    return detail


def result_level(r: StudentResult) -> str:
    """'all', 'some', or 'none' tests passed; picks the row color in the student list."""
    if r.all_passed:
        return "all"
    return "some" if r.passed > 0 else "none"


def info_text(r: StudentResult, t: TestResult | None) -> str:
    """Everything about a student that isn't the output itself."""
    parts = [f"{r.student}   ({r.version or 'no version folder'})   {r.summary}"]
    if t is not None:
        seed = f", seed {t.seed}" if t.seed is not None else ""
        line = f"Test {t.name}{seed}: {t.status}"
        if t.compare_lines is not None:
            line += f"   (only the first {t.compare_lines} lines are checked)"
        parts.append(line)
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
        self.geometry("1200x760")
        self.minsize(900, 550)

        self.assignment_var = tk.StringVar()
        self.submissions_var = tk.StringVar()
        self.assignments: dict[str, Path] = {}
        self.status_var = tk.StringVar(value="Choose an assignment and the submissions.")
        self.results: dict[str, StudentResult] = {}
        self.order: list[str] = []
        self.shown_student: str | None = None
        self.assignment: Assignment | None = None  # the one last graded
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        self._build()
        self.after(100, self._poll)

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
        ttk.Button(pick, text="Zip…", command=self._pick_zip).pack(side="left")
        ttk.Button(pick, text="Folder…", command=self._pick_folder).pack(side="left", padx=(4, 0))

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
        body.add(self._build_student_list(body), weight=0)

        right = ttk.PanedWindow(body, orient="vertical")
        body.add(right, weight=1)
        right.add(self._build_info(right), weight=0)
        right.add(self._build_compare(right), weight=1)

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

    def _build_compare(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent)
        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(6, 4))
        self.test_heading = ttk.Label(header, font=("Segoe UI", 10, "bold"))
        self.test_heading.pack(side="left")
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
            title="Choose the Teams submissions .zip", filetypes=[("Zip files", "*.zip")]
        )
        if path:
            self.submissions_var.set(path)

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose the extracted submissions folder")
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

        self.assignment = assignment
        self.results.clear()
        self.order.clear()
        self.students.delete(*self.students.get_children())
        self.test_rows.clear()
        self._clear_details()
        self._set_busy(True, "Reading submissions…")

        def work() -> None:
            try:
                with open_submissions(subs_path) as root:
                    subs = find_submissions(root)
                    self.events.put(("students", subs))
                    results = grade_all(
                        assignment, subs, on_result=lambda r: self.events.put(("result", r))
                    )
                self.events.put(("done", results))
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
        for s in subs:
            self.students.insert("", "end", iid=s.student, text=s.student, values=("waiting…",))
        self.progress.configure(maximum=max(1, len(subs)), value=0)
        self.status_var.set(f"Grading {len(subs)} students…")

    def _on_result(self, r: StudentResult) -> None:
        self.results[r.student] = r
        count = len(self.assignment.tests) if self.assignment else len(r.tests)
        self.students.item(r.student, values=(short_result(r, count),), tags=(result_level(r),))
        if count > 1:
            for i, t in enumerate(r.tests):
                row = f"{r.student}::test{i}"
                self.test_rows[row] = (r.student, t.name)
                self.students.insert(
                    r.student,
                    "end",
                    iid=row,
                    text=f"{'✓' if t.passed else '✗'}  {t.name}",
                    values=(t.status,),
                    tags=("test_pass" if t.passed else "test_fail",),
                )
        self.progress.step(1)
        if self.students.selection() == (r.student,):
            self._show_selected()

    def _on_done(self, results: list[StudentResult]) -> None:
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
        self._expand_only(student)
        self._mark_shown_test(r, test)

        self._set_text(self.info, info_text(r, test))
        if test is None:
            self._show_without_output(r)
            return
        if test.expected is None:
            rows = align("", test.actual)
            self._fill_outputs(
                [Cell("(no expected.txt for this test)", MARKER)],
                [row.actual for row in rows],
            )
            return
        rows = align(test.expected, test.actual, test.compare_lines)
        self._fill_outputs([row.expected for row in rows], [row.actual for row in rows])

    def _show_without_output(self, r: StudentResult) -> None:
        """The student's code never ran (e.g. compile error): expected output on the left."""
        tests = self.assignment.tests if self.assignment else []
        expected = read_expected(tests[0].expected_path) if tests else None
        limit = self.assignment.compare_lines if self.assignment else None
        left = [
            Cell(line, UNCHECKED if limit and i > limit else SAME, i)
            for i, line in enumerate(split_lines(expected or ""), 1)
        ]
        self._fill_outputs(left, [Cell(f"(no output: {r.status})", MARKER)])

    def _expand_only(self, student: str) -> None:
        """Show the test rows of ``student`` and hide everyone else's."""
        for row in self.students.get_children():
            self.students.item(row, open=row == student)

    def _mark_shown_test(self, r: StudentResult, test: TestResult | None) -> None:
        """Bold the test row being compared, and name that test above the outputs."""
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
            text=f"Test case: {test.name}  ({test.status})",
            foreground=PASS_COLOR if test.passed else FAIL_COLOR,
        )

    def _fill_outputs(self, left: list[Cell], right: list[Cell]) -> None:
        for text, cells in ((self.expected_text, left), (self.actual_text, right)):
            text.configure(state="normal")
            text.delete("1.0", "end")
            for cell in cells:
                number = f"{cell.number:>3}  " if cell.number is not None else "     "
                text.insert("end", number, ("lineno", cell.kind))
                body = "" if cell.text is None else cell.text
                if cell.kind in (SAME, DIFF, EXTRA_BLANK, UNCHECKED):
                    body = show_whitespace(body)
                # Tagging the newline too colors the line all the way across.
                text.insert("end", body + "\n", (cell.kind,))
            text.configure(state="disabled")
        self.expected_text.yview_moveto(0)
        self.actual_text.yview_moveto(0)

    def _clear_details(self) -> None:
        self.shown_student = None
        self._set_text(self.info, "")
        self._fill_outputs([], [])
        self.shown_test = None
        self.test_heading.configure(text="")

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
        if busy:
            self.progress.configure(value=0)
        self.status_var.set(status)


def main() -> None:
    GraderApp().mainloop()


if __name__ == "__main__":
    main()
