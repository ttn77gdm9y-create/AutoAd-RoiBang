import importlib.util
import json
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.create_live_activate_once import run_create_live_activate_once_request
from roibang_v2.workflows.create_provider_id_ledger import record_create_provider_id


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _runtime_config(tmp_path: Path, *, execution_enabled: bool = False, external_api_enabled: bool = False) -> Path:
    path = tmp_path / "runtime.json"
    path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase2",
                "database_path": str(tmp_path / "roibang.sqlite3"),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": "data/fixtures",
                "external_api_enabled": external_api_enabled,
                "execution_enabled": execution_enabled,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _policy() -> dict:
    return {
        "create_live_execute_once": {
            "allow_create_http_transport": True,
            "create_http_transport": {
                "enabled": True,
                "allow_mutation": True,
                "run_id": "activate-run-001",
                "operator": "operator",
                "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            },
        }
    }


def _seed_promotions(db_path: Path, *, count: int = 3) -> None:
    bootstrap_database(db_path)
    for index in range(1, count + 1):
        record_create_provider_id(
            db_path=db_path,
            entity_type="promotion",
            local_key=f"target-1-p001-u{index:02d}",
            provider_id=str(9000 + index),
            plan_id="plan-1",
            request_id="req-1",
            advertiser_id="1856647523922953",
            parent_local_key="target-1-p001",
            source_workflow="create_live_execute_once",
        )


def _seed_promotions_without_advertiser_id(db_path: Path) -> None:
    bootstrap_database(db_path)
    record_create_provider_id(
        db_path=db_path,
        entity_type="promotion",
        local_key="1856647523922953-first-live-20260511-15acc-wx-7r-male-a-p001-u01",
        provider_id="7638613694456414214",
        plan_id="plan-1",
        request_id="req-1",
        advertiser_id="",
        parent_local_key="1856647523922953-first-live-20260511-15acc-wx-7r-male-a-p001",
        source_workflow="create_live_execute_once",
    )


def test_create_live_activate_once_dry_run_batches_promotions_without_api_calls(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_promotions(db_path, count=11)

    result = run_create_live_activate_once_request(
        {
            "create_live_activate_once": {
                "plan_id": "plan-1",
                "execute": False,
                "runtime": {"execution_enabled": False, "external_api_enabled": False},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=lambda _call: (_ for _ in ()).throw(AssertionError("dry run must not call transport")),
    )

    assert result["ok"] is True
    assert result["status"] == "dry_run_completed"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["planned_unit_count"] == 11
    assert result["summary"]["planned_batch_count"] == 2
    assert [len(batch["promotion_ids"]) for batch in result["activation_batches"]] == [10, 1]


def test_create_live_activate_once_infers_advertiser_id_from_local_key(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_promotions_without_advertiser_id(db_path)

    result = run_create_live_activate_once_request(
        {
            "create_live_activate_once": {
                "plan_id": "plan-1",
                "execute": False,
                "runtime": {"execution_enabled": False, "external_api_enabled": False},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
    )

    assert result["summary"]["planned_unit_count"] == 1
    assert result["activation_batches"] == [
        {
            "advertiser_id": "1856647523922953",
            "promotion_ids": ["7638613694456414214"],
            "local_keys": ["1856647523922953-first-live-20260511-15acc-wx-7r-male-a-p001-u01"],
        }
    ]


def test_create_live_activate_once_execute_enables_units_from_plan_ledger(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_promotions(db_path, count=2)
    calls: list[dict] = []

    def fake_transport(call: dict) -> dict:
        calls.append(call)
        return {"code": 0, "message": "OK", "data": {"promotion_ids": [9001, 9002], "errors": []}}

    result = run_create_live_activate_once_request(
        {
            "create_live_activate_once": {
                "plan_id": "plan-1",
                "execute": True,
                "runtime": {"execution_enabled": True, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["status"] == "activate_completed"
    assert result["execution_enabled"] is True
    assert result["external_api_calls"] == 1
    assert result["summary"]["activated_unit_count"] == 2
    assert result["summary"]["failed_unit_count"] == 0
    assert result["summary"]["manual_review_required"] is False
    assert calls == [
        {
            "operation": "activate_unit",
            "endpoint": "/open_api/v3.0/promotion/status/update/",
            "payload": {
                "advertiser_id": 1856647523922953,
                "data": [
                    {"promotion_id": 9001, "opt_status": "ENABLE"},
                    {"promotion_id": 9002, "opt_status": "ENABLE"},
                ],
            },
            "transport_mode": "create_http",
        }
    ]


def test_create_live_activate_once_blocks_execute_without_runtime_enabled(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_promotions(db_path, count=1)

    result = run_create_live_activate_once_request(
        {
            "create_live_activate_once": {
                "plan_id": "plan-1",
                "execute": True,
                "runtime": {"execution_enabled": False, "external_api_enabled": True},
            }
        },
        runs_dir=tmp_path / "runs",
        db_path=db_path,
        transport=lambda _call: (_ for _ in ()).throw(AssertionError("blocked run must not call transport")),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["external_api_calls"] == 0
    assert result["blocking_reasons"] == ["runtime.execution_enabled is false"]


def test_create_live_activate_once_script_defaults_to_dry_run(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_promotions(db_path, count=1)
    runtime_path = _runtime_config(tmp_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(_policy(), ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_activate_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan-id",
            "plan-1",
            "--dry-run",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_live_activate_once"
    assert output["status"] == "dry_run_completed"
    assert output["external_api_calls"] == 0
    assert output["summary"]["planned_unit_count"] == 1


def test_create_live_activate_once_script_blocks_execute_before_token_when_runtime_disabled(tmp_path: Path, capsys):
    db_path = tmp_path / "roibang.sqlite3"
    _seed_promotions(db_path, count=1)
    runtime_path = _runtime_config(tmp_path, execution_enabled=False, external_api_enabled=False)
    policy_path = tmp_path / "policy.json"
    policy = _policy()
    policy["create_live_execute_once"]["create_http_transport"].pop("token_env", None)
    policy_path.write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
    module = _load_script("run_create_live_activate_once")

    exit_code = module.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--policy",
            str(policy_path),
            "--plan-id",
            "plan-1",
            "--execute",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["status"] == "blocked"
    assert output["external_api_calls"] == 0
    assert output["blocking_reasons"] == [
        "runtime.execution_enabled is false",
        "runtime.external_api_enabled is false",
    ]
