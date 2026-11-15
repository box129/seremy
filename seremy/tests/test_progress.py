import json

from seremy.progress import milestone, report_progress


def test_progress_publication_is_atomic_and_validation_order_is_monotonic(tmp_path, monkeypatch):
    path = tmp_path / "progress.json"
    monkeypatch.setenv("SEREMY_PROGRESS_FILE", str(path))
    values = []
    for stage in ("Preparing repository", "S01 · snapshot", "S02 · parsing", "S03 · binding",
                  "S04 · framework evidence", "S05 · structural components", "S06 · relationship views",
                  "S07 · graph validation", "S08 · documentation", "S07 · generated output validation", "Publishing draft"):
        report_progress(stage)
        value = json.loads(path.read_text(encoding="utf8"))
        assert value == milestone(stage)
        values.append(value["progress"])
        assert not path.with_suffix(".pending").exists()
    assert values == sorted(set(values)) and values[-1] < 100
