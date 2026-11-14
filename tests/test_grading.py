"""End-to-end tests that compile and run real Java. They need a JDK."""

import subprocess
from pathlib import Path

import pytest

from homework_grader.assignment import load_assignment
from homework_grader.grading import (
    COMPILE_ERROR,
    FAIL,
    MISSING_CLASSES,
    PASS,
    RUNTIME_ERROR,
    TIMEOUT,
    JavaNotFoundError,
    find_java_tool,
    generate_expected,
    grade_submission,
    reference_reads,
)
from homework_grader.submissions import Submission

try:
    find_java_tool("javac")
except JavaNotFoundError:
    pytest.skip("JDK not installed", allow_module_level=True)

REFERENCE = """
import java.util.Scanner;
public class Roller {
    public static void main(String[] args) {
        Scanner in = new Scanner(System.in);
        System.out.print("How many? ");
        int n = in.nextInt();
        for (int i = 0; i < n; i++) System.out.println((int) (Math.random() * 6) + 1);
        System.out.println(Helper.done());
    }
}
"""
HELPER = 'public class Helper { static String done() { return "done"; } }'


def _assignment(tmp_path: Path, timeout: float = 5) -> Path:
    root = tmp_path / "Roller"
    (root / "reference").mkdir(parents=True)
    (root / "reference" / "Roller.java").write_text(REFERENCE)
    (root / "reference" / "Helper.java").write_text(HELPER)
    (root / "assignment.toml").write_text(
        f'main_class = "Roller"\ntimeout_seconds = {timeout}\nrequired_classes = ["Helper"]\n'
    )
    for name, n, seed in (("a", 3, 42), ("b", 5, 7)):
        t = root / "tests" / name
        t.mkdir(parents=True)
        (t / "input.txt").write_text(f"{n}\n")
        (t / "seed.txt").write_text(str(seed))
    return root


def _student(tmp_path: Path, main_src: str, helper_src: str = HELPER) -> Submission:
    folder = tmp_path / "student"
    folder.mkdir(exist_ok=True)
    (folder / "Roller.java").write_text(main_src)
    (folder / "Helper.java").write_text(helper_src)
    return Submission(
        "Sam", "Version 1", {"Roller": folder / "Roller.java", "Helper": folder / "Helper.java"}
    )


@pytest.fixture
def assignment(tmp_path: Path):
    root = _assignment(tmp_path)
    a = load_assignment(root)
    messages = generate_expected(a)
    assert all("wrote expected.txt" in m for m in messages), messages
    return a


def test_reference_passes_its_own_tests(tmp_path, assignment):
    r = grade_submission(assignment, _student(tmp_path, REFERENCE))
    assert [t.status for t in r.tests] == [PASS, PASS]


def test_input_is_recorded_where_it_was_read(tmp_path, assignment):
    r = grade_submission(assignment, _student(tmp_path, REFERENCE))
    t = r.tests[0]
    assert t.input_reads == [(len("How many? "), "3\n")]
    # The output itself has no input in it: the first die roll follows the prompt.
    assert t.actual.startswith("How many? ") and t.actual[10] in "123456"


def test_reference_reads_are_found_for_the_expected_side(assignment):
    assert reference_reads(assignment) == {
        "a": [(len("How many? "), "3\n")],
        "b": [(len("How many? "), "5\n")],
    }


def test_errors_do_not_mention_the_launcher(tmp_path, assignment):
    src = REFERENCE.replace("int n = in.nextInt();", "int n = in.nextInt(); n = 1 / 0;")
    r = grade_submission(assignment, _student(tmp_path, src))
    err = r.tests[0].stderr
    assert "ArithmeticException" in err and "at Roller.main" in err
    assert "Launcher" not in err and "reflect" not in err


def test_different_seeds_give_different_expected_output(assignment):
    a, b = (t.expected_path.read_text() for t in assignment.tests)
    assert a != b


def test_seeded_random_object_matches_math_random(tmp_path, assignment):
    src = REFERENCE.replace("(int) (Math.random() * 6)", "(int) (rng.nextDouble() * 6)").replace(
        "Scanner in =", "java.util.Random rng = new java.util.Random(99); Scanner in ="
    )
    r = grade_submission(assignment, _student(tmp_path, src))
    assert [t.status for t in r.tests] == [PASS, PASS]


def test_expected_file_reproducible_by_hand(tmp_path, assignment):
    """Without the grader, a student using new Random(42).nextDouble() gets exactly expected.txt."""
    test = assignment.tests[0]
    assert test.seed == 42
    manual = tmp_path / "manual"
    manual.mkdir()
    (manual / "Roller.java").write_text(
        REFERENCE.replace("(int) (Math.random() * 6)", "(int) (r.nextDouble() * 6)").replace(
            "Scanner in =", "java.util.Random r = new java.util.Random(42); Scanner in ="
        )
    )
    (manual / "Helper.java").write_text(HELPER)
    subprocess.run([find_java_tool("javac"), "Roller.java", "Helper.java"], cwd=manual, check=True)
    out = (
        subprocess.run(
            [find_java_tool("java"), "-cp", ".", "Roller"],
            cwd=manual,
            input=b"3\n",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .replace("\r\n", "\n")
    )
    assert out == test.expected_path.read_text()


def test_wrong_output_fails_exactly(tmp_path, assignment):
    r = grade_submission(
        assignment, _student(tmp_path, REFERENCE.replace('"How many? "', '"How many?"'))
    )
    assert {t.status for t in r.tests} == {FAIL}


def test_compile_error(tmp_path, assignment):
    r = grade_submission(assignment, _student(tmp_path, "public class Roller { oops }"))
    assert r.status == COMPILE_ERROR
    assert "Roller.java" in r.compile_output


def test_missing_required_class(tmp_path, assignment):
    folder = tmp_path / "s"
    folder.mkdir()
    (folder / "Roller.java").write_text(REFERENCE)
    r = grade_submission(assignment, Submission("Sam", None, {"Roller": folder / "Roller.java"}))
    assert r.status == MISSING_CLASSES


def test_runtime_error_when_input_runs_out(tmp_path, assignment):
    src = REFERENCE.replace("int n = in.nextInt();", "int n = in.nextInt(); in.nextInt();")
    r = grade_submission(assignment, _student(tmp_path, src))
    assert {t.status for t in r.tests} == {RUNTIME_ERROR}
    assert "NoSuchElementException" in r.tests[0].stderr


def test_infinite_loop_times_out(tmp_path):
    root = _assignment(tmp_path, timeout=1)
    a = load_assignment(root)
    generate_expected(a)
    src = REFERENCE.replace("int n = in.nextInt();", "int n = in.nextInt(); while (n > -1) {}")
    r = grade_submission(a, _student(tmp_path, src))
    assert {t.status for t in r.tests} == {TIMEOUT}


# --- compare_lines, using the real Song assignment ---------------------------

SONG = Path(__file__).resolve().parents[1] / "assignments" / "Song"


def _song_student(tmp_path: Path, src: str) -> Submission:
    folder = tmp_path / "song_student"
    folder.mkdir(exist_ok=True)
    (folder / "Song.java").write_text(src)
    return Submission("Sam", "Version 1", {"Song": folder / "Song.java"})


@pytest.mark.parametrize(
    ("change", "status"),
    [
        (lambda s: s, PASS),
        (lambda s: s.replace('"Pig goes oink, oink,"', '"Cow goes moo, moo,"'), PASS),
        (lambda s: s.replace("        pigVerse();\n", ""), PASS),
        (lambda s: s.replace('"Duck goes quack, quack,"', '"Duck goes quack quack,"'), FAIL),
        (
            lambda s: s.replace(
                "        duckVerse();\n        System.out.println();", "        duckVerse();"
            ),
            FAIL,
        ),
    ],
    ids=["reference", "own-verse-6", "no-verse-6", "typo-in-verse-3-5", "missing-blank-line"],
)
def test_song_checks_only_first_five_verses(tmp_path, change, status):
    a = load_assignment(SONG)
    assert a.compare_lines == 29
    src = change((SONG / "reference" / "Song.java").read_text())
    r = grade_submission(a, _song_student(tmp_path, src))
    assert [t.status for t in r.tests] == [status]


# --- the real Gradanator assignment ------------------------------------------

GRADANATOR = Path(__file__).resolve().parents[1] / "assignments" / "Gradanator"
GRADANATOR_TESTS = [
    "1-normal",
    "2-premature-rounding",
    "3-homework-extra-credit-cap",
    "4-section-attendance-cap",
    "5-exam-cap-and-shift",
    "6-grade-boundary-60",
]


def _gradanator_student(tmp_path: Path, src: str) -> Submission:
    folder = tmp_path / "gradanator_student"
    folder.mkdir(exist_ok=True)
    (folder / "Gradanator.java").write_text(src)
    return Submission("Sam", "Version 1", {"Gradanator": folder / "Gradanator.java"})


@pytest.mark.parametrize(
    ("change", "failing"),
    [
        (lambda s: s, set()),
        (lambda s: s.replace("Excellent work, keep it up!", "Wow!"), set()),
        (
            lambda s: s.replace(
                "double weighted = (double) earned / possible * weight;",
                "double weighted = Math.round((double) earned / possible * weight * 10) / 10.0;",
            ),
            {"2-premature-rounding"},
        ),
        (lambda s: s.replace("earned = Math.min(earned, possible);", ""), {GRADANATOR_TESTS[2]}),
        (
            lambda s: s.replace(
                "Math.min(console.nextInt() * POINTS_PER_SECTION, SECTION_MAX)",
                "console.nextInt() * POINTS_PER_SECTION",
            ),
            {"4-section-attendance-cap"},
        ),
        (
            lambda s: s.replace("score = Math.min(score, EXAM_MAX);", ""),
            {"1-normal", "5-exam-cap-and-shift"},
        ),
        (lambda s: s.replace("percentage >= 60", "percentage > 60"), {"6-grade-boundary-60"}),
        (lambda s: s.replace('"Homework:"', '"Homework"'), set(GRADANATOR_TESTS)),
    ],
    ids=[
        "reference",
        "own-message",
        "premature-rounding",
        "no-homework-cap",
        "no-section-cap",
        "no-exam-cap",
        "boundary-off-by-one",
        "homework-no-colon",
    ],
)
def test_gradanator_catches_mistakes(tmp_path, change, failing):
    a = load_assignment(GRADANATOR)
    assert [t.name for t in a.tests] == GRADANATOR_TESTS
    assert a.compare_lines == 18
    src = (GRADANATOR / "reference" / "Gradanator.java").read_text()
    changed = change(src)
    assert changed != src or not failing
    r = grade_submission(a, _gradanator_student(tmp_path, changed))
    assert {t.name for t in r.tests if t.status != PASS} == failing
    assert {t.status for t in r.tests if t.status != PASS} <= {FAIL}


@pytest.mark.parametrize("student_class", ["SongNew", "song", "Songshs"])
def test_similar_class_name_is_renamed_for_grading(tmp_path, student_class):
    a = load_assignment(SONG)
    src = (SONG / "reference" / "Song.java").read_text().replace("Song", student_class)
    original = tmp_path / f"{student_class} 1.java"
    original.write_text(src)
    sub = Submission("Sam", "Version 1", {student_class: original})
    r = grade_submission(a, sub)
    assert [t.status for t in r.tests] == [PASS]
    assert r.renamed == {student_class: "Song"}
    assert r.summary == "1/1 passed (renamed)"
    assert any(f"Renamed class {student_class} to Song" in n for n in r.notes)
    assert original.read_text() == src  # the student's file is never edited
