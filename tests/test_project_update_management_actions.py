import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.workflows.project_update_execute import PROJECT_BUDGET_UPDATE_ENDPOINT
from roibang_v2.workflows.project_update_execute import PROJECT_CPA_BID_UPDATE_ENDPOINT
from roibang_v2.workflows.project_update_execute import PROJECT_DELETE_ENDPOINT
from roibang_v2.workflows.project_update_execute import PROJECT_ROI_GOAL_UPDATE_ENDPOINT
from roibang_v2.workflows.project_update_execute import PROJECT_STATUS_UPDATE_ENDPOINT
from roibang_v2.workflows.project_update_execute import run_project_update_execute_request
from roibang_v2.workflows.project_update_preflight import build_project_update_preflight


def _write_allowed_accounts(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "allowed_target_accounts": [
                    {
                        "advertiser_id": "adv-1",
                        "account_name": "黑旗-勇者突进-微小-傲星-153",
                        "product": "勇者突进",
                        "enable": True,
                        "channel": "wx",
                    },
                    {
                        "advertiser_id": "adv-2",
                        "account_name": "黑旗-勇者突进-微小-傲星-170",
                        "product": "勇者突进",
                        "enable": True,
                        "channel": "wx",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _seed_projects(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE projects (
          advertiser_id TEXT NOT NULL,
          project_id TEXT NOT NULL,
          project_name TEXT NOT NULL DEFAULT '',
          PRIMARY KEY (advertiser_id, project_id)
        )
        """
    )
    for advertiser_id, project_id in [
        ("adv-1", "p-status"),
        ("adv-1", "p-budget"),
        ("adv-2", "p-bid"),
        ("adv-2", "p-roi"),
    ]:
        conn.execute(
            "INSERT INTO projects (advertiser_id, project_id, project_name) VALUES (?, ?, ?)",
            (advertiser_id, project_id, f"勇者突进-{project_id}"),
        )
    conn.commit()
    conn.close()


def _project_update(allowlist_path: Path) -> dict:
    return {
        "project_update_id": "project-management-001",
        "operator": "郭靖",
        "allowed_target_accounts_path": str(allowlist_path),
        "execution": {"enabled": False, "status": "planned_only"},
        "actions": [
            {
                "action_type": "status_update",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "p-status",
                "opt_status": "DISABLE",
            },
            {
                "action_type": "budget_update",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "p-budget",
                "budget_mode": "BUDGET_MODE_DAY",
                "budget": 300,
            },
            {
                "action_type": "bid_update",
                "advertiser_id": "adv-2",
                "entity_type": "project",
                "project_id": "p-bid",
                "cpa_bid": 103,
            },
            {
                "action_type": "roi_coeff_update",
                "advertiser_id": "adv-2",
                "entity_type": "project",
                "project_id": "p-roi",
                "roi_goal": 0.41,
            },
        ],
    }


def _preflight(ok: bool = True) -> dict:
    return {
        "ok": ok,
        "workflow": "project_update_preflight",
        "status": "passed" if ok else "failed",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "project_update_id": "project-management-001",
            "action_count": 4,
            "restore_action_count": 0,
        },
        "violations": [] if ok else ["bad preflight"],
    }


def _load_script(name: str):
    script_path = Path("scripts") / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_project_update_preflight_accepts_project_management_actions(tmp_path: Path):
    allowlist_path = tmp_path / "allowed.json"
    db_path = tmp_path / "roibang.sqlite3"
    _write_allowed_accounts(allowlist_path)
    _seed_projects(db_path)

    result = build_project_update_preflight(_project_update(allowlist_path), db_path=db_path)

    assert result["ok"] is True
    assert result["workflow"] == "project_update_preflight"
    assert result["summary"]["action_count"] == 4
    assert result["summary"]["management_action_count"] == 4
    assert result["summary"]["project_count"] == 4
    assert result["violations"] == []
    assert [item["action_type"] for item in result["planned_changes"]] == [
        "status_update",
        "budget_update",
        "bid_update",
        "roi_coeff_update",
    ]


def test_project_update_preflight_rejects_invalid_management_action_values(tmp_path: Path):
    allowlist_path = tmp_path / "allowed.json"
    db_path = tmp_path / "roibang.sqlite3"
    _write_allowed_accounts(allowlist_path)
    _seed_projects(db_path)
    update = _project_update(allowlist_path)
    update["actions"][0]["opt_status"] = "DELETE"
    update["actions"][1]["budget_mode"] = "BUDGET_MODE_DAY"
    update["actions"][1]["budget"] = ""
    update["actions"][2]["cpa_bid"] = 0
    update["actions"][3]["roi_goal"] = 8

    result = build_project_update_preflight(update, db_path=db_path)

    assert result["ok"] is False
    assert "status_update opt_status must be ENABLE or DISABLE: adv-1/p-status" in result["violations"]
    assert "budget_update requires budget when budget_mode is BUDGET_MODE_DAY: adv-1/p-budget" in result["violations"]
    assert "bid_update cpa_bid must be greater than 0: adv-2/p-bid" in result["violations"]
    assert "roi_coeff_update roi_goal must be between 0.01 and 5: adv-2/p-roi" in result["violations"]


def test_project_update_preflight_accepts_ratio_budget_and_bid_actions(tmp_path: Path):
    allowlist_path = tmp_path / "allowed.json"
    db_path = tmp_path / "roibang.sqlite3"
    _write_allowed_accounts(allowlist_path)
    _seed_projects(db_path)
    update = {
        "project_update_id": "project-management-001",
        "operator": "郭靖",
        "allowed_target_accounts_path": str(allowlist_path),
        "actions": [
            {
                "action_type": "budget_update",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": "p-budget",
                "budget_mode": "BUDGET_MODE_DAY",
                "adjustment_ratio": -0.2,
            },
            {
                "action_type": "bid_update",
                "advertiser_id": "adv-2",
                "entity_type": "project",
                "project_id": "p-bid",
                "adjustment_ratio": -0.1,
            },
        ],
    }

    result = build_project_update_preflight(update, db_path=db_path)

    assert result["ok"] is True
    assert result["violations"] == []
    assert result["planned_changes"] == [
        {
            "action_type": "budget_update",
            "advertiser_id": "adv-1",
            "project_id": "p-budget",
            "budget_mode": "BUDGET_MODE_DAY",
            "adjustment_ratio": -0.2,
        },
        {
            "action_type": "bid_update",
            "advertiser_id": "adv-2",
            "project_id": "p-bid",
            "cpa_bid": None,
            "adjustment_ratio": -0.1,
        },
    ]


def test_project_update_execute_dry_run_blocks_without_approval(tmp_path: Path):
    result = run_project_update_execute_request(
        {
            "project_update": _project_update(tmp_path / "allowed.json"),
            "preflight_artifact": _preflight(),
            "execute_enabled": False,
            "approved": False,
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["blocking_reasons"] == ["project update execute requires execute_enabled=true and approved=true"]


def test_project_update_execute_batches_project_management_actions(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {"project_ids": []}}

    result = run_project_update_execute_request(
        {
            "project_update": _project_update(tmp_path / "allowed.json"),
            "preflight_artifact": _preflight(),
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["external_api_calls"] == 4
    assert [(call["operation"], call["endpoint"]) for call in calls] == [
        ("update_project_status", PROJECT_STATUS_UPDATE_ENDPOINT),
        ("update_project_budget", PROJECT_BUDGET_UPDATE_ENDPOINT),
        ("update_project_cpa_bid", PROJECT_CPA_BID_UPDATE_ENDPOINT),
        ("update_project_roi_goal", PROJECT_ROI_GOAL_UPDATE_ENDPOINT),
    ]
    assert calls[0]["payload"]["data"] == [{"project_id": "p-status", "opt_status": "DISABLE"}]
    assert calls[1]["payload"]["data"] == [
        {"project_id": "p-budget", "budget_mode": "BUDGET_MODE_DAY", "budget": 300}
    ]
    assert calls[2]["payload"]["data"] == [{"project_id": "p-bid", "cpa_bid": 103}]
    assert calls[3]["payload"]["data"] == [{"project_id": "p-roi", "roi_goal": 0.41}]
    assert Path(result["artifact_path"]).exists()


def test_project_update_execute_can_delete_projects(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {}}

    result = run_project_update_execute_request(
        {
            "project_update": {
                "project_update_id": "project-management-001",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-delete",
                    }
                ],
            },
            "preflight_artifact": _preflight(),
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 2
    assert calls == [
        {
            "operation": "delete_project",
            "method": "POST",
            "endpoint": PROJECT_DELETE_ENDPOINT,
            "payload": {"advertiser_id": "adv-1", "project_ids": ["p-delete"]},
        },
        {
            "operation": "lookup_project_schedule",
            "method": "GET",
            "endpoint": "/open_api/v3.0/project/list/",
            "payload": {
                "advertiser_id": "adv-1",
                "filtering": {"ids": ["p-delete"]},
                "page": 1,
                "page_size": 1,
            },
        },
    ]


def test_project_update_execute_reports_delete_project_item_errors(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "message": "OK",
            "data": {
                "project_ids": ["p-ok"],
                "errors": [
                    {
                        "project_id": "p-missing",
                        "error_message": "项目不存在或者项目已被删除",
                    }
                ],
            },
        }

    result = run_project_update_execute_request(
        {
            "project_update": {
                "project_update_id": "project-management-001",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-ok",
                    },
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-missing",
                    },
                ],
            },
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is False
    assert result["status"] == "partial_failed"
    assert result["external_api_calls"] == 2
    assert result["summary"]["updated_project_count"] == 1
    assert result["summary"]["failed_project_count"] == 1
    assert "p-missing" in result["blocking_reasons"][0]
    assert result["results"] == [
        {
            "operation": "delete_project",
            "advertiser_id": "adv-1",
            "project_count": 1,
            "requested_project_count": 2,
            "failed_project_count": 1,
            "project_ids": ["p-ok"],
            "requested_project_ids": ["p-ok", "p-missing"],
            "error_list": [
                {
                    "project_id": "p-missing",
                    "error_message": "项目不存在或者项目已被删除",
                }
            ],
            "status": "partial_failed",
        }
    ]
    assert [call["operation"] for call in calls] == ["delete_project", "lookup_project_schedule"]
    assert calls[0]["payload"]["project_ids"] == ["p-ok", "p-missing"]


def test_project_update_execute_verifies_deleted_projects_are_gone(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        if request["operation"] == "delete_project":
            return {
                "code": 0,
                "message": "OK",
                "data": {"project_ids": ["p-deleted", "p-still-active"], "errors": []},
            }
        if request["operation"] == "lookup_project_schedule":
            return {
                "code": 0,
                "message": "OK",
                "data": {"list": [{"project_id": "p-still-active", "project_name": "7R-未删除"}]},
            }
        return {"code": 0, "message": "OK", "data": {}}

    result = run_project_update_execute_request(
        {
            "project_update": {
                "project_update_id": "project-management-001",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-deleted",
                    },
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-still-active",
                    },
                ],
            },
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is False
    assert result["status"] == "partial_failed"
    assert result["external_api_calls"] == 2
    assert result["summary"]["updated_project_count"] == 1
    assert result["summary"]["failed_project_count"] == 1
    assert result["results"][0]["project_ids"] == ["p-deleted"]
    assert result["results"][0]["failed_project_count"] == 1
    assert result["results"][0]["error_list"] == [
        {
            "project_id": "p-still-active",
            "project_name": "7R-未删除",
            "error_message": "删除接口返回成功，但复核时项目仍存在",
        }
    ]
    assert [call["operation"] for call in calls] == ["delete_project", "lookup_project_schedule"]


def test_project_update_execute_blocks_management_action_missing_project_id(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {}}

    result = run_project_update_execute_request(
        {
            "project_update": {
                "project_update_id": "project-management-001",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_name": "7R-测试",
                    }
                ],
            },
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is False
    assert result["status"] == "failed_before_update"
    assert result["external_api_calls"] == 0
    assert result["blocking_reasons"] == ["delete_project requires advertiser_id and project_id: adv-1/"]
    assert calls == []


def test_project_update_execute_resolves_ratio_budget_and_bid_updates(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        if request["operation"] == "lookup_project_schedule":
            project_ids = set(request["payload"]["filtering"]["ids"])
            rows = []
            if "p-budget" in project_ids:
                rows.append(
                    {
                        "project_id": "p-budget",
                        "budget_mode": "BUDGET_MODE_DAY",
                        "budget": 1000,
                    }
                )
            if "p-bid" in project_ids:
                rows.append({"project_id": "p-bid", "cpa_bid": 103})
            return {"code": 0, "message": "OK", "data": {"list": rows}}
        return {"code": 0, "message": "OK", "data": {}}

    result = run_project_update_execute_request(
        {
            "project_update": {
                "project_update_id": "project-management-ratio-001",
                "actions": [
                    {
                        "action_type": "budget_update",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-budget",
                        "budget_mode": "BUDGET_MODE_DAY",
                        "adjustment_ratio": -0.2,
                    },
                    {
                        "action_type": "bid_update",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-bid",
                        "adjustment": {"type": "ratio", "value": -0.1},
                    },
                ],
            },
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 3
    assert [call["operation"] for call in calls] == [
        "lookup_project_schedule",
        "update_project_budget",
        "update_project_cpa_bid",
    ]
    assert calls[1]["payload"]["data"] == [
        {"project_id": "p-budget", "budget_mode": "BUDGET_MODE_DAY", "budget": 800}
    ]
    assert calls[2]["payload"]["data"] == [{"project_id": "p-bid", "cpa_bid": 92.7}]


def test_project_update_execute_blocks_ratio_update_when_current_value_missing(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {"list": [{"project_id": "p-budget"}]}}

    result = run_project_update_execute_request(
        {
            "project_update": {
                "project_update_id": "project-management-ratio-001",
                "actions": [
                    {
                        "action_type": "budget_update",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-budget",
                        "budget_mode": "BUDGET_MODE_DAY",
                        "adjustment_ratio": -0.2,
                    }
                ],
            },
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is False
    assert result["status"] == "failed_before_update"
    assert result["external_api_calls"] == 1
    assert result["blocking_reasons"] == ["ratio update missed current budget: adv-1/p-budget"]
    assert [call["operation"] for call in calls] == ["lookup_project_schedule"]


def test_project_update_execute_can_run_management_action_without_preflight(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {}}

    result = run_project_update_execute_request(
        {
            "project_update": {
                "project_update_id": "project-management-001",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "adv-1",
                        "entity_type": "project",
                        "project_id": "p-delete",
                    }
                ],
            },
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["preflight_artifact_path"] == ""
    assert [call["operation"] for call in calls] == ["delete_project", "lookup_project_schedule"]


def test_project_update_execute_splits_management_actions_into_ten_item_batches(tmp_path: Path):
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {"code": 0, "message": "OK", "data": {}}

    project_update = {
        "project_update_id": "project-management-001",
        "actions": [
            {
                "action_type": "status_update",
                "advertiser_id": "adv-1",
                "entity_type": "project",
                "project_id": f"p-{index}",
                "opt_status": "DISABLE",
            }
            for index in range(11)
        ],
    }
    result = run_project_update_execute_request(
        {
            "project_update": project_update,
            "preflight_artifact": _preflight(),
            "execute_enabled": True,
            "approved": True,
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 2
    assert [len(call["payload"]["data"]) for call in calls] == [10, 1]
    assert calls[0]["payload"]["data"][0] == {"project_id": "p-0", "opt_status": "DISABLE"}


def test_project_status_update_cli_wrapper_prints_project_update_json(tmp_path: Path, capsys):
    update_path = tmp_path / "project_status_update.local.json"
    update_path.write_text(
        json.dumps(
            {
                "project_update_id": "project-status-001",
                "actions": [
                    {
                        "action_type": "status_update",
                        "advertiser_id": "adv-1",
                        "project_id": "p-1",
                        "opt_status": "ENABLE",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    preflight_path = tmp_path / "preflight.json"
    preflight_path.write_text(
        json.dumps(
            {
                "ok": True,
                "workflow": "project_update_preflight",
                "status": "passed",
                "summary": {"project_update_id": "project-status-001"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script("run_project_status_update.py")

    exit_code = module.run_from_args(
        [
            "--project-update",
            str(update_path),
            "--preflight-artifact",
            str(preflight_path),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["workflow"] == "project_update_execute"
    assert output["status"] == "blocked"
    assert output["external_api_calls"] == 0


def test_project_update_execute_cli_reads_nested_runner_transport_config():
    module = _load_script("run_project_update_execute.py")

    config = module._transport_config(
        {
            "create_live_execute_once": {
                "create_http_transport": {
                    "enabled": True,
                    "allow_mutation": True,
                    "run_id": "run-001",
                }
            }
        }
    )

    assert config == {"enabled": True, "allow_mutation": True, "run_id": "run-001"}
