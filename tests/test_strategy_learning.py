import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.strategy_learning import build_strategy_learning_artifact, run_strategy_learning_request


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_product_configs(tmp_path: Path) -> Path:
    products_dir = tmp_path / "configs" / "products"
    _write_json(
        products_dir / "diandian-hero.local.json",
        {
            "product_key": "diandian-hero",
            "product": "点点英雄",
            "platform": "WECHAT_GAME",
            "automation": {"enabled": True},
        },
    )
    _write_json(
        products_dir / "yzt-wechat-mini-game.local.json",
        {
            "product_key": "yzt-wechat-mini-game",
            "product": "勇者突进",
            "platform": "WECHAT_GAME",
            "automation": {"enabled": True},
        },
    )
    return products_dir


def _insert_account(conn: sqlite3.Connection, advertiser_id: str, account_name: str, product: str) -> None:
    conn.execute(
        """
        INSERT INTO account_pool (advertiser_id, account_name, product, platform, source, synced_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (advertiser_id, account_name, product, "WECHAT_GAME", "unit_test", "2026-06-01T00:00:00+08:00"),
    )


def _insert_project(conn: sqlite3.Connection, advertiser_id: str, project_id: str, project_name: str) -> None:
    conn.execute(
        """
        INSERT INTO projects (project_id, advertiser_id, name, status, source, synced_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, advertiser_id, project_name, "PROJECT_STATUS_ENABLE", "unit_test", "2026-06-01T00:00:00+08:00"),
    )


def _insert_hourly_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    metric_hour: int,
    advertiser_id: str,
    project_id: str,
    project_name: str,
    cost: float,
    convert: float,
    roi: float,
) -> None:
    conn.execute(
        """
        INSERT INTO project_hourly_metrics (
          metric_date, metric_hour, advertiser_id, project_id, project_name,
          stat_cost, show_cnt, click_cnt, convert_cnt, roi_1day, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (metric_date, metric_hour, advertiser_id, project_id, project_name, cost, 1000, 100, convert, roi, "unit_test", "now"),
    )


def _insert_daily_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    advertiser_id: str,
    project_id: str,
    project_name: str,
    cost: float,
    convert: float,
    roi: float,
) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, project_name, promotion_id, promotion_name,
          material_id, material_kind, stat_cost, convert_cnt, roi_1day, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric_date,
            advertiser_id,
            project_id,
            project_name,
            f"unit-{project_id}",
            "单元",
            f"material-{project_id}",
            "video",
            cost,
            convert,
            roi,
            "unit_test",
            "now",
        ),
    )


def _insert_operation(
    conn: sqlite3.Connection,
    *,
    operation_id: str,
    occurred_at: str,
    advertiser_id: str,
    project_id: str,
    action: str,
    detail: str,
) -> None:
    conn.execute(
        """
        INSERT INTO operation_logs (
          operation_id, occurred_at, advertiser_id, entity_type, entity_id, action, detail, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (operation_id, occurred_at, advertiser_id, "project", project_id, action, detail, "unit_test", "now"),
    )


def _insert_budget_learning_rows(conn: sqlite3.Connection, *, product: str, product_prefix: str, count: int) -> None:
    for index in range(count):
        advertiser_id = f"{product_prefix}-acc-{index:03d}"
        project_id = f"{product_prefix}-project-{index:03d}"
        project_name = f"{product}-降预算样本-{index:03d}"
        _insert_account(conn, advertiser_id, f"{product}-账户-{index:03d}", product)
        _insert_project(conn, advertiser_id, project_id, project_name)
        _insert_hourly_metric(
            conn,
            metric_date="2026-05-20",
            metric_hour=10,
            advertiser_id=advertiser_id,
            project_id=project_id,
            project_name=project_name,
            cost=1000 + index,
            convert=3 + index % 3,
            roi=0.05 + (index % 4) * 0.01,
        )
        _insert_daily_metric(
            conn,
            metric_date="2026-05-21",
            advertiser_id=advertiser_id,
            project_id=project_id,
            project_name=project_name,
            cost=500 + index,
            convert=2,
            roi=0.08,
        )
        _insert_operation(
            conn,
            operation_id=f"op-budget-{product_prefix}-{index:03d}",
            occurred_at="2026-05-20 11:00:00",
            advertiser_id=advertiser_id,
            project_id=project_id,
            action="修改",
            detail="修改 项目预算: 1000 -> 800",
        )


def test_strategy_learning_builds_cross_product_and_product_candidates(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    products_dir = _write_product_configs(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_budget_learning_rows(conn, product="勇者突进", product_prefix="yzt", count=30)
        _insert_budget_learning_rows(conn, product="点点英雄", product_prefix="hero", count=5)
        _insert_account(conn, "hero-pause-acc", "点点英雄-暂停账户", "点点英雄")
        _insert_project(conn, "hero-pause-acc", "hero-pause-project", "点点英雄-暂停样本")
        _insert_hourly_metric(
            conn,
            metric_date="2026-05-20",
            metric_hour=9,
            advertiser_id="hero-pause-acc",
            project_id="hero-pause-project",
            project_name="点点英雄-暂停样本",
            cost=1200,
            convert=0,
            roi=0,
        )
        _insert_operation(
            conn,
            operation_id="op-pause-hero-001",
            occurred_at="2026-05-20 10:00:00",
            advertiser_id="hero-pause-acc",
            project_id="hero-pause-project",
            action="修改",
            detail="修改 启停状态: 启用 -> 暂停",
        )

    artifact = build_strategy_learning_artifact(
        db_path=db_path,
        policy={
            "target_date": "2026-06-01",
            "lookback_days": 45,
            "products_dir": str(products_dir),
        },
    )

    assert artifact["ok"] is True
    assert artifact["execution_enabled"] is False
    assert artifact["external_api_calls"] == 0
    assert artifact["runtime_contract"]["runtime_metric_source"] == "realtime_patrol_snapshot"
    assert artifact["runtime_contract"]["allow_builtin_default_project_actions"] is False
    assert artifact["summary"]["learning_sample_count"] == 36
    assert artifact["summary"]["action_counts"]["suggest_lower_budget"] == 35
    candidates = artifact["candidate_strategies"]

    cross_budget = next(
        item for item in candidates if item["action"] == "suggest_lower_budget" and item["scope"]["type"] == "cross_product"
    )
    hero_budget = next(
        item for item in candidates if item["action"] == "suggest_lower_budget" and item["scope"]["product_key"] == "diandian-hero"
    )
    hero_pause = next(
        item for item in candidates if item["action"] == "pause_project" and item["scope"]["product_key"] == "diandian-hero"
    )
    assert cross_budget["status"] == "candidate_requires_review"
    assert hero_budget["status"] == "candidate_requires_review"
    assert hero_budget["enabled"] is False
    assert hero_budget["sample_counts"] == {"total": 35, "product": 5, "with_pre_metrics": 5}
    assert "候选门槛" in hero_budget["中文摘要"]
    assert hero_budget["evidence_samples"][0]["account_name"].startswith("点点英雄-账户")
    assert hero_budget["evidence_samples"][0]["advertiser_id"].startswith("hero-acc")
    assert hero_pause["status"] == "insufficient_samples_readonly"
    assert "低于最低 80 条" in "；".join(hero_pause["blocking_reasons"])


def test_strategy_learning_classifies_create_project_before_budget_fields(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    products_dir = _write_product_configs(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account(conn, "hero-create-acc", "点点英雄-创建账户", "点点英雄")
        _insert_project(conn, "hero-create-acc", "hero-create-project", "点点英雄-创建样本")
        _insert_operation(
            conn,
            operation_id="op-create-hero-001",
            occurred_at="2026-05-20 10:00:00",
            advertiser_id="hero-create-acc",
            project_id="hero-create-project",
            action="新建",
            detail="出价方式: 按展示付费(oCPM)\n项目预算: 1000\n启停状态: 启用",
        )
        _insert_account(conn, "hero-copy-acc", "点点英雄-复制账户", "点点英雄")
        _insert_project(conn, "hero-copy-acc", "hero-copy-project", "点点英雄-复制样本")
        _insert_operation(
            conn,
            operation_id="op-copy-hero-001",
            occurred_at="2026-05-20 10:01:00",
            advertiser_id="hero-copy-acc",
            project_id="hero-copy-project",
            action="复制",
            detail="复制项目，项目预算: 1000，出价方式: 按展示付费(oCPM)",
        )
        _insert_account(conn, "hero-budget-acc", "点点英雄-预算账户", "点点英雄")
        _insert_project(conn, "hero-budget-acc", "hero-budget-project", "点点英雄-预算样本")
        _insert_hourly_metric(
            conn,
            metric_date="2026-05-20",
            metric_hour=10,
            advertiser_id="hero-budget-acc",
            project_id="hero-budget-project",
            project_name="点点英雄-预算样本",
            cost=1200,
            convert=3,
            roi=0.05,
        )
        _insert_operation(
            conn,
            operation_id="op-budget-hero-001",
            occurred_at="2026-05-20 11:00:00",
            advertiser_id="hero-budget-acc",
            project_id="hero-budget-project",
            action="修改",
            detail="修改 项目预算: 1000 -> 800",
        )
        _insert_operation(
            conn,
            operation_id="op-budget-up-hero-001",
            occurred_at="2026-05-20 12:00:00",
            advertiser_id="hero-budget-acc",
            project_id="hero-budget-project",
            action="修改",
            detail="修改 项目预算: 1000 -> 1200",
        )

    artifact = build_strategy_learning_artifact(
        db_path=db_path,
        policy={
            "target_date": "2026-06-01",
            "lookback_days": 45,
            "products_dir": str(products_dir),
        },
    )

    assert artifact["summary"]["learning_sample_count"] == 3
    assert artifact["summary"]["action_counts"] == {"suggest_create_project": 2, "suggest_lower_budget": 1}
    samples = {sample["operation_id"]: sample for sample in artifact["samples"]}
    assert samples["op-create-hero-001"]["standard_action"] == "suggest_create_project"
    assert samples["op-copy-hero-001"]["standard_action"] == "suggest_create_project"
    assert samples["op-budget-hero-001"]["standard_action"] == "suggest_lower_budget"
    assert "op-budget-up-hero-001" not in samples


def test_strategy_learning_second_stage_generates_disabled_rule_preview(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    products_dir = _write_product_configs(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_budget_learning_rows(conn, product="勇者突进", product_prefix="yzt", count=30)
        _insert_budget_learning_rows(conn, product="点点英雄", product_prefix="hero", count=5)

    artifact = build_strategy_learning_artifact(
        db_path=db_path,
        policy={
            "target_date": "2026-06-01",
            "lookback_days": 45,
            "products_dir": str(products_dir),
            "second_stage_learning": {
                "enabled": True,
                "min_backtest_samples": 5,
                "min_backtest_positive_rate": 0.5,
                "min_metric_available_rate": 0.5,
            },
        },
    )

    hero_budget = next(
        item for item in artifact["candidate_strategies"] if item["action"] == "suggest_lower_budget" and item["scope"]["product_key"] == "diandian-hero"
    )
    assert artifact["summary"]["second_stage_learning_enabled"] is True
    assert artifact["summary"]["candidate_passed_backtest_count"] >= 1
    assert hero_budget["status"] == "candidate_passed_backtest"
    assert hero_budget["enabled"] is False
    assert hero_budget["control_strategy_rule"]["rule_id"] == "adjust_project_budget_low_roi"
    assert hero_budget["control_strategy_rule"]["enabled"] is False
    assert hero_budget["control_strategy_rule"]["review_required"] is True
    assert hero_budget["second_stage_learning"]["backtest"]["status"] == "passed"
    assert hero_budget["second_stage_learning"]["sample_segments"]["positive_conversion_count"] == 5
    assert "默认未启用" in hero_budget["control_strategy_rule"]["中文摘要"]


def test_strategy_learning_blocks_mixed_high_risk_samples(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    products_dir = _write_product_configs(tmp_path)
    with sqlite3.connect(db_path) as conn:
        for index, convert in enumerate([0, 2]):
            advertiser_id = f"hero-pause-acc-{index}"
            project_id = f"hero-pause-project-{index}"
            project_name = f"点点英雄-暂停混合样本-{index}"
            _insert_account(conn, advertiser_id, f"点点英雄-暂停账户-{index}", "点点英雄")
            _insert_project(conn, advertiser_id, project_id, project_name)
            _insert_hourly_metric(
                conn,
                metric_date="2026-05-20",
                metric_hour=9,
                advertiser_id=advertiser_id,
                project_id=project_id,
                project_name=project_name,
                cost=1200,
                convert=convert,
                roi=0.02,
            )
            _insert_daily_metric(
                conn,
                metric_date="2026-05-21",
                advertiser_id=advertiser_id,
                project_id=project_id,
                project_name=project_name,
                cost=200,
                convert=0,
                roi=0,
            )
            _insert_operation(
                conn,
                operation_id=f"op-pause-mixed-{index}",
                occurred_at="2026-05-20 10:00:00",
                advertiser_id=advertiser_id,
                project_id=project_id,
                action="修改",
                detail="修改 启停状态: 启用 -> 暂停",
            )

    artifact = build_strategy_learning_artifact(
        db_path=db_path,
        policy={
            "target_date": "2026-06-01",
            "lookback_days": 45,
            "products_dir": str(products_dir),
            "sample_standards": {
                "pause_project": {
                    "min_total_samples": 2,
                    "min_product_samples": 2,
                    "max_false_positive_rate": 0.1,
                }
            },
            "second_stage_learning": {
                "enabled": True,
                "min_backtest_samples": 1,
                "min_backtest_positive_rate": 0.5,
            },
        },
    )

    hero_pause = next(
        item for item in artifact["candidate_strategies"] if item["action"] == "pause_project" and item["scope"]["product_key"] == "diandian-hero"
    )
    assert hero_pause["status"] == "blocked_mixed_high_risk_samples"
    assert artifact["summary"]["blocked_mixed_high_risk_samples_count"] >= 1
    assert "有 1 条操作前已有转化" in "；".join(hero_pause["blocking_reasons"])
    assert "control_strategy_rule" not in hero_pause


def test_strategy_learning_request_writes_latest_and_disabled_candidate_configs(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    products_dir = _write_product_configs(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_budget_learning_rows(conn, product="勇者突进", product_prefix="yzt", count=30)
        _insert_budget_learning_rows(conn, product="点点英雄", product_prefix="hero", count=5)

    output_dir = tmp_path / "configs" / "learned-strategies"
    result = run_strategy_learning_request(
        {
            "strategy_learning": {
                "target_date": "2026-06-01",
                "lookback_days": 45,
                "products_dir": str(products_dir),
                "write_candidate_configs": True,
                "output_strategy_dir": str(output_dir),
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    artifact_path = Path(result["artifact_path"])
    latest_path = tmp_path / "runs" / "strategy_learning" / "latest.json"
    assert artifact_path.exists()
    assert latest_path.exists()
    assert json.loads(latest_path.read_text(encoding="utf-8"))["artifact_path"] == str(artifact_path)
    assert result["generated_strategy_config_paths"]
    hero_config = output_dir / "diandian-hero.learned.local.json"
    assert hero_config.exists()
    payload = json.loads(hero_config.read_text(encoding="utf-8"))
    assert payload["runtime_contract"]["runtime_metric_source"] == "realtime_patrol_snapshot"
    assert payload["runtime_contract"]["allow_builtin_default_project_actions"] is False
    assert payload["enabled"] is False
    assert payload["summary"]["strategy_count"] == len(payload["strategies"])
    assert payload["summary"]["enabled_strategy_count"] == 0
    assert payload["summary"]["中文摘要"].startswith("diandian-hero 本次生成")
    assert all(strategy["enabled"] is False for strategy in payload["strategies"])
