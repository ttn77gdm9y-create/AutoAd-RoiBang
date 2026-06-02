import json
from pathlib import Path

from roibang_v2.workflows.product_automation_job import build_product_job_commands
from roibang_v2.workflows.product_automation_job import build_product_job_request
from roibang_v2.workflows.product_automation_job import run_product_automation_job
from roibang_v2.workflows.product_automation_job import workflow_for_job


def _product(tmp_path: Path) -> dict:
    allowed_path = tmp_path / "allowed.json"
    allowed_path.write_text(
        json.dumps(
            {
                "allowed_target_accounts": [
                    {"advertiser_id": "target-1", "account_name": "点点账户1", "enable": True},
                    {"advertiser_id": "target-2", "account_name": "点点账户2", "enable": False},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "product_key": "diandian-hero",
        "product": "点点英雄",
        "platform": "WECHAT_GAME",
        "source_advertiser_id": "source-1",
        "organization_id": "org-1",
        "allowed_target_accounts_path": str(allowed_path),
        "account_remark_pattern": "点点英雄-微小-郭靖",
        "automation": {
            "enabled": True,
            "account_discovery": {
                "account_name_keyword": "点点英雄",
                "account_remark_equals": "点点英雄-微小-郭靖",
            },
            "material_daily_sync": {"enabled": True},
            "operation_log_sync": {"enabled": True},
            "daily_report_sync": {"enabled": True},
            "source_material_auto_push": {"enabled": True},
            "source_material_preload": {"enabled": True, "target_scope": "allowed_accounts"},
            "source_material_rollup": {"enabled": True},
            "delivery_patrol": {"enabled": True},
        },
    }


def test_builds_material_daily_sync_request_from_product_config(tmp_path: Path):
    request = build_product_job_request(_product(tmp_path), "material_daily_sync", target_date="yesterday")
    cfg = request["material_history_backfill"]

    assert cfg["product"] == "点点英雄"
    assert cfg["active_account_discovery"]["allow_keyword_accounts"] is True
    assert cfg["active_account_discovery"]["product"] == "点点英雄"
    assert cfg["active_account_discovery"]["workbench"]["keyword"] == "点点英雄"
    assert cfg["material_fetch"]["openapi"]["report_presets"] == ["material_daily"]


def test_builds_source_auto_push_request_with_product_account_keyword(tmp_path: Path):
    request = build_product_job_request(_product(tmp_path), "source_material_auto_push", target_date="yesterday")
    cfg = request["source_material_account_auto_push"]

    assert cfg["product"] == "点点英雄"
    assert cfg["source_advertiser_id"] == "source-1"
    assert cfg["material_source"]["account_name_keyword"] == "点点英雄"
    assert cfg["material_source"]["max_materials"] == 500
    assert cfg["execute"]["create_http_transport"]["run_id"] == "diandian-hero-source-material-account-auto-push"


def test_builds_operation_log_sync_request_from_product_config(tmp_path: Path):
    request = build_product_job_request(_product(tmp_path), "operation_log_sync", target_date="yesterday")
    cfg = request["operation_log_history_sync"]

    assert cfg["product_keyword"] == "点点英雄"
    assert cfg["date_range"] == {"mode": "yesterday"}
    assert cfg["openapi_http"]["response_audit_dir"] == "data/runs/openapi_http/diandian-hero-operation-log-daily"
    assert 51010 in cfg["openapi_http"]["retry_api_codes"]
    assert 400308 in cfg["openapi_http"]["retry_api_codes"]


def test_builds_daily_report_sync_request_from_product_config(tmp_path: Path):
    request = build_product_job_request(_product(tmp_path), "daily_report_sync", target_date="yesterday")
    cfg = request["daily_report_pipeline"]

    assert cfg["active_account_discovery"]["workbench"]["keyword"] == "点点英雄"
    assert cfg["report_fetch"]["product"] == "点点英雄"
    assert cfg["report_fetch"]["output"]["snapshot_dir"] == "data/snapshots/report/diandian-hero-daily"
    assert 51010 in cfg["report_fetch"]["openapi_http"]["retry_api_codes"]
    assert 400308 in cfg["report_fetch"]["openapi_http"]["retry_api_codes"]


def test_builds_preload_request_from_allowed_accounts(tmp_path: Path):
    request = build_product_job_request(_product(tmp_path), "source_material_preload", target_date="2026-05-25")
    cfg = request["source_material_preload_to_accounts"]

    assert cfg["product"] == "点点英雄"
    assert cfg["target_date"] == "2026-05-25"
    assert cfg["target_accounts"]["accounts"] == [
        {"advertiser_id": "target-1", "account_name": "点点账户1", "account_remark": ""}
    ]


def test_builds_source_material_rollup_request_from_product_config(tmp_path: Path):
    request = build_product_job_request(_product(tmp_path), "source_material_rollup", target_date="yesterday")
    cfg = request["product_source_material_rollup"]

    assert cfg["product"] == "点点英雄"
    assert cfg["source_advertiser_id"] == "source-1"
    assert cfg["organization_id"] == "org-1"
    assert cfg["date_range"] == {"start": "2026-02-10", "end": "yesterday"}
    assert cfg["windows"] == [1, 3, 7, 15, 30, "all"]


def test_build_product_job_commands_writes_request_and_command(tmp_path: Path):
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    product = _product(tmp_path)
    (products_dir / "diandian-hero.local.json").write_text(
        json.dumps(product, ensure_ascii=False),
        encoding="utf-8",
    )

    commands = build_product_job_commands(
        job="source_material_preload",
        products_dir=products_dir,
        request_dir=tmp_path / "requests",
        product_key="diandian-hero",
        target_date="2026-05-25",
        execute=True,
        yes=True,
    )

    assert len(commands) == 1
    assert Path(commands[0].request_path).exists()
    assert commands[0].command[-2:] == ["--execute", "--yes"]


def test_build_product_job_commands_writes_scoped_delivery_patrol_requests(tmp_path: Path):
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    product = _product(tmp_path)
    product["automation"]["delivery_patrol"]["account_scopes"] = [
        {
            "scope_id": "diandian-hero-guojing",
            "account_remark_equals": "点点英雄-微小-郭靖",
            "workbench_keyword": "点点英雄",
        },
        {
            "scope_id": "diandian-hero-all",
            "account_name_contains": "点点英雄",
            "workbench_keyword": "点点英雄",
        },
    ]
    (products_dir / "diandian-hero.local.json").write_text(
        json.dumps(product, ensure_ascii=False),
        encoding="utf-8",
    )

    commands = build_product_job_commands(
        job="delivery_patrol",
        products_dir=products_dir,
        request_dir=tmp_path / "requests",
        product_key="diandian-hero",
        target_date="2026-05-30",
    )

    assert [command.scope_id for command in commands] == ["diandian-hero-guojing", "diandian-hero-all"]
    assert all(Path(command.request_path).exists() for command in commands)
    assert "diandian-hero-guojing-delivery_patrol" in Path(commands[0].request_path).name
    assert "diandian-hero-all-delivery_patrol" in Path(commands[1].request_path).name

    guojing = json.loads(Path(commands[0].request_path).read_text(encoding="utf-8"))["delivery_patrol"]
    all_accounts = json.loads(Path(commands[1].request_path).read_text(encoding="utf-8"))["delivery_patrol"]

    assert guojing["account_scope"]["account_remark_equals"] == "点点英雄-微小-郭靖"
    assert "account_name_contains" not in guojing["account_scope"]
    assert all_accounts["account_scope"]["account_name_contains"] == "点点英雄"
    assert "account_remark_equals" not in all_accounts["account_scope"]
    assert guojing["active_account_discovery"]["workbench"]["keyword"] == "点点英雄"
    assert all_accounts["active_account_discovery"]["workbench"]["keyword"] == "点点英雄"
    assert guojing["openapi_http"]["response_audit_dir"].endswith("diandian-hero-guojing-delivery-patrol")
    assert all_accounts["openapi_http"]["response_audit_dir"].endswith("diandian-hero-all-delivery-patrol")


def test_product_automation_artifact_is_namespaced_by_job(tmp_path: Path):
    products_dir = tmp_path / "products"
    products_dir.mkdir()
    (products_dir / "diandian-hero.local.json").write_text(
        json.dumps(_product(tmp_path), ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_product_automation_job(
        job="material_daily_sync",
        products_dir=products_dir,
        request_dir=tmp_path / "requests",
        runs_dir=tmp_path / "runs",
        product_key="diandian-hero",
        target_date="2026-05-25",
        dry_run=True,
    )

    assert result["workflow"] == "product_automation_job_material_daily_sync"
    assert Path(result["artifact_path"]).parent.name == "product_automation_job_material_daily_sync"
    assert workflow_for_job("source_material_preload") == "product_automation_job_source_material_preload"
