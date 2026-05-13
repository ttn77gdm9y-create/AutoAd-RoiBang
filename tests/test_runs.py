import json

from roibang_v2.runs import write_run_artifact


def test_write_run_artifact_does_not_overwrite_same_second(monkeypatch, tmp_path):
    monkeypatch.setattr("roibang_v2.runs.utc_timestamp", lambda: "20260513T040729Z")

    first = write_run_artifact(tmp_path, "create_mode", {"value": "first"})
    second = write_run_artifact(tmp_path, "create_mode", {"value": "second"})

    assert first.name == "20260513T040729Z.json"
    assert second.name == "20260513T040729Z-001.json"
    assert json.loads(first.read_text(encoding="utf-8"))["value"] == "first"
    assert json.loads(second.read_text(encoding="utf-8"))["value"] == "second"
