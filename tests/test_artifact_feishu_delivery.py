import json
from pathlib import Path

from roibang_v2.workflows.artifact_feishu_delivery import deliver_artifact_to_feishu, format_artifact_feishu_message


def _artifact() -> dict:
    return {
        "ok": True,
        "workflow": "create_live_execute_report",
        "status": "reported_completed",
        "message": "真实创建结果：完成项目1个、单元1个。",
        "summary": {
            "created_project_count": 1,
            "created_unit_count": 1,
            "material_bind_count": 2,
            "source_external_api_calls": 4,
        },
        "readable_reference": {
            "selected_materials": {
                "assignment_count": 2,
                "unique_material_count": 1,
                "top_materials_by_cost": [
                    {
                        "material_id": "m1",
                        "name": "素材1",
                        "stat_cost": 123.45,
                        "convert_cnt": 2,
                        "assigned_count": 2,
                    }
                ],
            }
        },
    }


def test_format_artifact_feishu_message_includes_readable_reference():
    message = format_artifact_feishu_message(_artifact(), artifact_path="data/runs/a.json")

    assert "RoiBang-V2 任务执行报告" in message
    assert "create_live_execute_report：成功，状态 reported_completed" in message
    assert "创建项目：1" in message
    assert "素材推送：2" in message
    assert "素材1（m1）：消耗 123.45，转化 2，使用 2 次" in message
    assert "完整 JSON：data/runs/a.json" in message


def test_deliver_artifact_to_feishu_uses_sender():
    calls = []

    def sender(config: dict, text: str) -> dict:
        calls.append((config, text))
        return {"ok": True, "stage": "message"}

    result = deliver_artifact_to_feishu(
        _artifact(),
        artifact_path="data/runs/a.json",
        runtime_file="data/secrets/feishu.runtime.local.json",
        feishu_sender=sender,
    )

    assert result["ok"] is True
    assert calls[0][0]["runtime_file"] == "data/secrets/feishu.runtime.local.json"
    assert "素材1（m1）" in calls[0][1]


def test_artifact_feishu_delivery_script_prints_message(tmp_path: Path, capsys):
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(_artifact(), ensure_ascii=False), encoding="utf-8")

    import importlib.util

    spec = importlib.util.spec_from_file_location("run_artifact_feishu_delivery", "scripts/run_artifact_feishu_delivery.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    exit_code = module.run_from_args(["--artifact", str(path), "--print-message-only"])

    assert exit_code == 0
    assert "素材1（m1）" in capsys.readouterr().out
