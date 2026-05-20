import importlib.util
import json
import sqlite3
from pathlib import Path

from roibang_v2.workflows.create_batch_review import build_create_batch_review
from roibang_v2.workflows.create_batch_review import parse_create_project_name
from roibang_v2.workflows.create_batch_review import run_create_batch_review_request


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE material_daily_metrics (
          metric_date TEXT NOT NULL,
          advertiser_id TEXT NOT NULL,
          project_id TEXT NOT NULL DEFAULT '',
          project_name TEXT NOT NULL DEFAULT '',
          promotion_id TEXT NOT NULL DEFAULT '',
          promotion_name TEXT NOT NULL DEFAULT '',
          material_id TEXT NOT NULL,
          material_kind TEXT NOT NULL DEFAULT 'video',
          stat_cost REAL NOT NULL DEFAULT 0,
          show_cnt REAL NOT NULL DEFAULT 0,
          click_cnt REAL NOT NULL DEFAULT 0,
          convert_cnt REAL NOT NULL DEFAULT 0,
          active_register REAL NOT NULL DEFAULT 0,
          roi_1day REAL NOT NULL DEFAULT 0,
          roi_7days REAL NOT NULL DEFAULT 0,
          metric_payload_json TEXT NOT NULL DEFAULT '{}',
          source TEXT NOT NULL,
          synced_at TEXT NOT NULL
        )
        """
    )
    rows = [
        (
            "2026-05-18",
            "adv-1",
            "p-1",
            "0518_郭靖_勇者突进_微小每付7R通投历史放量_BATCHA_01",
            "u-1",
            "单元 1",
            "m-1",
            100,
            1000,
            20,
            1,
            2,
            0.1,
        ),
        (
            "2026-05-18",
            "adv-1",
            "p-1",
            "0518_郭靖_勇者突进_微小每付7R通投历史放量_BATCHA_01",
            "u-1",
            "单元 1",
            "m-2",
            300,
            2000,
            40,
            2,
            3,
            0.2,
        ),
        (
            "2026-05-19",
            "adv-2",
            "p-2",
            "0518_郭靖_勇者突进_微小每付通投测新_BATCHB_01",
            "u-2",
            "单元 2",
            "m-3",
            50,
            500,
            10,
            0,
            1,
            0,
        ),
        (
            "2026-05-19",
            "adv-3",
            "p-3",
            "不是创建批次项目",
            "u-3",
            "单元 3",
            "m-4",
            10,
            100,
            1,
            0,
            0,
            0,
        ),
    ]
    conn.executemany(
        """
        INSERT INTO material_daily_metrics (
          metric_date, advertiser_id, project_id, project_name, promotion_id, promotion_name,
          material_id, stat_cost, show_cnt, click_cnt, convert_cnt, active_register, roi_1day,
          source, synced_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'test', '2026-05-20T00:00:00')
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _load_script():
    script_path = Path("scripts/run_create_batch_review.py")
    spec = importlib.util.spec_from_file_location("run_create_batch_review", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_parse_create_project_name_extracts_batch_fields():
    parsed = parse_create_project_name("0518_郭靖_勇者突进_微小每付通投历史放量_ABCD1234_05")

    assert parsed == {
        "parsed": True,
        "batch_date_code": "0518",
        "mode_label": "微小每付通投历史放量",
        "batch_id": "ABCD1234",
        "project_seq": "05",
        "batch_key": "0518:微小每付通投历史放量:ABCD1234",
    }


def test_build_create_batch_review_groups_by_batch_and_mode(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    _init_db(db_path)

    result = build_create_batch_review(
        db_path=db_path,
        start_date="2026-05-18",
        end_date="2026-05-19",
        project_name_contains="郭靖",
    )

    assert result["workflow"] == "create_batch_review"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["batch_count"] == 2
    assert result["summary"]["project_count"] == 2
    assert result["summary"]["unparsed_metric_row_count"] == 0
    assert result["summary"]["stat_cost"] == 450
    assert result["summary"]["roi_1day"] == 0.1556
    assert result["batches"][0]["mode_label"] == "微小每付7R通投历史放量"
    assert result["batches"][0]["stat_cost"] == 400
    assert result["batches"][0]["conversion_cost"] == 133.3333
    assert "RoiBang-V2 创建批次复盘" in result["message"]


def test_run_create_batch_review_request_writes_artifact(tmp_path: Path):
    db_path = tmp_path / "test.sqlite3"
    _init_db(db_path)

    result = run_create_batch_review_request(
        {
            "db_path": str(db_path),
            "start_date": "2026-05-18",
            "end_date": "2026-05-19",
            "project_name_contains": "郭靖",
        },
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is True
    assert Path(result["artifact_path"]).exists()
    assert Path(result["latest_artifact_path"]).exists()
    assert json.loads(Path(result["latest_artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "create_batch_review"
    assert result["source"] == {
        "db_path": str(db_path),
        "data_source": "material_daily_metrics",
    }


def test_create_batch_review_cli_accepts_request_file(tmp_path: Path, capsys):
    db_path = tmp_path / "test.sqlite3"
    _init_db(db_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "create_batch_review": {
                    "db_path": str(db_path),
                    "start_date": "2026-05-18",
                    "end_date": "2026-05-19",
                    "project_name_contains": "郭靖",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    module = _load_script()

    exit_code = module.run_from_args(["--request", str(request_path), "--runs-dir", str(tmp_path / "runs")])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["workflow"] == "create_batch_review"
    assert output["summary"]["batch_count"] == 2
    assert output["external_api_calls"] == 0
