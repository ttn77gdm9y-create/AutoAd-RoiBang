import json
from pathlib import Path

from roibang_v2.workflows.create_suggestion_lifecycle import build_create_suggestion_lifecycle


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _suggestions_artifact() -> dict:
    return {
        "workflow": "rule_suggestions",
        "summary": {"target_date": "2026-05-31"},
        "suggestions": [
            {
                "suggestion_id": "create-1001",
                "suggested_action": "suggest_create_project",
                "product_key": "demo-game",
                "product_name": "演示游戏",
                "advertiser_id": "1001",
                "account_name": "演示账户一",
                "mode_key": "wx_pay_general_recent_scale",
                "strategy_id": "recent-scale-capacity-v1",
            },
            {
                "suggestion_id": "create-1002",
                "suggested_action": "suggest_create_project",
                "product_key": "demo-game",
                "product_name": "演示游戏",
                "advertiser_id": "1002",
                "account_name": "演示账户二",
                "mode_key": "wx_pay_general_recent_scale",
                "strategy_id": "recent-scale-capacity-v1",
            },
        ],
    }


def test_create_suggestion_lifecycle_locks_suggestion_after_execution_submission(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs"
    review_path = runs_dir / "create_plan_execution_review" / "review.json"
    _write_json(
        runs_dir / "create_plan_from_suggestions" / "preview.json",
        {
            "workflow": "create_plan_from_suggestions",
            "status": "preview_only",
            "generated_at": "2026-05-31T01:00:00+00:00",
            "source": {"source_suggestion_ids": ["create-1001"]},
            "source_suggestions": [_suggestions_artifact()["suggestions"][0]],
        },
    )
    _write_json(
        review_path,
        {
            "workflow": "create_plan_execution_review",
            "status": "warning_only",
            "generated_at": "2026-05-31T02:00:00+00:00",
            "operation_record": {
                "plan_id": "plan-1",
                "plan_path": "data/runs/create_mode/plan-1.json",
                "source_suggestion_ids": ["create-1001"],
                "source_strategy_ids": ["recent-scale-capacity-v1"],
            },
            "warnings": ["唯一素材数较少"],
        },
    )
    _write_json(
        runs_dir / "frontend_operation_log" / "execute.json",
        {
            "workflow": "frontend_operation_log",
            "operation_type": "create_live_execute",
            "status": "queued",
            "task_id": "task-create-1",
            "created_at": "2026-05-31T03:00:00+00:00",
            "request": {
                "execution_review_artifact_path": "data/runs/create_plan_execution_review/review.json",
            },
            "result": {"plan_id": "plan-1"},
            "details": {"plan_id": "plan-1"},
        },
    )

    result = build_create_suggestion_lifecycle(
        runs_dir=runs_dir,
        project_root=tmp_path,
        suggestions_artifact=_suggestions_artifact(),
        suggestions_artifact_path="data/runs/rule_suggestions/latest.json",
        product_key="demo-game",
    )

    first = result["by_suggestion_id"]["create-1001"]
    second = result["by_suggestion_id"]["create-1002"]
    assert first["lifecycle_status"] == "execution_submitted"
    assert first["locked_for_create_plan"] is True
    assert first["execution_task_id"] == "task-create-1"
    assert first["plan_preview_path"] == "data/runs/create_plan_from_suggestions/preview.json"
    assert first["execution_review_path"] == "data/runs/create_plan_execution_review/review.json"
    assert second["lifecycle_status"] == "unprocessed"
    assert second["locked_for_create_plan"] is False
    assert result["summary"]["locked_suggestion_count"] == 1


def test_create_suggestion_lifecycle_review_blocked_is_not_locked(tmp_path: Path):
    runs_dir = tmp_path / "data" / "runs"
    _write_json(
        runs_dir / "create_plan_execution_review" / "blocked.json",
        {
            "workflow": "create_plan_execution_review",
            "status": "blocked",
            "generated_at": "2026-05-31T02:00:00+00:00",
            "operation_record": {
                "plan_id": "plan-1",
                "source_suggestion_ids": ["create-1001"],
            },
            "blocking_reasons": ["素材不足"],
        },
    )

    result = build_create_suggestion_lifecycle(
        runs_dir=runs_dir,
        project_root=tmp_path,
        suggestions_artifact=_suggestions_artifact(),
        product_key="demo-game",
    )

    record = result["by_suggestion_id"]["create-1001"]
    assert record["lifecycle_status"] == "reviewed_blocked"
    assert record["locked_for_create_plan"] is False
    assert record["blocking_reasons"] == ["素材不足"]
