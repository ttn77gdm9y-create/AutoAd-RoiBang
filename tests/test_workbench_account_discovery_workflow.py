import json
import importlib.util
from datetime import date
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.workbench_account_discovery import (
    build_workbench_account_discovery_preflight,
    run_workbench_account_discovery_request,
)


def _write_accounts_csv(path: Path):
    path.write_text(
        "\n".join(
            [
                "account_name,advertiser_id,消耗,product,platform",
                "黑旗-勇者突进-微小-傲星-306,1858371222574218,\"570,011.13\",勇者突进,WECHAT_GAME",
                "黑旗-勇者突进-微小-傲星-153,1856647523922953,\"549,533.67\",勇者突进,WECHAT_GAME",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_session(path: Path):
    path.write_text(
        json.dumps(
            {
                "cookie": "sessionid=secret-session",
                "csrf_token": "secret-csrf-token",
                "ebpid": "1851650746645060",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _request(csv_path: Path, session_path: Path, audit_dir: Path) -> dict:
    return {
        "workbench_account_discovery": {
            "target_date": {"mode": "yesterday"},
            "account_pool_csv": str(csv_path),
            "product": "勇者突进",
            "platforms": ["WECHAT_GAME"],
            "min_spend": 0,
            "workbench": {
                "enabled": True,
                "session_file": str(session_path),
                "keyword": "勇者突进-微小",
                "limit": 100,
                "stop_when_sorted_cost_reaches_zero": True,
                "response_audit_dir": str(audit_dir),
            },
        }
    }


def test_workbench_account_discovery_preflight_counts_pages_without_external_calls(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "session.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _write_session(session_path)

    result = build_workbench_account_discovery_preflight(
        _request(csv_path, session_path, tmp_path / "audit"),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
    )

    assert result["workflow"] == "workbench_account_discovery_preflight"
    assert result["external_api_calls"] == 0
    assert result["summary"] == {
        "target_date": "2026-05-06",
        "candidate_account_count": 2,
        "planned_request_count": 1,
        "min_spend": 0.0,
        "source": "workbench_account_list",
    }
    assert Path(result["artifact_path"]).exists()


def test_workbench_account_discovery_workflow_writes_discovery_artifact(tmp_path):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "session.json"
    audit_dir = tmp_path / "audit"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _write_session(session_path)

    def opener(_url, _body, _headers, _timeout_seconds):
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "advertiser_id": "1858371222574218",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-306",
                            "metrics": {"stat_cost": "1,252.22"},
                        },
                        {
                            "advertiser_id": "outside-pool",
                            "advertiser_name": "池外账户",
                            "metrics": {"stat_cost": "999.00"},
                        },
                        {
                            "advertiser_id": "1856647523922953",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-153",
                            "metrics": {"stat_cost": "0.00"},
                        },
                    ],
                    "pagination": {"page": 1, "limit": 100, "total": 3, "hasMore": False},
                },
                "msg": "",
            },
        )

    result = run_workbench_account_discovery_request(
        _request(csv_path, session_path, audit_dir),
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        today=date(2026, 5, 7),
        opener=opener,
    )

    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert result["workflow"] == "workbench_account_discovery"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 1
    assert result["summary"]["active_account_count"] == 1
    assert result["active_account_ids"] == ["1858371222574218"]
    assert artifact["accounts"][0]["stat_cost"] == 1252.22
    assert "secret-session" not in (audit_dir / "workbench_account_list.jsonl").read_text(encoding="utf-8")


def test_workbench_account_discovery_cli_can_temporarily_enable_readonly_without_editing_request(
    tmp_path: Path,
    capsys,
):
    db_path = tmp_path / "roibang.sqlite3"
    csv_path = tmp_path / "accounts.csv"
    session_path = tmp_path / "session.json"
    request_path = tmp_path / "request.json"
    runtime_path = tmp_path / "runtime.json"
    bootstrap_database(db_path)
    _write_accounts_csv(csv_path)
    _write_session(session_path)
    payload = _request(csv_path, session_path, tmp_path / "audit")
    payload["workbench_account_discovery"]["workbench"]["enabled"] = False
    request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(db_path),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": True,
                "execution_enabled": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script_path = Path("scripts/run_workbench_account_discovery.py")
    spec = importlib.util.spec_from_file_location("run_workbench_account_discovery", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    def opener(_url, _body, _headers, _timeout_seconds):
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "advertiser_id": "1858371222574218",
                            "advertiser_name": "黑旗-勇者突进-微小-傲星-306",
                            "metrics": {"stat_cost": "88.00"},
                        }
                    ],
                    "pagination": {"page": 1, "limit": 100, "total": 1, "hasMore": False},
                },
            },
        )

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--request",
            str(request_path),
            "--enable-readonly",
        ],
        opener=opener,
        today=date(2026, 5, 7),
    )

    captured = capsys.readouterr()
    original_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert '"workflow": "workbench_account_discovery"' in captured.out
    assert '"active_account_count": 1' in captured.out
    assert original_request["workbench_account_discovery"]["workbench"]["enabled"] is False
