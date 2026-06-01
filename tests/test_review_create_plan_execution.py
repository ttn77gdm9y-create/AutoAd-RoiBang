import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.review_create_plan_execution import build_create_plan_execution_review
from roibang_v2.workflows.review_create_plan_execution import run_create_plan_execution_review_request
from tests.test_create_plan_review import _plan


def _source_preview(*, project_capacity: int = 1, qualified_material_count: int = 3) -> dict:
    return {
        "workflow": "create_plan_from_suggestions",
        "status": "preview_only",
        "summary": {"source_suggestion_count": 1, "account_count": 1},
        "suggestion_groups": [
            {
                "group_id": "create-plan-group-1",
                "strategy_ids": ["stage4-capacity-v1"],
                "account_count": 1,
            }
        ],
        "source_suggestions": [
            {
                "suggestion_id": "create-acc-1",
                "suggested_action": "suggest_create_project",
                "product_key": "diandian-hero",
                "product_name": "点点英雄",
                "advertiser_id": "acc-1",
                "account_name": "账户一",
                "mode_key": "wx_pay_male_random_materials",
                "strategy_id": "stage4-capacity-v1",
                "metrics": {
                    "project_capacity": project_capacity,
                    "qualified_material_count": qualified_material_count,
                    "convert_cnt": 6,
                    "roi_1day": 1.2,
                },
                "reason": "账户容量和素材满足扩量条件。",
            }
        ],
    }


def test_create_plan_execution_review_allows_warning_plan_with_source_evidence():
    result = build_create_plan_execution_review(
        _plan(),
        {"operator": "运营A"},
        plan_path="data/runs/create_mode/plan-1.json",
        review_config={"checks": {"min_qualified_material_count": 1}},
        source_suggestion_preview_artifact=_source_preview(),
        source_suggestion_preview_path="data/runs/create_plan_from_suggestions/source.json",
    )

    assert result["ok"] is True
    assert result["status"] == "warning_only"
    assert result["execution_enabled"] is False
    assert result["summary"]["batch_name"] == "2026-05-26 点点英雄 每付男素材不限 批次 01"
    assert result["summary"]["source_strategy_ids"] == ["stage4-capacity-v1"]
    assert result["risk_summary"]["blockers"] == 0
    assert result["risk_summary"]["warnings"] == 1
    assert result["execution_manifest"]["can_confirm_execution"] is True
    assert result["operation_record"]["source_suggestion_ids"] == ["create-acc-1"]


def test_create_plan_execution_review_blocks_when_source_capacity_is_insufficient():
    result = build_create_plan_execution_review(
        _plan(),
        {"operator": "运营A"},
        plan_path="data/runs/create_mode/plan-1.json",
        review_config={"checks": {"min_qualified_material_count": 1}},
        source_suggestion_preview_artifact=_source_preview(project_capacity=0),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert any("容量 0 < 计划项目 1" in reason for reason in result["blocking_reasons"])


def test_create_plan_execution_review_blocks_duplicate_plan_ledger(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO create_provider_id_ledger (
              entity_type, local_key, provider_id, plan_id, request_id, advertiser_id,
              parent_local_key, status, source_workflow, execution_enabled,
              response_payload_json, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "project",
                "acc-1-p001",
                "project-real-1",
                "plan-1",
                "",
                "acc-1",
                "",
                "active",
                "create_live_execute_once",
                0,
                "{}",
                "2026-05-31T00:00:00Z",
                "2026-05-31T00:00:00Z",
            ),
        )

    result = build_create_plan_execution_review(
        _plan(),
        {"operator": "运营A"},
        plan_path="data/runs/create_mode/plan-1.json",
        db_path=db_path,
        source_suggestion_preview_artifact=_source_preview(),
    )

    assert result["status"] == "blocked"
    assert any("本地账本已存在计划 plan-1" in reason for reason in result["blocking_reasons"])


def test_run_create_plan_execution_review_request_writes_artifact(tmp_path: Path):
    plan_path = tmp_path / "data" / "runs" / "create_mode" / "plan-1.json"
    source_path = tmp_path / "data" / "runs" / "create_plan_from_suggestions" / "source.json"
    plan_path.parent.mkdir(parents=True)
    source_path.parent.mkdir(parents=True)
    plan_path.write_text(json.dumps(_plan(), ensure_ascii=False), encoding="utf-8")
    source_path.write_text(json.dumps(_source_preview(), ensure_ascii=False), encoding="utf-8")

    result = run_create_plan_execution_review_request(
        {
            "plan_path": "data/runs/create_mode/plan-1.json",
            "source_suggestion_preview_path": "data/runs/create_plan_from_suggestions/source.json",
            "operator": "运营A",
        },
        runs_dir=tmp_path / "data" / "runs",
        project_root=tmp_path,
    )

    assert result["status"] == "warning_only"
    assert Path(result["artifact_path"]).exists()
