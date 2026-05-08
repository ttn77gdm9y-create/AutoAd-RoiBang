import json
import sqlite3
from pathlib import Path

from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.workflows.material_duplicate_analysis import run_material_duplicate_analysis_request


def _insert_profile(
    conn: sqlite3.Connection,
    *,
    material_id: str,
    signature: str = "",
    name: str = "",
    video_id: str = "",
    duration: float = 0,
) -> None:
    payload = {"material_id": material_id}
    if signature:
        payload["signature"] = signature
    conn.execute(
        """
        INSERT INTO material_profiles (
          material_id, canonical_material_key, material_kind, name, video_id,
          review_status, create_time, duration, cover_url, source_advertiser_id,
          payload_json, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            material_id,
            f"material:{material_id}",
            "video",
            name,
            video_id,
            "APPROVED",
            "",
            duration,
            "",
            "a1",
            json.dumps(payload, ensure_ascii=False),
            "unit_test",
            "2026-05-08T00:00:00+00:00",
        ),
    )


def _insert_rollup(conn: sqlite3.Connection, *, material_id: str, stat_cost: float) -> None:
    conn.execute(
        """
        INSERT INTO material_metric_rollups (
          window_key, window_days, period_start, period_end, canonical_material_key,
          material_id, material_kind, account_count, project_count, promotion_count,
          stat_cost, show_cnt, click_cnt, convert_cnt, active_register,
          roi_1day_cost_weighted, roi_7days_cost_weighted, source, synced_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "all_history",
            0,
            "2026-02-10",
            "2026-05-06",
            f"material:{material_id}",
            material_id,
            "video",
            1,
            1,
            1,
            stat_cost,
            0,
            0,
            0,
            0,
            0,
            0,
            "unit_test",
            "2026-05-08T00:00:00+00:00",
        ),
    )


def test_duplicate_analysis_groups_same_signature_without_merging_rollups(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_profile(conn, material_id="m1", signature="sig-a", name="勇者素材A.mp4", video_id="v1")
        _insert_profile(conn, material_id="m2", signature="sig-a", name="勇者素材A-重传.mp4", video_id="v2")
        _insert_profile(conn, material_id="m3", signature="sig-b", name="勇者素材B.mp4", video_id="v3")
        _insert_profile(conn, material_id="m4", name="无指纹素材.mp4", video_id="v4")
        for material_id, cost in [("m1", 100), ("m2", 300), ("m3", 50), ("m4", 10)]:
            _insert_rollup(conn, material_id=material_id, stat_cost=cost)

    result = run_material_duplicate_analysis_request(
        {"material_duplicate_analysis": {"rules": ["signature"], "min_group_size": 2}},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert result["external_api_calls"] == 0
    assert result["summary"]["duplicate_group_count"] == 1
    assert result["summary"]["duplicate_material_count"] == 2
    assert result["summary"]["rows_written"] == 2
    with sqlite3.connect(db_path) as conn:
        duplicate_rows = conn.execute(
            """
            SELECT duplicate_group_key, material_id, duplicate_rule,
                   confidence_label, signature, stat_cost_all_history
            FROM material_duplicate_candidates
            ORDER BY material_id
            """
        ).fetchall()
        rollup_rows = conn.execute(
            """
            SELECT canonical_material_key, material_id, stat_cost
            FROM material_metric_rollups
            ORDER BY material_id
            """
        ).fetchall()

    assert duplicate_rows == [
        ("signature:sig-a", "m1", "signature", "high", "sig-a", 100.0),
        ("signature:sig-a", "m2", "signature", "high", "sig-a", 300.0),
    ]
    assert rollup_rows == [
        ("material:m1", "m1", 100.0),
        ("material:m2", "m2", 300.0),
        ("material:m3", "m3", 50.0),
        ("material:m4", "m4", 10.0),
    ]


def test_duplicate_analysis_name_duration_rule_is_opt_in(tmp_path: Path):
    db_path = tmp_path / "roibang.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        _insert_profile(conn, material_id="m1", name="勇者素材A.mp4", duration=12.01)
        _insert_profile(conn, material_id="m2", name="勇者素材A", duration=12.18)
        _insert_profile(conn, material_id="m3", name="勇者素材A", duration=14.00)

    disabled = run_material_duplicate_analysis_request(
        {"material_duplicate_analysis": {"rules": ["signature"], "min_group_size": 2}},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )
    enabled = run_material_duplicate_analysis_request(
        {
            "material_duplicate_analysis": {
                "rules": ["name_duration"],
                "min_group_size": 2,
                "duration_tolerance_seconds": 0.25,
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert disabled["summary"]["duplicate_group_count"] == 0
    assert enabled["summary"]["duplicate_group_count"] == 1
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT material_id, duplicate_rule, confidence_label
            FROM material_duplicate_candidates
            ORDER BY material_id
            """
        ).fetchall()
    assert rows == [("m1", "name_duration", "medium"), ("m2", "name_duration", "medium")]
