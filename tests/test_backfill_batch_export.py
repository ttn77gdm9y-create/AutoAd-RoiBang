import importlib.util
import json
from pathlib import Path

from roibang_v2.backfill.batches import export_batch_request


def _load_export_script():
    script_path = Path("scripts/export_backfill_batch_request.py")
    spec = importlib.util.spec_from_file_location("export_backfill_batch_request", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_plan(path: Path):
    path.write_text(
        json.dumps(
            {
                "workflow": "report_backfill_batch_plan",
                "batches": [
                    {
                        "batch_id": "batch_0001",
                        "planned_request_count": 4,
                        "report_fetch_request": {
                            "report_fetch": {
                                "mode": "backfill",
                                "source": "openapi_http_execute",
                                "batch_id": "batch_0001",
                                "account_ids": ["1858371222574218"],
                                "date_range": {"start": "2026-02-10", "end": "2026-02-11"},
                                "openapi": {
                                    "endpoints": ["report_custom", "operation_log_search"],
                                    "report_presets": ["promotion_daily"],
                                    "page_size": 100,
                                },
                                "openapi_http": {"enabled": False},
                                "execution": {"status": "planned_only", "external_api_enabled": False},
                            }
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_export_batch_request_writes_disabled_request_file(tmp_path):
    plan_path = tmp_path / "plan.json"
    output_dir = tmp_path / "requests"
    _write_plan(plan_path)

    result = export_batch_request(plan_path=plan_path, batch_id="batch_0001", output_dir=output_dir)
    payload = json.loads(Path(result["output_path"]).read_text(encoding="utf-8"))

    assert result == {
        "ok": True,
        "workflow": "backfill_batch_request_export",
        "batch_id": "batch_0001",
        "execution_enabled": False,
        "external_api_calls": 0,
        "output_path": str(output_dir / "batch_0001.report-fetch.json"),
        "summary": {
            "planned_request_count": 4,
            "account_count": 1,
            "date_range": {"start": "2026-02-10", "end": "2026-02-11"},
        },
    }
    assert payload["report_fetch"]["source"] == "openapi_http_execute"
    assert payload["report_fetch"]["execution"] == {"status": "planned_only", "external_api_enabled": False}
    assert payload["report_fetch"]["openapi_http"]["enabled"] is False


def test_export_batch_request_rejects_missing_batch(tmp_path):
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)

    try:
        export_batch_request(plan_path=plan_path, batch_id="batch_9999", output_dir=tmp_path / "requests")
    except ValueError as exc:
        assert "batch_9999" in str(exc)
    else:
        raise AssertionError("missing batch should raise")


def test_export_backfill_batch_request_cli_prints_summary(tmp_path, capsys):
    plan_path = tmp_path / "plan.json"
    output_dir = tmp_path / "requests"
    _write_plan(plan_path)
    module = _load_export_script()

    exit_code = module.export_from_args(
        [
            "--plan",
            str(plan_path),
            "--batch-id",
            "batch_0001",
            "--output-dir",
            str(output_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"workflow": "backfill_batch_request_export"' in captured.out
    assert '"batch_id": "batch_0001"' in captured.out
    assert '"openapi_http"' not in captured.out
