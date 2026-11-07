import zipfile
from pathlib import Path

from homework_grader.submissions import find_submissions, open_submissions


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_latest_version_by_number(tmp_path: Path):
    work = tmp_path / "submittedWork"
    _write(work / "Sam" / "Version 2" / "Main.java", "public class Main {} // v2")
    _write(work / "Sam" / "Version 10" / "Main.java", "public class Main {} // v10")
    [sub] = find_submissions(tmp_path)
    assert sub.version == "Version 10"
    assert "v10" in sub.files["Main"].read_text()


def test_teams_renamed_file_matched_by_class(tmp_path: Path):
    work = tmp_path / "submittedWork"
    _write(work / "Sam" / "Version 3" / "Main 2.java", "public class Main {}")
    _write(work / "Sam" / "Version 3" / "Helper (1).java", "class Helper {}")
    [sub] = find_submissions(tmp_path)
    assert set(sub.files) == {"Main", "Helper"}


def test_duplicate_class_uses_highest_teams_number(tmp_path: Path):
    v = tmp_path / "submittedWork" / "Sam" / "Version 1"
    _write(v / "Main.java", "public class Main {} // old")
    _write(v / "Main 1.java", "public class Main {} // new")
    [sub] = find_submissions(tmp_path)
    assert sub.files["Main"].name == "Main 1.java"
    assert any("define Main" in n for n in sub.notes)


def test_class_name_ignores_comments(tmp_path: Path):
    v = tmp_path / "submittedWork" / "Sam" / "Version 1"
    _write(v / "Point3.java", "// public class Wrong\npublic final class Point3 {}")
    [sub] = find_submissions(tmp_path)
    assert set(sub.files) == {"Point3"}


def test_zip_with_nested_submitted_work(tmp_path: Path):
    zpath = tmp_path / "export.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("Class Export/submittedWork/Ana/Version 1/Main.java", "public class Main {}")
        zf.writestr("Class Export/submittedWork/Ben/Version 1/notes.txt", "no java")
    with open_submissions(zpath) as root:
        subs = find_submissions(root)
        assert [s.student for s in subs] == ["Ana", "Ben"]
        assert subs[1].files == {}
