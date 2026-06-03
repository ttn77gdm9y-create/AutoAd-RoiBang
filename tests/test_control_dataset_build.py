import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.control_dataset_build import (
    build_control_operation_dataset,
    build_operation_log_sync_plan_from_metrics,
    discover_control_metric_scope,
    run_control_dataset_build_request,
    run_control_operation_log_history_sync_request,
)


def _insert_metric(
    conn: sqlite3.Connection,
    *,
    metric_date: str,
    advertiser_id: str,
    project_id: str = "project-1",
    promotion_id: str = "promotion-1",
    material_id: str = "material-1",
    cost: float = 0,
    conversions: float = 0,
    roi_1day: float = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, project_name,
          promotion_id, promotion_name, material_id, material_kind,
          stat_cost, show_cnt, click_cnt, convert_cnt, roi_1day,
          source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metric_date,
            advertiser_id,
            project_id,
            f"{project_id}-name",
            promotion_id,
            f"{promotion_id}-name",
            material_id,
            "video",
            cost,
            cost * 10,
            cost,
            conversions,
            roi_1day,
            "unit_test",
            "2026-05-11T00:00:00+08:00",
        ),
    )


def _insert_account_pool(
    conn: sqlite3.Connection,
    *,
    advertiser_id: str,
    account_name: str,
    product: str,
    platform: str = "WECHAT_GAME",
) -> None:
    conn.execute(
        """
        INSERT INTO account_pool (
          advertiser_id, account_name, product, platform, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            advertiser_id,
            account_name,
            product,
            platform,
            "unit_test",
            "2026-05-11T00:00:00+08:00",
        ),
    )


def test_control_scope_uses_accounts_and_date_range_from_material_daily_metrics(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, metric_date="2026-05-02", advertiser_id="a2", cost=20)
        _insert_metric(conn, metric_date="2026-05-01", advertiser_id="a1", cost=10)
        _insert_metric(conn, metric_date="2026-05-03", advertiser_id="a1", cost=30)

    scope = discover_control_metric_scope(db_path)

    assert scope["account_source"] == "material_daily_metrics"
    assert scope["date_range_source"] == "material_daily_metrics"
    assert scope["date_range"] == {"start": "2026-05-01", "end": "2026-05-03", "days": 3}
    assert scope["accounts"] == [
        {"advertiser_id": "a1", "account_name": "", "product": "", "platform": "WECHAT_GAME"},
        {"advertiser_id": "a2", "account_name": "", "product": "", "platform": "WECHAT_GAME"},
    ]
    assert scope["metric_row_count"] == 3


def test_operation_log_sync_plan_is_built_from_metric_scope(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, metric_date="2026-05-01", advertiser_id="a1", cost=10)
        _insert_metric(conn, metric_date="2026-05-03", advertiser_id="a2", cost=20)

    payload = build_operation_log_sync_plan_from_metrics(db_path, page_size=20)
    plan = payload["plan"]

    assert payload["summary"]["account_source"] == "material_daily_metrics"
    assert payload["summary"]["account_date_source"] == "material_daily_metrics_spent_account_dates"
    assert payload["summary"]["date_range"] == {"start": "2026-05-01", "end": "2026-05-03", "days": 3}
    assert payload["summary"]["account_count"] == 2
    assert payload["summary"]["account_date_count"] == 2
    assert payload["summary"]["planned_request_count"] == 2
    assert {request["endpoint_key"] for request in plan["requests"]} == {"operation_log_search"}
    assert plan["requests"][0]["query_params"]["advertiser_id"] == "a1"
    assert plan["requests"][0]["query_params"]["start_time"] == "2026-05-01 00:00:00"
    assert plan["requests"][0]["query_params"]["end_time"] == "2026-05-01 23:59:59"
    assert plan["requests"][1]["query_params"]["advertiser_id"] == "a2"
    assert plan["requests"][1]["query_params"]["start_time"] == "2026-05-03 00:00:00"


def test_operation_log_sync_plan_can_limit_to_latest_metric_window(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, metric_date="2026-05-01", advertiser_id="a1", cost=10)
        _insert_metric(conn, metric_date="2026-05-02", advertiser_id="a1", cost=0)
        _insert_metric(conn, metric_date="2026-05-03", advertiser_id="a2", cost=20)
        _insert_metric(conn, metric_date="2026-05-04", advertiser_id="a1", cost=30)

    payload = build_operation_log_sync_plan_from_metrics(db_path, page_size=20, window_days=2)
    requests = payload["plan"]["requests"]

    assert payload["summary"]["metric_scope_date_range"] == {"start": "2026-05-01", "end": "2026-05-04", "days": 4}
    assert payload["summary"]["date_range"] == {"start": "2026-05-03", "end": "2026-05-04", "days": 2}
    assert payload["summary"]["sync_window_days"] == 2
    assert payload["summary"]["planned_request_count"] == 2
    assert [(item["query_params"]["advertiser_id"], item["date"]) for item in requests] == [
        ("a2", "2026-05-03"),
        ("a1", "2026-05-04"),
    ]


def test_operation_log_sync_plan_can_target_yesterday_only(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, metric_date="2026-05-10", advertiser_id="a1", cost=10)
        _insert_metric(conn, metric_date="2026-05-11", advertiser_id="a1", cost=30)
        _insert_metric(conn, metric_date="2026-05-11", advertiser_id="a2", cost=0)

    payload = build_operation_log_sync_plan_from_metrics(
        db_path,
        page_size=20,
        date_range={"mode": "yesterday", "today": "2026-05-12"},
    )
    requests = payload["plan"]["requests"]

    assert payload["summary"]["date_range_mode"] == "yesterday"
    assert payload["summary"]["date_range"] == {"start": "2026-05-11", "end": "2026-05-11", "days": 1}
    assert payload["summary"]["planned_request_count"] == 1
    assert [(item["query_params"]["advertiser_id"], item["date"]) for item in requests] == [
        ("a1", "2026-05-11"),
    ]


def test_operation_log_sync_plan_uses_all_spent_product_accounts_for_target_date(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(1, 21):
            advertiser_id = f"diandian-{index:02d}"
            _insert_account_pool(
                conn,
                advertiser_id=advertiser_id,
                account_name=f"黑旗-点点英雄-微小-傲星-{index}",
                product="点点英雄",
            )
            _insert_metric(
                conn,
                metric_date="2026-06-02",
                advertiser_id=advertiser_id,
                material_id=f"material-{index}",
                cost=10 + index,
            )
        _insert_account_pool(
            conn,
            advertiser_id="other-product",
            account_name="黑旗-其他游戏-微小-傲星-1",
            product="其他游戏",
        )
        _insert_metric(
            conn,
            metric_date="2026-06-02",
            advertiser_id="other-product",
            material_id="other-material",
            cost=99,
        )

    payload = build_operation_log_sync_plan_from_metrics(
        db_path,
        page_size=20,
        product_keyword="点点英雄",
        date_range={"target_date": "2026-06-02"},
    )
    requests = payload["plan"]["requests"]

    assert payload["summary"]["account_source"] == "material_daily_metrics"
    assert payload["summary"]["account_date_source"] == "material_daily_metrics_spent_account_dates"
    assert payload["summary"]["date_range"] == {"start": "2026-06-02", "end": "2026-06-02", "days": 1}
    assert payload["summary"]["account_count"] == 20
    assert payload["summary"]["planned_request_count"] == 20
    assert {request["query_params"]["advertiser_id"] for request in requests} == {
        f"diandian-{index:02d}" for index in range(1, 21)
    }


def test_control_scope_filters_product_keyword_by_account_name_and_product_not_project_name(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(
            conn,
            advertiser_id="a1",
            account_name="黑旗-勇者突进-微小-傲星-1",
            product="勇者突进",
        )
        _insert_account_pool(
            conn,
            advertiser_id="a2",
            account_name="黑旗-其他产品-微小-傲星-2",
            product="其他产品",
        )
        _insert_metric(conn, metric_date="2026-05-01", advertiser_id="a1", project_id="BL-勇者-每次-0210", cost=10)
        _insert_metric(conn, metric_date="2026-05-02", advertiser_id="a2", project_id="勇者突进误写项目", cost=20)

    scope = discover_control_metric_scope(db_path, product_keyword="勇者突进")

    assert scope["filter"] == {"product_keyword": "勇者突进"}
    assert scope["date_range"] == {"start": "2026-05-01", "end": "2026-05-01", "days": 1}
    assert scope["accounts"] == [
        {
            "advertiser_id": "a1",
            "account_name": "黑旗-勇者突进-微小-傲星-1",
            "product": "勇者突进",
            "platform": "WECHAT_GAME",
        }
    ]


def test_control_operation_dataset_joins_operation_logs_with_before_after_project_metrics(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO operation_logs (
              operation_id, occurred_at, advertiser_id, entity_type, entity_id,
              action, operator, detail, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "op-1",
                "2026-05-03 12:00:00",
                "a1",
                "project",
                "project-1",
                "暂停项目",
                "operator",
                "状态: 开启 -> 暂停",
                "unit_test",
                "2026-05-11T00:00:00+08:00",
            ),
        )
        _insert_metric(conn, metric_date="2026-05-01", advertiser_id="a1", cost=100, conversions=1, roi_1day=0.10)
        _insert_metric(conn, metric_date="2026-05-02", advertiser_id="a1", cost=300, conversions=3, roi_1day=0.30)
        _insert_metric(conn, metric_date="2026-05-03", advertiser_id="a1", cost=200, conversions=2, roi_1day=0.20)
        _insert_metric(conn, metric_date="2026-05-04", advertiser_id="a1", cost=50, conversions=1, roi_1day=0.50)
        _insert_metric(conn, metric_date="2026-05-05", advertiser_id="a1", cost=150, conversions=1, roi_1day=0.10)
        _insert_metric(conn, metric_date="2026-05-02", advertiser_id="a1", project_id="other", cost=999, conversions=9)

    dataset = build_control_operation_dataset(db_path, window_days=3)

    assert dataset["summary"]["operation_count"] == 1
    row = dataset["rows"][0]
    assert row["operation_id"] == "op-1"
    assert row["entity_type"] == "project"
    assert row["before_3d"]["stat_cost"] == 400
    assert row["before_3d"]["convert_cnt"] == 4
    assert row["before_3d"]["cpa"] == 100
    assert row["before_3d"]["roi_1day_cost_weighted"] == 0.25
    assert row["event_day"]["stat_cost"] == 200
    assert row["after_3d"]["stat_cost"] == 200
    assert row["after_3d"]["convert_cnt"] == 2
    assert row["after_3d"]["roi_1day_cost_weighted"] == 0.2


def test_run_control_dataset_build_request_writes_artifact_without_external_calls(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_metric(conn, metric_date="2026-05-01", advertiser_id="a1", cost=10)

    result = run_control_dataset_build_request(
        {"window_days": 2},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["account_source"] == "material_daily_metrics"
    assert result["summary"]["planned_operation_log_request_count"] == 1
    assert Path(result["artifact_path"]).exists()


def test_run_control_dataset_build_writes_large_rows_to_jsonl_and_keeps_artifact_compact(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        for idx in range(3):
            operation_id = f"op-{idx}"
            entity_id = f"project-{idx}"
            conn.execute(
                """
                INSERT INTO operation_logs (
                  operation_id, occurred_at, advertiser_id, entity_type, entity_id,
                  action, operator, detail, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    "2026-05-03 12:00:00",
                    "a1",
                    "project",
                    entity_id,
                    "暂停项目",
                    "operator",
                    "状态: 开启 -> 暂停",
                    "unit_test",
                    "2026-05-11T00:00:00+08:00",
                ),
            )
            _insert_metric(conn, metric_date="2026-05-02", advertiser_id="a1", project_id=entity_id, cost=100)

    result = run_control_dataset_build_request(
        {"window_days": 2, "row_sample_limit": 1},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    rows_path = Path(result["operation_metric_dataset_rows_path"])
    request_rows_path = Path(result["operation_log_sync_plan_requests_path"])
    artifact = json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))
    assert rows_path.exists()
    assert request_rows_path.exists()
    assert len(rows_path.read_text(encoding="utf-8").strip().splitlines()) == 3
    assert len(request_rows_path.read_text(encoding="utf-8").strip().splitlines()) == 1
    assert result["operation_metric_dataset"]["summary"]["operation_count"] == 3
    assert len(result["operation_metric_dataset"]["rows"]) == 1
    assert len(result["operation_log_sync_plan"]["request_sample"]) == 1
    assert "requests" not in result["operation_log_sync_plan"]
    assert len(artifact["operation_metric_dataset"]["rows"]) == 1
    assert artifact["operation_metric_dataset_rows_path"] == str(rows_path)
    assert artifact["operation_log_sync_plan_requests_path"] == str(request_rows_path)


def test_operation_log_history_sync_imports_logs_and_builds_control_dataset(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_account_pool(
            conn,
            advertiser_id="a1",
            account_name="黑旗-勇者突进-微小-傲星-1",
            product="勇者突进",
        )
        _insert_metric(
            conn,
            metric_date="2026-05-01",
            advertiser_id="a1",
            project_id="勇者突进项目",
            cost=100,
            conversions=1,
            roi_1day=0.2,
        )

    calls = []

    def transport(request: dict) -> dict:
        calls.append(request["query_params"]["advertiser_id"])
        return {
            "code": 0,
            "data": {
                "logs": [
                    {
                        "request_id": "op-a1-1",
                        "create_time": "2026-05-01 10:00:00",
                        "object_type": "项目",
                        "object_id": "勇者突进项目",
                        "content_title": "暂停项目",
                        "content_log": ["状态: 开启 -> 暂停"],
                        "operator": "tester",
                    }
                ],
                "page_info": {"page": 1, "page_size": 20, "total_page": 1},
            },
        }

    result = run_control_operation_log_history_sync_request(
        {
            "product_keyword": "勇者突进",
            "operation_log_page_size": 20,
            "openapi_http": {"enabled": True},
            "execution": {"status": "execute", "external_api_enabled": True},
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        transport=transport,
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["summary"]["planned_request_count"] == 1
    assert result["summary"]["transport_calls"] == 1
    assert result["summary"]["operation_logs_imported"] == 1
    assert result["summary"]["control_dataset_operation_count"] == 1
    assert calls == ["a1"]
    assert Path(result["artifact_path"]).exists()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT operation_id, entity_type, entity_id, action FROM operation_logs"
        ).fetchone()
    assert row == ("op-a1-1", "project", "勇者突进项目", "暂停项目")
