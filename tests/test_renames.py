"""Tests for matching a student's class name to the one the assignment needs."""

from pathlib import Path

from homework_grader.grading import find_renames


def _files(*names: str) -> dict[str, Path]:
    return {n: Path(f"{n}.java") for n in names}


def test_renames_similar_names():
    assert find_renames(["Song"], _files("SongNew")) == {"SongNew": "Song"}
    assert find_renames(["Song"], _files("song")) == {"song": "Song"}
    assert find_renames(["Song"], _files("Songshs")) == {"Songshs": "Song"}
    assert find_renames(["Gradanator"], _files("Gradenator")) == {"Gradenator": "Gradanator"}


def test_no_rename_when_present_or_unrelated():
    assert find_renames(["Song"], _files("Song", "SongHelper")) == {}
    assert find_renames(["Song"], _files("Asdf")) == {}


def test_no_rename_when_ambiguous():
    assert find_renames(["Song"], _files("SongA", "SongB")) == {}


def test_exact_case_match_wins_over_other_candidates():
    assert find_renames(["Song"], _files("song", "SongNew")) == {"song": "Song"}


def test_required_classes_are_not_used_as_candidates():
    assert find_renames(["Song", "SongHelper"], _files("SongHelper")) == {}
