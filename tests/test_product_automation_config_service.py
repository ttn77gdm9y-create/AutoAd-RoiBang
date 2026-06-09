import json
from pathlib import Path

from backend.app.services.product_automation import build_product_automation_dry_run
from backend.app.services.product_automation import build_product_automation_overview
from backend.app.services.product_automation import save_product_automation_config


def _save_body(enabled_jobs: list[str]) -> dict:
    return {
        "product_key": "diandian-hero",
        "product": "点点英雄",
        "platform": "WECHAT_GAME",
        "source_advertiser_name": "黑旗-点点英雄-微小-傲星-151",
        "source_advertiser_id": "1856647522964490",
        "organization_id": "1851650746645060",
        "allowed_target_accounts_path": "configs/allowed-create-accounts.diandian-hero.local.json",
        "account_name_keyword": "点点英雄",
        "account_remark_equals": "点点英雄-微小-郭靖",
        "enabled_jobs": enabled_jobs,
    }


def test_save_product_automation_config_allows_all_jobs_closed(tmp_path: Path):
    result = save_product_automation_config(configs_dir=tmp_path, body=_save_body([]))

    assert result["summary"]["status"] == "committed"
    assert result["summary"]["items"] == [
        {"label": "产品", "value": "点点英雄"},
        {"label": "开启任务", "value": 0},
        {"label": "关闭任务", "value": 7},
        {"label": "真实执行", "value": "未执行"},
    ]
    rows = {row["配置项"]: row["值"] for row in result["table"]["rows"]}
    assert rows["已开启定时任务"] == "未开启"
    assert "每日素材明细同步" in rows["已关闭定时任务"]

    saved = json.loads((tmp_path / "products" / "diandian-hero.local.json").read_text(encoding="utf-8"))
    assert saved["automation"]["material_daily_sync"]["enabled"] is False
    assert saved["automation"]["source_material_preload"]["enabled"] is False


def test_product_automation_overview_lists_closed_jobs(tmp_path: Path):
    configs_dir = tmp_path / "configs"
    product_dir = configs_dir / "products"
    product_dir.mkdir(parents=True)
    product_dir.joinpath("diandian-hero.local.json").write_text(
        json.dumps(
            {
                **_save_body(["daily_report_sync"]),
                "automation": {
                    "enabled": True,
                    "daily_report_sync": {"enabled": True},
                    "material_daily_sync": {"enabled": False},
                    "source_material_preload": {"enabled": False},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_product_automation_overview(project_root=tmp_path, configs_dir=configs_dir, runs_dir=tmp_path / "runs")
    row = result["table"]["rows"][0]

    assert row["已开启定时任务"] == "每日报表同步"
    assert "每日素材明细同步" in row["已关闭定时任务"]
    assert "源素材预推送" in row["已关闭定时任务"]


def test_product_automation_dry_run_says_job_is_closed(tmp_path: Path):
    configs_dir = tmp_path / "configs"
    product_dir = configs_dir / "products"
    product_dir.mkdir(parents=True)
    product_dir.joinpath("diandian-hero.local.json").write_text(
        json.dumps(
            {
                **_save_body([]),
                "automation": {
                    "enabled": True,
                    "material_daily_sync": {"enabled": False},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_product_automation_dry_run(
        project_root=tmp_path,
        configs_dir=configs_dir,
        runs_dir=tmp_path / "runs",
        product_key="diandian-hero",
        job="material_daily_sync",
        target_date="yesterday",
    )

    assert result["summary"]["status"] == "blocked"
    assert result["summary"]["blocking_reasons"] == ["点点英雄 已关闭“每日素材明细同步”，不会生成这个定时任务请求。"]
