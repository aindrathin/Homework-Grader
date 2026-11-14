from homework_grader.settings import load_settings, save_settings


def test_round_trip(tmp_path):
    path = tmp_path / "sub" / "settings.json"
    saved = {"assignment": "DiceRoller", "submissions": r"C:\exports\dice.zip"}
    save_settings(saved, path)
    assert load_settings(path) == saved


def test_missing_file_gives_empty(tmp_path):
    assert load_settings(tmp_path / "nope.json") == {}


def test_bad_file_gives_empty(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert load_settings(path) == {}
    path.write_text('["a list"]', encoding="utf-8")
    assert load_settings(path) == {}


def test_non_string_values_dropped(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"assignment": "Song", "submissions": 5}', encoding="utf-8")
    assert load_settings(path) == {"assignment": "Song"}
