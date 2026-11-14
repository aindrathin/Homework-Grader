"""Tests for what the window saves between runs: code edits, notes, and the last grading."""

from pathlib import Path

from homework_grader import grading
from homework_grader.grading import FAIL, GRADED, PASS, StudentResult
from homework_grader.saved_state import SavedEdits, SavedSession, StudentNotes, fingerprint
from homework_grader.submissions import Submission


def test_edits_saved_per_version(tmp_path):
    path = tmp_path / "edits.json"
    SavedEdits(path).set("key", "Sam", "Version 2", {"Main": "class Main {}"})

    edits = SavedEdits(path)  # a fresh load, like reopening the window
    assert edits.get("key", "Sam", "Version 2") == {"Main": "class Main {}"}
    assert edits.get("key", "Sam", "Version 1") == {}
    assert edits.get("other", "Sam", "Version 2") == {}


def test_clearing_edits_removes_them(tmp_path):
    path = tmp_path / "edits.json"
    edits = SavedEdits(path)
    edits.set("key", "Sam", None, {"Main": "x"})
    edits.set("key", "Sam", None, {})
    assert SavedEdits(path).data == {}


def test_edits_to_older_versions_are_dropped(tmp_path):
    path = tmp_path / "edits.json"
    edits = SavedEdits(path)
    edits.set("key", "Sam", "Version 1", {"Main": "old"})
    edits.set("key", "Ana", "Version 1", {"Main": "kept"})
    edits.keep_versions("key", {"Sam": "Version 2", "Ana": "Version 1"})

    reloaded = SavedEdits(path)
    assert reloaded.get("key", "Sam", "Version 1") == {}
    assert reloaded.get("key", "Ana", "Version 1") == {"Main": "kept"}


def test_bad_files_load_empty(tmp_path):
    for name in ("edits.json", "notes.json"):
        (tmp_path / name).write_text("not json", encoding="utf-8")
    assert SavedEdits(tmp_path / "edits.json").get("k", "Sam", None) == {}
    assert StudentNotes(tmp_path / "notes.json").get("Song", "Sam") == ""
    (tmp_path / "session.json").write_text('{"format": 1}', encoding="utf-8")
    assert SavedSession(tmp_path / "session.json").load() is None


def test_notes_saved_per_assignment(tmp_path):
    path = tmp_path / "notes.json"
    StudentNotes(path).set("Song", "Sam", "Asked for help with loops.")

    notes = StudentNotes(path)
    assert notes.get("Song", "Sam") == "Asked for help with loops."
    assert notes.get("DiceRoller", "Sam") == ""
    notes.set("Song", "Sam", "  \n")  # a blank note is removed
    assert StudentNotes(path).data == {}


def test_session_round_trip(tmp_path):
    sub = Submission("Sam", "Version 1", {"Main": Path("x/Main 1.java")}, ["note"], {"Main": "src"})
    tests = [
        grading.TestResult("t1", PASS, 7, "hi\n", "hi\n", input="5\n", input_reads=[(3, "5\n")]),
        grading.TestResult("t2", FAIL, None, None, "x", manual=True),
    ]
    result = StudentResult(
        "Sam",
        "Version 1",
        GRADED,
        tests,
        edited=["Main"],
        edited_sources={"Main": "edited"},
        expected_reads={"t1": [(3, "5\n")]},
    )
    session = SavedSession(tmp_path / "session.json")
    session.save("Song", tmp_path / "subs.zip", "abc", [sub], [result])

    loaded = SavedSession(tmp_path / "session.json").load()
    assert loaded is not None
    assert loaded["assignment"] == "Song"
    assert loaded["submissions"] == tmp_path / "subs.zip"
    assert loaded["fingerprint"] == "abc"
    assert loaded["submissions_list"] == [sub]
    r = loaded["results"][0]
    assert r.tests[0].input_reads == [(3, "5\n")]
    assert r.expected_reads == {"t1": [(3, "5\n")]}
    assert r.edited_sources == {"Main": "edited"}
    assert not r.tests[1].manual  # manual passes come from their own file
    r.tests[1].manual = True
    assert r == result

    session.clear()
    assert session.load() is None


def test_fingerprint_notices_changes(tmp_path):
    assignment = tmp_path / "Song"
    (assignment / "tests" / "t1").mkdir(parents=True)
    expected = assignment / "tests" / "t1" / "expected.txt"
    expected.write_text("a", encoding="utf-8")
    subs = tmp_path / "subs"
    (subs / "Sam" / "Version 1").mkdir(parents=True)
    java = subs / "Sam" / "Version 1" / "Song.java"
    java.write_text("class Song {}", encoding="utf-8")

    first = fingerprint(assignment, subs)
    assert fingerprint(assignment, subs) == first
    expected.write_text("b", encoding="utf-8")
    second = fingerprint(assignment, subs)
    assert second != first
    java.write_text("class Song { int x; }", encoding="utf-8")
    assert fingerprint(assignment, subs) != second
