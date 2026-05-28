import json
from pathlib import Path

from roibang_v2.workflows.site_handsel import build_site_handsel_plan
from roibang_v2.workflows.site_handsel import run_site_handsel_request


def test_build_site_handsel_plan_chunks_targets_and_stays_dry_run(tmp_path: Path):
    targets = [str(1000 + index) for index in range(21)]
    target_file = tmp_path / "targets.txt"
    target_file.write_text("\n".join(targets[10:]), encoding="utf-8")

    result = build_site_handsel_plan(
        {
            "site_handsel": {
                "source_advertiser_id": "1866125087858183",
                "site_id": "7643710255184904243",
                "target_advertiser_ids": ",".join(targets[:10]),
                "target_accounts_path": str(target_file),
            }
        }
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["summary"]["target_count"] == 21
    assert result["summary"]["batch_count"] == 2
    assert [len(item["payload"]["target_advertiser_ids"]) for item in result["requests"]] == [20, 1]


def test_run_site_handsel_request_executes_and_writes_artifact(tmp_path: Path):
    calls = []

    def fake_transport(request):
        calls.append(request)
        return {
            "code": 0,
            "message": "OK",
            "data": {
                "success_list": [
                    {
                        "origin_site_id": "7643710255184904243",
                        "target_advertiser_id": "2001",
                        "site_id": "9001",
                    }
                ],
                "error_list": [
                    {
                        "origin_site_id": "7643710255184904243",
                        "target_advertiser_id": "2002",
                        "error_reason": "no permission",
                    }
                ],
            },
        }

    result = run_site_handsel_request(
        {
            "site_handsel": {
                "source_advertiser_id": "1866125087858183",
                "site_id": "7643710255184904243",
                "target_advertiser_ids": ["2001", "2002"],
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
    assert calls[0]["operation"] == "handsel_site"
    assert calls[0]["endpoint"] == "/open_api/2/tools/site/handsel/"
    assert json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "site_handsel"


def test_run_site_handsel_request_blocks_missing_required_fields(tmp_path: Path):
    result = run_site_handsel_request(
        {"site_handsel": {"source_advertiser_id": "186"}},
        config={},
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "missing site_id" in result["blocking_reasons"]
    assert "missing target_advertiser_ids" in result["blocking_reasons"]
