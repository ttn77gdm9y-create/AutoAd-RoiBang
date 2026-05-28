import json
import sys
from pathlib import Path

from roibang_v2.ui.artifact_reader import compact_summary
from roibang_v2.ui.artifact_reader import find_latest_artifact
from roibang_v2.ui.artifact_reader import load_latest_artifact
from roibang_v2.ui.script_runner import build_account_remark_config_command
from roibang_v2.ui.script_runner import build_account_remark_execute_command
from roibang_v2.ui.script_runner import build_ai_template_drafts_command
from roibang_v2.ui.script_runner import build_create_live_config_check_command
from roibang_v2.ui.script_runner import build_create_live_execute_command
from roibang_v2.ui.script_runner import build_create_live_execute_report_command
from roibang_v2.ui.script_runner import build_create_live_terminal_command
from roibang_v2.ui.script_runner import build_create_plan_command
from roibang_v2.ui.script_runner import build_delivery_patrol_command
from roibang_v2.ui.script_runner import build_project_filter_command
from roibang_v2.ui.script_runner import build_project_update_execute_command
from roibang_v2.ui.script_runner import build_product_config_publish_command
from roibang_v2.ui.execution_review import build_account_remark_execution_review
from roibang_v2.ui.execution_review import build_payload_chinese_rows
from roibang_v2.ui.execution_review import build_payload_chinese_summary
from roibang_v2.ui.execution_review import build_project_update_execution_review
from roibang_v2.ui.execution_review import remember_execution_path
from roibang_v2.ui.execution_review import resolve_optional_execution_path
from roibang_v2.ui.streamlit_shell import list_create_modes
from roibang_v2.ui.streamlit_shell import list_products
from roibang_v2.ui.streamlit_shell import build_allowed_create_accounts_config
from roibang_v2.ui.streamlit_shell import draft_mode_filename
from roibang_v2.ui.streamlit_shell import load_create_template_catalog
from roibang_v2.ui.streamlit_shell import load_create_mode
from roibang_v2.ui.streamlit_shell import load_product_config
from roibang_v2.ui.streamlit_shell import load_ui_config
from roibang_v2.ui.streamlit_shell import mode_label
from roibang_v2.ui.streamlit_shell import product_config_missing_fields
from roibang_v2.ui.streamlit_shell import product_create_template_catalog_path
from roibang_v2.ui.streamlit_shell import product_label
from roibang_v2.ui.streamlit_shell import save_allowed_create_accounts_config
from roibang_v2.ui.streamlit_shell import save_create_mode_draft
from roibang_v2.ui.streamlit_shell import save_product_create_mode_config
from roibang_v2.ui.streamlit_shell import save_product_create_template_catalog
from roibang_v2.ui.streamlit_shell import save_product_draft
from roibang_v2.ui.streamlit_shell import split_account_ids


def test_load_ui_config_merges_defaults(tmp_path):
    config_path = tmp_path / "ui.json"
    config_path.write_text(json.dumps({"title": "Test UI", "runs_dir": "runs"}), encoding="utf-8")

    config = load_ui_config(config_path)

    assert config["title"] == "Test UI"
    assert config["runs_dir"] == "runs"
    assert config["default_owner"] == "郭靖"


def test_list_create_modes_reads_display_name_and_mode_key(tmp_path):
    mode_dir = tmp_path / "create-modes"
    mode_dir.mkdir()
    mode_path = mode_dir / "wx_pay_general_recent_scale.example.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_recent_scale",
                "display_name": "每付通投近期放量",
                "template_key": "wx_pay_general",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list_create_modes(mode_dir)

    assert rows == [
        {
            "mode_key": "wx_pay_general_recent_scale",
            "display_name": "每付通投近期放量",
            "template_key": "wx_pay_general",
            "product_key": "",
            "path": str(mode_path),
        }
    ]
    assert mode_label(rows[0]) == "每付通投近期放量 (wx_pay_general_recent_scale)"


def test_load_create_mode_reads_exact_mode_key(tmp_path):
    mode_dir = tmp_path / "create-modes"
    mode_dir.mkdir()
    mode_path = mode_dir / "wx_pay_general_recent_scale.example.json"
    mode_path.write_text(
        json.dumps({"mode_key": "wx_pay_general_recent_scale", "defaults": {"daily_budget": 88888}}),
        encoding="utf-8",
    )

    mode = load_create_mode(mode_dir, "wx_pay_general_recent_scale")

    assert mode["mode_key"] == "wx_pay_general_recent_scale"
    assert mode["defaults"]["daily_budget"] == 88888


def test_load_create_mode_reads_product_specific_mode(tmp_path):
    mode_dir = tmp_path / "create-modes"
    product_dir = mode_dir / "diandian-hero"
    product_dir.mkdir(parents=True)
    mode_path = product_dir / "wx_pay_general_recent_scale.local.json"
    mode_path.write_text(
        json.dumps(
            {
                "mode_key": "wx_pay_general_recent_scale",
                "product_key": "diandian-hero",
                "display_name": "点点英雄每付通投近期放量",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list_create_modes(mode_dir)
    mode = load_create_mode(mode_dir, "wx_pay_general_recent_scale", "diandian-hero")

    assert rows == [
        {
            "mode_key": "wx_pay_general_recent_scale",
            "display_name": "点点英雄每付通投近期放量",
            "template_key": "",
            "product_key": "diandian-hero",
            "path": str(mode_path),
        }
    ]
    assert mode["product_key"] == "diandian-hero"


def test_save_create_mode_draft_writes_local_json(tmp_path):
    output = save_create_mode_draft(
        tmp_path,
        {"mode_key": "WX Pay Draft", "display_name": "草稿", "defaults": {"daily_budget": 10000}},
    )

    assert output.name == "wx-pay-draft.local.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["display_name"] == "草稿"
    assert draft_mode_filename("每付通投 草稿") == "create-mode-draft"


def test_save_create_mode_draft_normalizes_random_materials(tmp_path):
    output = save_create_mode_draft(
        tmp_path,
        {
            "mode_key": "wx_pay_general_random_materials_draft",
            "display_name": "素材不限草稿",
            "defaults": {"daily_budget": 88888, "cpa_bid": 86.88},
            "material_selection": {
                "selection_type": "random_materials",
                "lookback_days": 30,
                "first_seen_days": 7,
                "min_stat_cost": 200,
            },
        },
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert "cpa_bid" not in payload["defaults"]
    assert payload["material_selection"]["min_stat_cost"] == 0
    assert payload["material_selection"]["sort_by"] == "random_stable"
    assert "lookback_days" not in payload["material_selection"]
    assert "first_seen_days" not in payload["material_selection"]


def test_save_product_create_mode_config_writes_product_local_json(tmp_path):
    output = save_product_create_mode_config(
        tmp_path / "create-modes",
        {
            "mode_key": "wx_pay_general_scale",
            "product_key": "diandian-hero",
            "display_name": "点点英雄每付通投历史放量",
            "defaults": {"daily_budget": 10000},
        },
    )

    assert output == tmp_path / "create-modes" / "diandian-hero" / "wx_pay_general_scale.local.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["product_key"] == "diandian-hero"
    assert payload["defaults"]["daily_budget"] == 10000


def test_save_product_create_mode_config_normalizes_random_materials(tmp_path):
    output = save_product_create_mode_config(
        tmp_path / "create-modes",
        {
            "mode_key": "wx_pay_general_random_materials",
            "product_key": "diandian-hero",
            "display_name": "点点英雄每付通投素材不限",
            "defaults": {"daily_budget": 88888, "cpa_bid": 86.88},
            "material_selection": {
                "selection_type": "random_materials",
                "lookback_days": 30,
                "first_seen_days": 7,
                "min_create_age_days": 3,
                "min_stat_cost": 200,
                "sort_by": "stat_cost_desc",
                "random_shuffle": False,
            },
        },
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    selection = payload["material_selection"]
    assert selection["min_stat_cost"] == 0
    assert selection["sort_by"] == "random_stable"
    assert selection["random_shuffle"] is True
    assert "lookback_days" not in selection
    assert "first_seen_days" not in selection
    assert "min_create_age_days" not in selection
    assert "cpa_bid" not in payload["defaults"]


def test_save_product_create_mode_config_allows_yzt_product_specific_json(tmp_path):
    output = save_product_create_mode_config(
        tmp_path / "create-modes",
        {
            "mode_key": "wx_pay_general_scale",
            "product_key": "yzt-wechat-mini-game",
            "display_name": "勇者突进每付通投历史放量",
        },
    )

    assert output == tmp_path / "create-modes" / "yzt-wechat-mini-game" / "wx_pay_general_scale.local.json"


def test_product_create_template_catalog_prefers_product_local_json(tmp_path):
    template_dir = tmp_path / "create-templates"
    template_dir.mkdir()
    (template_dir / "wx-mini-game.json").write_text(json.dumps({"product": "勇者突进"}), encoding="utf-8")
    (template_dir / "diandian-hero.local.json").write_text(
        json.dumps({"product_key": "diandian-hero", "product": "点点英雄"}, ensure_ascii=False),
        encoding="utf-8",
    )

    path = product_create_template_catalog_path(template_dir, "diandian-hero")
    catalog = load_create_template_catalog(template_dir, "diandian-hero")

    assert path == template_dir / "diandian-hero.local.json"
    assert catalog["product"] == "点点英雄"


def test_save_product_create_template_catalog_writes_product_local_json(tmp_path):
    output = save_product_create_template_catalog(
        tmp_path / "create-templates",
        {
            "product_key": "diandian-hero",
            "product": "点点英雄",
            "templates": {"wx_pay_general": {"title_pool": ["点点文案"]}},
        },
    )

    assert output == tmp_path / "create-templates" / "diandian-hero.local.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["templates"]["wx_pay_general"]["title_pool"] == ["点点文案"]


def test_list_products_reads_product_key_and_foundation(tmp_path):
    product_dir = tmp_path / "products"
    product_dir.mkdir()
    (product_dir / "yzt-wechat-mini-game.example.json").write_text(
        json.dumps(
            {
                "product_key": "yzt-wechat-mini-game",
                "product": "勇者突进",
                "platform": "WECHAT_GAME",
                "source_advertiser_id": "1856647522964490",
                "organization_id": "1851650746645060",
                "foundation": {"anchor_id": "anchor-1"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list_products(product_dir)
    loaded = load_product_config(product_dir, "yzt-wechat-mini-game")

    assert rows == [
        {
            "product_key": "yzt-wechat-mini-game",
            "product": "勇者突进",
            "platform": "WECHAT_GAME",
            "source_advertiser_id": "1856647522964490",
        }
    ]
    assert loaded["organization_id"] == "1851650746645060"
    assert product_label(rows[0]) == "勇者突进 (yzt-wechat-mini-game)"


def test_product_config_missing_fields_reports_foundation_gaps():
    missing = product_config_missing_fields(
        {
            "product_key": "bad",
            "product": "坏配置",
            "platform": "WECHAT_GAME",
            "source_advertiser_id": "source-1",
            "organization_id": "org-1",
            "foundation": {"anchor_id": "anchor-1"},
        }
    )

    assert "foundation.effective_touch_url" in missing
    assert "foundation.landing_url" in missing
    assert "foundation.fixed_video_cover_id" in missing
    assert "source_advertiser_id" not in missing


def test_save_product_draft_writes_local_json(tmp_path):
    output = save_product_draft(
        tmp_path,
        {"product_key": "New Product", "product": "新产品", "foundation": {"anchor_id": "anchor-1"}},
    )

    assert output.name == "new-product.local.json"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["product"] == "新产品"
    assert payload["draft"]["enabled"] is True


def test_build_and_save_allowed_create_accounts_config(tmp_path):
    account_ids = split_account_ids("1861, 1862\n1861\n1863")
    config = build_allowed_create_accounts_config(
        product="点点英雄",
        channel="wx",
        account_ids=account_ids,
        account_name_prefix="点点英雄-微小-郭靖",
    )
    output = save_allowed_create_accounts_config(tmp_path / "allowed.local.json", config)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert account_ids == ["1861", "1862", "1863"]
    assert payload["product"] == "点点英雄"
    assert payload["channel"] == "wx"
    assert payload["allowed_target_accounts"][0] == {
        "advertiser_id": "1861",
        "account_name": "点点英雄-微小-郭靖-001",
        "product": "点点英雄",
        "channel": "wx",
        "enable": True,
    }


def test_artifact_reader_prefers_latest_json(tmp_path):
    workflow_dir = tmp_path / "delivery_patrol"
    workflow_dir.mkdir()
    old_path = workflow_dir / "20260517T010000Z.json"
    new_path = workflow_dir / "20260518T010000Z.json"
    old_path.write_text(json.dumps({"ok": True, "summary": {"value": "old"}}), encoding="utf-8")
    new_path.write_text(json.dumps({"ok": True, "summary": {"value": "new"}}), encoding="utf-8")

    latest = find_latest_artifact(tmp_path, "delivery_patrol")
    payload = load_latest_artifact(tmp_path, "delivery_patrol")

    assert latest == new_path
    assert payload["summary"]["value"] == "new"
    assert payload["artifact_path"] == str(new_path)
    assert compact_summary(payload)["summary"]["value"] == "new"


def test_build_delivery_patrol_command_uses_readonly_entrypoint():
    command = build_delivery_patrol_command(readonly=True)

    assert command[0] == sys.executable
    assert command[1:4] == ["scripts/run_delivery_patrol.py", "--config", "configs/runtime.openapi-execute.local.example.json"]
    assert "--enable-readonly" in command


def test_build_create_plan_command_splits_accounts_and_never_executes():
    command = build_create_plan_command(
        mode="每付通投近期放量",
        accounts="1851, 1852\n1853",
        owner="郭靖",
        target_date="2026-05-18",
    )

    assert command[:2] == [sys.executable, "scripts/run_create_mode.py"]
    assert "--mode" in command
    assert "每付通投近期放量" in command
    assert command.count("--account") == 3
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_create_plan_command_rejects_empty_accounts():
    try:
        build_create_plan_command(
            mode="每付通投素材不限",
            accounts=" \n ",
            owner="郭靖",
        )
    except ValueError as exc:
        assert "账户 ID" in str(exc)
    else:
        raise AssertionError("expected empty accounts to be rejected")


def test_build_create_plan_command_can_pin_product_template_catalog():
    command = build_create_plan_command(
        mode="每付通投近期放量",
        accounts="1861",
        owner="郭靖",
        product_key="diandian-hero",
        template_catalog="configs/create-templates/diandian-hero.local.json",
        cpa_bid="108",
        roi_coefficient="0.41",
    )

    assert "--product-key" in command
    assert "diandian-hero" in command
    assert "--template-catalog" in command
    assert "configs/create-templates/diandian-hero.local.json" in command
    assert "--cpa-bid" in command
    assert "108" in command
    assert "--roi-coefficient" in command
    assert "0.41" in command
    assert "--execute" not in command


def test_build_product_config_publish_command_uses_fixed_script_without_business_execution():
    command = build_product_config_publish_command(draft_path="configs/product-drafts/new-product.local.json")

    assert command[:2] == [sys.executable, "scripts/run_product_config_publish.py"]
    assert "--draft" in command
    assert "configs/product-drafts/new-product.local.json" in command
    assert "--products-dir" in command
    assert "configs/products" in command
    assert "--runs-dir" in command
    assert "data/runs" in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_account_remark_config_command_splits_accounts_and_never_executes():
    command = build_account_remark_config_command(
        update_id="diandian-remark",
        remark="点点英雄-微小-郭靖",
        accounts="1861, 1862\n1863",
        output_path="configs/account-updates/diandian-remark.local.json",
    )

    assert command[:2] == [sys.executable, "scripts/run_account_remark_update_config.py"]
    assert "--update-id" in command
    assert "diandian-remark" in command
    assert "--remark" in command
    assert "点点英雄-微小-郭靖" in command
    assert command.count("--account") == 3
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_project_filter_command_adds_action_specific_fields():
    command = build_project_filter_command(
        project_update_id="close-low-cost",
        advertiser_ids="1851,1852\n1853",
        action_type="status_update",
        name_contains="0518",
        spend_window="today",
        metric_field="stat_cost",
        metric_op="lt",
        metric_value="100",
        output_path="configs/project-updates/close-low-cost.local.json",
        opt_status="DISABLE",
    )

    assert command[:2] == [sys.executable, "scripts/run_project_realtime_filter_config.py"]
    assert command[command.index("--config") + 1] == "configs/project-update-execute.local.json"
    assert command.count("--advertiser-id") == 3
    assert "--metric-filter" in command
    assert "stat_cost:lt:100" in command
    assert "--opt-status" in command
    assert "DISABLE" in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_create_live_terminal_command_checks_config_by_default():
    command = build_create_live_terminal_command(plan_path="configs/create-plans/test.local.json")

    assert command[:2] == [sys.executable, "scripts/run_create_live_execute_terminal.py"]
    assert "--plan" in command
    assert "configs/create-plans/test.local.json" in command
    assert "--check-config-only" in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_create_live_terminal_command_can_build_real_run_command():
    command = build_create_live_terminal_command(
        plan_path="configs/create-plans/test.local.json",
        check_config_only=False,
        open_progress_window=True,
    )

    assert command[:2] == [sys.executable, "scripts/run_create_live_execute_terminal.py"]
    assert "--plan" in command
    assert "configs/create-plans/test.local.json" in command
    assert "--check-config-only" not in command
    assert "--open-progress-window" in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_create_live_config_check_command_uses_json_entrypoint():
    command = build_create_live_config_check_command(plan_path="configs/create-plans/test.local.json")

    assert command[:2] == [sys.executable, "scripts/run_create_live_execute_once.py"]
    assert "--plan" in command
    assert "configs/create-plans/test.local.json" in command
    assert "--check-config-only" in command
    assert "--open-progress-window" not in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_create_live_execute_command_uses_fixed_json_entrypoint():
    command = build_create_live_execute_command(plan_path="configs/create-plans/test.local.json")

    assert command[:2] == [sys.executable, "scripts/run_create_live_execute_once.py"]
    assert "--plan" in command
    assert "configs/create-plans/test.local.json" in command
    assert "--check-config-only" not in command
    assert "--open-progress-window" not in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_create_live_execute_command_can_resume_existing_plan():
    command = build_create_live_execute_command(
        plan_path="configs/create-plans/test.local.json",
        resume_existing_plan=True,
    )

    assert "--resume-existing-plan" in command


def test_build_create_live_execute_report_command_pushes_feishu_by_default():
    command = build_create_live_execute_report_command(
        plan_path="configs/create-plans/test.local.json",
        execute_artifact_path="data/runs/create_live_execute_once/a.json",
    )

    assert command[:2] == [sys.executable, "scripts/run_create_live_execute_report.py"]
    assert "--plan" in command
    assert "configs/create-plans/test.local.json" in command
    assert "--create-live-execute-once-artifact" in command
    assert "data/runs/create_live_execute_once/a.json" in command
    assert "--push-feishu" in command
    assert "--execute" not in command
    assert "--yes" not in command


def test_build_project_update_execute_command_requires_explicit_execute_flag():
    dry_command = build_project_update_execute_command(project_update_path="configs/project-updates/test.local.json")
    execute_command = build_project_update_execute_command(
        project_update_path="configs/project-updates/test.local.json",
        execute=True,
    )

    assert dry_command[:2] == [sys.executable, "scripts/run_project_update_execute.py"]
    assert "--execute" not in dry_command
    assert "--yes" not in dry_command
    assert "--execute" in execute_command
    assert "--yes" in execute_command


def test_build_account_remark_execute_command_requires_explicit_execute_flag():
    dry_command = build_account_remark_execute_command(
        account_remark_update_path="configs/account-updates/test.local.json"
    )
    execute_command = build_account_remark_execute_command(
        account_remark_update_path="configs/account-updates/test.local.json",
        execute=True,
    )

    assert dry_command[:2] == [sys.executable, "scripts/run_account_remark_update.py"]
    assert "--account-remark-update" in dry_command
    assert "configs/project-update-execute.local.json" in dry_command
    assert "--execute" not in dry_command
    assert "--yes" not in dry_command
    assert "--execute" in execute_command
    assert "--yes" in execute_command


def test_execution_path_persists_across_streamlit_reruns_and_defaults_do_not_auto_show(tmp_path: Path):
    state = {}

    assert remember_execution_path(state, "project_update_execute_path", "configs/project-updates/delete.local.json") == "configs/project-updates/delete.local.json"
    assert remember_execution_path(state, "project_update_execute_path", "") == "configs/project-updates/delete.local.json"
    assert resolve_optional_execution_path(state, "project_update_execute_path", "configs/project-updates/other.local.json", project_root=tmp_path) == "configs/project-updates/delete.local.json"

    default_remark_path = "configs/account-updates/ui-account-remark-update.local.json"
    assert resolve_optional_execution_path({}, "account_remark_update_path", default_remark_path, project_root=tmp_path) == ""

    existing = tmp_path / default_remark_path
    existing.parent.mkdir(parents=True)
    existing.write_text("{}", encoding="utf-8")
    assert resolve_optional_execution_path({}, "account_remark_update_path", default_remark_path, project_root=tmp_path) == default_remark_path


def test_project_update_execution_review_summarizes_delete_actions_in_plain_chinese():
    review = build_project_update_execution_review(
        {
            "project_update_id": "delete-low-spend",
            "actions": [
                {
                    "action_type": "delete_project",
                    "advertiser_id": "adv-1",
                    "project_id": "project-1",
                    "project_name": "测试项目",
                    "stat_cost": 12.3,
                }
            ],
        }
    )

    assert review["summary"]["动作"] == "删除项目"
    assert review["summary"]["项目数"] == 1
    assert review["rows"] == [
        {
            "动作": "删除项目",
            "账户 ID": "adv-1",
            "项目 ID": "project-1",
            "项目名称": "测试项目",
            "消耗": 12.3,
            "目标值": "",
        }
    ]


def test_account_remark_execution_review_summarizes_updates_in_plain_chinese():
    review = build_account_remark_execution_review(
        {
            "account_remark_update": {
                "remark": "点点英雄-微小-郭靖",
                "advertiser_ids": ["adv-1", "adv-2"],
            }
        }
    )

    assert review["summary"] == {"动作": "修改账户备注", "账户数": 2, "目标备注": "点点英雄-微小-郭靖"}
    assert review["rows"][0] == {"动作": "修改账户备注", "账户 ID": "adv-1", "目标备注": "点点英雄-微小-郭靖"}


def test_payload_chinese_summary_explains_generic_execution_json():
    payload = {
        "ok": True,
        "workflow": "project_update_execute",
        "status": "completed",
        "execution_enabled": True,
        "external_api_calls": 3,
        "artifact_path": "data/runs/project_update_execute/a.json",
        "summary": {"action_count": 2, "updated_project_count": 2},
    }

    summary = build_payload_chinese_summary(payload)

    assert summary["结果"] == "成功"
    assert summary["流程"] == "project_update_execute"
    assert summary["状态"] == "completed"
    assert summary["真实执行"] == "是"
    assert summary["接口调用"] == 3
    assert summary["动作数"] == 2
    assert summary["项目数"] == 2
    assert summary["结果文件"] == "data/runs/project_update_execute/a.json"


def test_payload_chinese_rows_explains_actions_before_raw_json():
    rows = build_payload_chinese_rows(
        {
            "actions": [
                {
                    "action_type": "delete_project",
                    "advertiser_id": "adv-1",
                    "project_id": "project-1",
                    "project_name": "测试项目",
                }
            ]
        }
    )

    assert rows == [
        {
            "动作": "删除项目",
            "账户 ID": "adv-1",
            "项目 ID": "project-1",
            "项目名称": "测试项目",
            "消耗": "",
            "目标值": "",
        }
    ]


def test_build_ai_template_drafts_command_is_readonly():
    command = build_ai_template_drafts_command()

    assert command[:2] == [sys.executable, "scripts/run_ai_create_template_drafts.py"]
    assert "configs/runtime.example.json" in command
    assert "--execute" not in command
    assert "--yes" not in command
