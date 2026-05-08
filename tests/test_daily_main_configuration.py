import json
from pathlib import Path


def test_workbench_daily_pipeline_template_excludes_material_daily_from_main_path():
    payload = json.loads(Path("configs/daily-report-pipeline.workbench-discovery.disabled.example.json").read_text())
    pipeline = payload["daily_report_pipeline"]

    assert pipeline["active_account_discovery"]["source"] == "workbench_account_list"
    assert pipeline["report_fetch"]["openapi"]["report_presets"] == ["promotion_daily"]
    assert "material_daily" not in pipeline["report_fetch"]["openapi"]["report_presets"]


def test_scheduler_runs_field_catalog_before_daily_pipeline_and_uses_main_daily_template():
    payload = json.loads(Path("configs/scheduler/roibang-v2.jobs.example.json").read_text())
    jobs = payload["jobs"]
    job_ids = [job["id"] for job in jobs]

    assert job_ids.index("roibang-report-field-catalog") < job_ids.index("roibang-daily-report-pipeline")
    field_job = next(job for job in jobs if job["id"] == "roibang-report-field-catalog")
    daily_job = next(job for job in jobs if job["id"] == "roibang-daily-report-pipeline")
    assert field_job["script"]["path"] == "scripts/run_report_field_catalog.py"
    assert field_job["category"] == "report_field_catalog"
    assert daily_job["script"]["args"] == [
        "--config",
        "configs/runtime.example.json",
        "--request",
        "configs/daily-report-pipeline.workbench-discovery.disabled.example.json",
    ]


def test_material_daily_has_separate_disabled_fetch_template():
    payload = json.loads(Path("configs/report-fetch.material-daily.disabled.example.json").read_text())
    report_fetch = payload["report_fetch"]

    assert report_fetch["openapi"]["report_presets"] == ["material_daily"]
    assert report_fetch["openapi"]["page_size"] == 20
    assert report_fetch["openapi_http"]["enabled"] is False
    assert report_fetch["execution"]["external_api_enabled"] is False
