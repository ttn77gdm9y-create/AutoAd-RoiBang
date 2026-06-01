import importlib.util
import json
from pathlib import Path

from roibang_v2.workflows.ai_template_draft_promote import promote_ai_template_draft_preview


def _preview_payload() -> dict:
    return {
        "ok": True,
        "workflow": "ai_template_draft_promotion_preview",
        "phase": "preview",
        "status": "preview_only",
        "execution_enabled": False,
        "external_api_calls": 0,
        "product_key": "demo-game",
        "product": "演示游戏",
        "draft_key": "ai_wx_pay_general_recent_scale_cost500_v1",
        "draft_name": "AI 每付通投近期放量 消耗500草稿",
        "target_path": "configs/create-modes/demo-game/ai_wx_pay_general_recent_scale_cost500_v1.local.json",
        "summary": {
            "title": "AI 模板草稿转正预览",
            "中文摘要": "为产品 演示游戏 的草稿生成转正预览 JSON；不写入人工固定模板，不执行真实创建。",
        },
        "proposed_create_mode": {
            "mode_key": "ai_wx_pay_general_recent_scale_cost500_v1",
            "display_name": "AI 每付通投近期放量 消耗500草稿",
            "product_key": "demo-game",
            "product": "演示游戏",
            "platform": "WECHAT_GAME",
            "template_key": "wx_pay_general",
            "template_name_suffix": "AI 每付通投近期放量 消耗500草稿",
            "source_advertiser_id": "source-1",
            "organization_id": "org-1",
            "defaults": {"daily_budget": 10000, "cpa_bid": 111},
            "material_requirements": {"materials_per_unit": 6},
            "material_selection": {"lookback_days": 7, "selection_type": "high_spend", "min_stat_cost": 500},
        },
        "execution": {"enabled": False, "status": "preview_only", "real_business_action": False},
        "actions": [],
    }


def _write_preview(tmp_path: Path) -> Path:
    preview_path = tmp_path / "runs" / "ai_template_draft_preview" / "preview.json"
    preview_path.parent.mkdir(parents=True)
    preview_path.write_text(json.dumps(_preview_payload(), ensure_ascii=False), encoding="utf-8")
    return preview_path


def test_promote_ai_template_draft_preview_writes_create_mode_and_artifact(tmp_path: Path):
    preview_path = _write_preview(tmp_path)
    mode_dir = tmp_path / "configs" / "create-modes"

    result = promote_ai_template_draft_preview(
        preview_path=preview_path,
        mode_dir=mode_dir,
        runs_dir=tmp_path / "runs",
    )

    target = mode_dir / "demo-game" / "ai_wx_pay_general_recent_scale_cost500_v1.local.json"
    assert result["ok"] is True
    assert result["workflow"] == "ai_template_draft_promote"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "promoted"
    assert result["summary"]["中文摘要"] == "AI 模板草稿已写入本地创建模式：演示游戏 / ai_wx_pay_general_recent_scale_cost500_v1。"
    assert result["summary"]["target_path"] == str(target)
    assert result["actions"] == []
    assert Path(result["artifact_path"]).exists()
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert saved["product"] == "演示游戏"
    assert saved["product_key"] == "demo-game"
    assert saved["mode_key"] == "ai_wx_pay_general_recent_scale_cost500_v1"


def test_promote_ai_template_draft_preview_blocks_existing_target_without_replace(tmp_path: Path):
    preview_path = _write_preview(tmp_path)
    mode_dir = tmp_path / "configs" / "create-modes"
    target = mode_dir / "demo-game" / "ai_wx_pay_general_recent_scale_cost500_v1.local.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"mode_key": "old", "product": "旧配置"}, ensure_ascii=False), encoding="utf-8")

    result = promote_ai_template_draft_preview(
        preview_path=preview_path,
        mode_dir=mode_dir,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "target already exists" in result["blocking_reasons"]
    assert json.loads(target.read_text(encoding="utf-8"))["product"] == "旧配置"


def test_run_ai_template_draft_promote_script_writes_create_mode(tmp_path: Path, capsys):
    preview_path = _write_preview(tmp_path)
    script_path = Path("scripts/run_ai_template_draft_promote.py")
    spec = importlib.util.spec_from_file_location("run_ai_template_draft_promote", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    code = module.run_from_args(
        [
            "--preview",
            str(preview_path),
            "--mode-dir",
            str(tmp_path / "configs" / "create-modes"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["ok"] is True
    assert output["workflow"] == "ai_template_draft_promote"
    assert output["summary"]["真实执行"] == "否"
