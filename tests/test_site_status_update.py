import json
from pathlib import Path

from roibang_v2.workflows.site_status_update import build_site_status_update_plan
from roibang_v2.workflows.site_status_update import run_site_status_update_request


def test_build_site_status_update_plan_reads_handsel_artifact(tmp_path: Path):
    handsel = tmp_path / "handsel.json"
    handsel.write_text(
        json.dumps(
            {
                "success_list": [
                    {"target_advertiser_id": "2001", "site_id": "9001"},
                    {"target_advertiser_id": "2001", "site_id": "9002"},
                    {"target_advertiser_id": "2002", "site_id": "9003"},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = build_site_status_update_plan({"site_status_update": {"handsel_artifact": str(handsel)}})

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["summary"]["status"] == "delete"
    assert result["summary"]["site_count"] == 3
    assert result["summary"]["advertiser_count"] == 2
    assert result["requests"][0]["operation"] == "update_site_status"
    assert result["requests"][0]["endpoint"] == "/open_api/2/tools/site/update_status/"
    assert result["requests"][0]["payload"] == {
        "advertiser_id": 2001,
        "site_ids": [9001, 9002],
        "status": "delete",
    }


def test_run_site_status_update_request_executes_and_writes_artifact(tmp_path: Path):
    calls = []

    def fake_transport(request):
        calls.append(request)
        return {
            "code": 0,
            "message": "OK",
            "data": {
                "success": ["9001"],
                "fail": [{"site_id": "9002", "message": "Site Not Found"}],
            },
        }

    result = run_site_status_update_request(
        {
            "site_status_update": {
                "advertiser_id": "2001",
                "site_ids": ["9001", "9002"],
                "status": "delete",
                "execute": True,
            }
        },
        config={},
        runs_dir=tmp_path / "runs",
        transport=fake_transport,
    )

    assert result["ok"] is False
    assert result["status"] == "partial"
    assert result["external_api_calls"] == 1
    assert result["summary"]["success_count"] == 1
    assert result["summary"]["error_count"] == 1
    assert calls[0]["payload"] == {"advertiser_id": 2001, "site_ids": [9001, 9002], "status": "delete"}
    assert json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "site_status_update"


def test_run_site_status_update_request_blocks_missing_required_fields(tmp_path: Path):
    result = run_site_status_update_request(
        {"site_status_update": {"status": "delete"}},
        config={},
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "missing site pairs" in result["blocking_reasons"]
