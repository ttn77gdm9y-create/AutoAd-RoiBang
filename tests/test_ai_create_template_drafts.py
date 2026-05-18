import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.workflows.ai_create_template_drafts import run_ai_create_template_drafts_request


def _create_rollup_table(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE product_source_material_metric_rollups (
              product TEXT,
              source_advertiser_id TEXT,
              window_key TEXT,
              period_start TEXT,
              period_end TEXT,
              material_id TEXT,
              material_type TEXT,
              source_video_id TEXT,
              name TEXT,
              review_status TEXT,
              create_time TEXT,
              first_seen_metric_date TEXT,
              effective_create_date TEXT,
              effective_create_date_source TEXT,
              account_count INTEGER,
              project_count INTEGER,
              promotion_count INTEGER,
              stat_cost REAL,
              show_cnt REAL,
              click_cnt REAL,
              convert_cnt REAL,
              active_register REAL,
              roi_1day_cost_weighted REAL,
              roi_7days_cost_weighted REAL,
              source TEXT,
              synced_at TEXT
            )
            """
        )


def _insert_rollup(
    db_path: Path,
    *,
    window_key: str,
    period_start: str,
    period_end: str,
    index: int,
    stat_cost: float,
    convert_cnt: float,
    effective_create_date: str,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO product_source_material_metric_rollups (
              product, source_advertiser_id, window_key, period_start, period_end,
              material_id, material_type, source_video_id, name, review_status,
              create_time, first_seen_metric_date, effective_create_date, effective_create_date_source,
              account_count, project_count, promotion_count, stat_cost, show_cnt, click_cnt,
              convert_cnt, active_register, roi_1day_cost_weighted, roi_7days_cost_weighted, source, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "勇者突进",
                "1856647522964490",
                window_key,
                period_start,
                period_end,
                f"m{window_key}{index:04d}",
                "video",
                f"v{index:010d}",
                f"素材{index}",
                "pass",
                effective_create_date,
                effective_create_date,
                effective_create_date,
                "first_seen_metric_date",
                1,
                1,
                1,
                stat_cost,
                1000,
                100,
                convert_cnt,
                convert_cnt,
                0.06 if stat_cost else 0,
                0.08 if stat_cost else 0,
                "test",
                "2026-05-16T00:00:00Z",
            ),
        )


def _seed_rollups(db_path: Path) -> None:
    _create_rollup_table(db_path)
    for index in range(35):
        _insert_rollup(
            db_path,
            window_key="last_7d",
            period_start="2026-05-09",
            period_end="2026-05-15",
            index=index,
            stat_cost=300,
            convert_cnt=0,
            effective_create_date="2026-05-15",
        )
    for index in range(60):
        _insert_rollup(
            db_path,
            window_key="last_30d",
            period_start="2026-04-16",
            period_end="2026-05-15",
            index=1000 + index,
            stat_cost=1200,
            convert_cnt=8,
            effective_create_date="2026-04-20",
        )
    for index in range(25):
        _insert_rollup(
            db_path,
            window_key="last_30d",
            period_start="2026-04-16",
            period_end="2026-05-15",
            index=2000 + index,
            stat_cost=300,
            convert_cnt=3,
            effective_create_date="2026-05-10",
        )
    for index in range(25):
        _insert_rollup(
            db_path,
            window_key="last_30d",
            period_start="2026-04-16",
            period_end="2026-05-15",
            index=3000 + index,
            stat_cost=100,
            convert_cnt=0,
            effective_create_date="2026-05-01",
        )


def _write_manual_mode(path: Path, *, mode_key: str, display_name: str, selection_type: str) -> None:
    path.write_text(
        json.dumps(
            {
                "mode_key": mode_key,
                "display_name": display_name,
                "template_key": "wx_pay_general",
                "template_name_suffix": display_name,
                "defaults": {
                    "daily_budget": 10000,
                    "cpa_bid": 111,
                    "project_count": 5,
                    "units_per_project": 1,
                },
                "material_requirements": {
                    "materials_per_unit": 6,
                    "allow_reuse_on_insufficient": True,
                },
                "material_selection": {
                    "lookback_days": 7,
                    "selection_type": selection_type,
                    "random_shuffle": True,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _manual_mode_dir(tmp_path: Path) -> Path:
    mode_dir = tmp_path / "create-modes"
    mode_dir.mkdir()
    _write_manual_mode(
        mode_dir / "wx_pay_general_recent_scale.example.json",
        mode_key="wx_pay_general_recent_scale",
        display_name="每付通投近期放量",
        selection_type="high_spend",
    )
    _write_manual_mode(
        mode_dir / "wx_pay_general_scale.example.json",
        mode_key="wx_pay_general_scale",
        display_name="每付通投历史放量",
        selection_type="high_spend",
    )
    _write_manual_mode(
        mode_dir / "wx_pay_general_test_new.example.json",
        mode_key="wx_pay_general_test_new",
        display_name="每付通投测新",
        selection_type="test_new",
    )
    return mode_dir


def _load_script():
    script_path = Path("scripts/run_ai_create_template_drafts.py")
    spec = importlib.util.spec_from_file_location("run_ai_create_template_drafts", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_ai_create_template_drafts_are_draft_only_and_separate_from_manual_modes(tmp_path):
    db_path = tmp_path / "db.sqlite3"
    runs_dir = tmp_path / "runs"
    mode_dir = _manual_mode_dir(tmp_path)
    before_files = {item.name: item.read_text(encoding="utf-8") for item in mode_dir.glob("*.json")}
    _seed_rollups(db_path)

    result = run_ai_create_template_drafts_request(
        {
            "ai_create_template_drafts": {
                "product": "勇者突进",
                "source_advertiser_id": "1856647522964490",
                "manual_mode_dir": str(mode_dir),
                "max_drafts": 5,
            }
        },
        db_path=db_path,
        runs_dir=runs_dir,
    )

    assert result["ok"] is True
    assert result["workflow"] == "ai_create_template_drafts"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["status"] == "drafted"
    assert result["summary"]["draft_count"] == 5
    assert Path(result["artifact_path"]).exists()
    assert result["manual_template_boundary"]["writes_manual_template"] is False
    assert result["manual_template_boundary"]["generates_create_plan"] is False
    assert result["manual_template_boundary"]["requires_human_promotion"] is True
    assert all(draft["status"] == "draft_only" for draft in result["drafts"])
    assert all("not_in_manual_create_modes" in draft["usage_blocking_reasons"] for draft in result["drafts"])
    assert before_files == {item.name: item.read_text(encoding="utf-8") for item in mode_dir.glob("*.json")}


def test_ai_create_template_drafts_blocks_without_source_account(tmp_path):
    db_path = tmp_path / "db.sqlite3"
    _seed_rollups(db_path)
    result = run_ai_create_template_drafts_request(
        {
            "ai_create_template_drafts": {
                "product": "勇者突进",
                "manual_mode_dir": str(_manual_mode_dir(tmp_path)),
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["drafts"] == []
    assert "missing source_advertiser_id" in result["blocking_reasons"]


def test_run_ai_create_template_drafts_script_uses_readonly_runtime(tmp_path, capsys):
    db_path = tmp_path / "db.sqlite3"
    runs_dir = tmp_path / "runs"
    mode_dir = _manual_mode_dir(tmp_path)
    _seed_rollups(db_path)
    runtime = tmp_path / "runtime.json"
    request = tmp_path / "request.json"
    runtime.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "test",
                "database_path": str(db_path),
                "runs_dir": str(runs_dir),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    request.write_text(
        json.dumps(
            {
                "ai_create_template_drafts": {
                    "product": "勇者突进",
                    "source_advertiser_id": "1856647522964490",
                    "manual_mode_dir": str(mode_dir),
                    "max_drafts": 2,
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module = _load_script()
    assert module.run_from_args(["--config", str(runtime), "--request", str(request)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["execution_enabled"] is False
    assert output["external_api_calls"] == 0
    assert output["summary"]["draft_count"] == 2
    assert Path(output["artifact_path"]).exists()
