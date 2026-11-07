"""A simple desktop window (tkinter, included with Python) for running the grader."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .assignment import load_assignment
from .grading import StudentResult, generate_expected, grade_all
from .report import describe_student, write_csv
from .submissions import find_submissions, open_submissions

PASS_COLOR = "#1b7f3b"
FAIL_COLOR = "#b3261e"
ERROR_COLOR = "#9a6700"

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


class GraderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Homework Grader")
        self.geometry("1100x720")
        self.minsize(800, 500)

        self.assignment_var = tk.StringVar()
        self.submissions_var = tk.StringVar()
        self.assignments: dict[str, Path] = {}
        self.status_var = tk.StringVar(value="Choose an assignment and the submissions.")
        self.results: dict[str, StudentResult] = {}
        self.order: list[str] = []
        self.test_names: list[str] = []
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

        panes = ttk.PanedWindow(self, orient="vertical")
        panes.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        table_frame = ttk.Frame(panes)
        self.table = ttk.Treeview(table_frame, show="headings", selectmode="browse")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=yscroll.set)
        self.table.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        self.table.tag_configure("pass", foreground=PASS_COLOR)
        self.table.tag_configure("fail", foreground=FAIL_COLOR)
        self.table.tag_configure("error", foreground=ERROR_COLOR)
        self.table.bind("<<TreeviewSelect>>", self._show_selected)
        panes.add(table_frame, weight=1)

        detail_frame = ttk.Frame(panes)
        self.detail = tk.Text(detail_frame, wrap="none", font=("Consolas", 10), state="disabled")
        dy = ttk.Scrollbar(detail_frame, orient="vertical", command=self.detail.yview)
        dx = ttk.Scrollbar(detail_frame, orient="horizontal", command=self.detail.xview)
        self.detail.configure(yscrollcommand=dy.set, xscrollcommand=dx.set)
        dy.pack(side="right", fill="y")
        dx.pack(side="bottom", fill="x")
        self.detail.pack(side="left", fill="both", expand=True)
        panes.add(detail_frame, weight=1)

        self._set_columns([])

    def _set_columns(self, test_names: list[str]) -> None:
        self.test_names = test_names
        cols = ["student", "version", "result", *(f"t{i}" for i in range(len(test_names)))]
        self.table.configure(columns=cols)
        for col, title, width in (
            ("student", "Student", 220),
            ("version", "Version", 110),
            ("result", "Result", 140),
        ):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, anchor="w")
        for i, name in enumerate(test_names):
            self.table.heading(f"t{i}", text=name)
            self.table.column(f"t{i}", width=110, anchor="center")

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

        self.results.clear()
        self.order.clear()
        self.table.delete(*self.table.get_children())
        self._set_columns([t.name for t in assignment.tests])
        self._show_text("")
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
            self.table.insert(
                "", "end", iid=s.student, values=(s.student, s.version or "", "waiting…")
            )
        self.progress.configure(maximum=max(1, len(subs)), value=0)
        self.status_var.set(f"Grading {len(subs)} students…")

    def _on_result(self, r: StudentResult) -> None:
        self.results[r.student] = r
        by_name = {t.name: t.status for t in r.tests}
        values = (
            r.student,
            r.version or "",
            r.summary,
            *(by_name.get(n, "") for n in self.test_names),
        )
        tag = "pass" if r.all_passed else ("fail" if r.status == "GRADED" else "error")
        self.table.item(r.student, values=values, tags=(tag,))
        self.progress.step(1)
        if self.table.selection() == (r.student,):
            self._show_selected()

    def _on_done(self, results: list[StudentResult]) -> None:
        full = sum(r.all_passed for r in results)
        self._set_busy(False, f"Done. {full} of {len(results)} students passed every test.")

    def _on_messages(self, messages: list[str]) -> None:
        self._show_text("\n".join(messages))
        self._set_busy(False, "Finished generating expected output.")

    def _on_error(self, message: str) -> None:
        self._set_busy(False, "Stopped because of an error.")
        messagebox.showerror("Error", message)

    # ----------------------------------------------------------------- helpers
    def _show_selected(self, _event=None) -> None:
        sel = self.table.selection()
        if sel and sel[0] in self.results:
            self._show_text(describe_student(self.results[sel[0]]))

    def _show_text(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

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
