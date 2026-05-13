import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.project_status_update_config import build_project_status_update_config
from roibang_v2.workflows.project_status_update_config import run_project_status_update_config_request


def _load_script():
    script_path = Path("scripts/run_project_status_update_config.py")
    spec = importlib.util.spec_from_file_location("run_project_status_update_config", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_project_status_update_config_expands_enabled_projects_from_accounts():
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "project_id": "p-1",
                        "name": "勇者突进-正常",
                        "status_first": "PROJECT_STATUS_ENABLE",
                        "delivery_type": "NORMAL",
                    },
                    {
                        "project_id": "p-duration",
                        "name": "勇者突进-周期稳投",
                        "status_first": "PROJECT_STATUS_ENABLE",
                        "delivery_type": "DURATION",
                    },
                ],
                "page_info": {"total_number": 2},
            },
        }

    result = build_project_status_update_config(
        {
            "project_update_id": "pause-six-accounts-001",
            "operator": "郭靖",
            "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
            "advertiser_ids": ["adv-1"],
            "opt_status": "DISABLE",
            "reason": "重建前关停旧项目",
        },
        transport=transport,
    )

    assert result["external_api_calls"] == 1
    assert result["summary"]["action_count"] == 1
    assert result["summary"]["skipped_duration_project_count"] == 1
    assert result["project_update"]["actions"] == [
        {
            "action_type": "status_update",
            "advertiser_id": "adv-1",
            "entity_type": "project",
            "project_id": "p-1",
            "project_name": "勇者突进-正常",
            "opt_status": "DISABLE",
            "reason": "重建前关停旧项目",
        }
    ]
    assert calls[0]["operation"] == "lookup_project_list"
    assert calls[0]["payload"]["filtering"] == {"status_first": "PROJECT_STATUS_ENABLE"}


def test_project_status_update_config_filters_projects_by_name_contains():
    calls: list[dict] = []

    def transport(request: dict) -> dict:
        calls.append(request)
        return {
            "code": 0,
            "data": {
                "list": [
                    {"project_id": "p-0511", "name": "0511_郭靖_勇者突进_微小每付7R男"},
                    {"project_id": "p-0501", "name": "0501_郭靖_勇者突进_微小每付通投"},
                ]
            },
        }

    result = build_project_status_update_config(
        {
            "project_update_id": "enable-0511-001",
            "advertiser_ids": ["adv-1"],
            "opt_status": "ENABLE",
            "name_contains": ["0511"],
        },
        transport=transport,
    )

    assert result["summary"]["action_count"] == 1
    assert result["summary"]["name_contains"] == ["0511"]
    assert result["project_update"]["actions"][0]["project_id"] == "p-0511"
    assert calls[0]["payload"]["filtering"] == {
        "status_first": "PROJECT_STATUS_DISABLE",
        "status_second": "PROJECT_STATUS_STOP",
        "name": "0511",
    }


def test_run_project_status_update_config_writes_project_update_json(tmp_path: Path):
    def transport(_request: dict) -> dict:
        return {"code": 0, "data": {"list": [{"project_id": "p-1", "name": "勇者突进"}]}}

    output_path = tmp_path / "pause.local.json"
    result = run_project_status_update_config_request(
        {
            "project_update_id": "pause-account-001",
            "advertiser_ids": ["adv-1"],
            "opt_status": "DISABLE",
            "output_path": str(output_path),
        },
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["workflow"] == "project_status_update_config"
    assert result["project_update_path"] == str(output_path)
    assert Path(result["artifact_path"]).exists()
    assert saved["actions"][0]["action_type"] == "status_update"


def test_project_status_update_config_cli_requires_config_for_live_lookup(tmp_path: Path, capsys):
    module = _load_script()

    exit_code = module.run_from_args(
        [
            "--project-update-id",
            "pause-account-001",
            "--advertiser-id",
            "adv-1",
            "--opt-status",
            "DISABLE",
            "--output",
            str(tmp_path / "pause.local.json"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["workflow"] == "project_status_update_config"
    assert output["status"] == "blocked"
    assert output["blocking_reasons"] == ["project status update config requires --config for live project lookup"]


def test_project_status_update_config_cli_reads_nested_runner_transport_config():
    module = _load_script()

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
