import json

from roibang_v2.runs import write_latest_artifact
from roibang_v2.runs import write_run_artifact
from roibang_v2.runs import write_snapshot_artifact


def test_write_run_artifact_does_not_overwrite_same_second(monkeypatch, tmp_path):
    monkeypatch.setattr("roibang_v2.runs.utc_timestamp", lambda: "20260513T040729Z")

    first = write_run_artifact(tmp_path, "create_mode", {"value": "first"})
    second = write_run_artifact(tmp_path, "create_mode", {"value": "second"})

    assert first.name == "20260513T040729Z.json"
    assert second.name == "20260513T040729Z-001.json"
    assert json.loads(first.read_text(encoding="utf-8"))["value"] == "first"
    assert json.loads(second.read_text(encoding="utf-8"))["value"] == "second"


def test_write_latest_artifact_replaces_latest_json(tmp_path):
    first = write_latest_artifact(tmp_path, "delivery_business_report", {"value": "first"})
    second = write_latest_artifact(tmp_path, "delivery_business_report", {"value": "second"})

    assert first == second
    assert first.name == "latest.json"
    assert json.loads(first.read_text(encoding="utf-8")) == {"value": "second"}


def test_write_snapshot_artifact_creates_stable_file_and_updates_latest(monkeypatch, tmp_path):
    monkeypatch.setattr("roibang_v2.runs.utc_timestamp", lambda: "20260513T040729Z")

    first = write_snapshot_artifact(tmp_path, "rule_suggestions", {"value": "first"})
    second = write_snapshot_artifact(tmp_path, "rule_suggestions", {"value": "second"})
    latest = tmp_path / "rule_suggestions" / "latest.json"

    assert first.name == "20260513T040729Z.json"
    assert second.name == "20260513T040729Z-001.json"
    assert latest.exists()
    assert json.loads(first.read_text(encoding="utf-8")) == {"value": "first", "artifact_path": str(first)}
    assert json.loads(second.read_text(encoding="utf-8")) == {"value": "second", "artifact_path": str(second)}
    assert json.loads(latest.read_text(encoding="utf-8")) == {"value": "second", "artifact_path": str(second)}
