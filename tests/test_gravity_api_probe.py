import json
import subprocess
from pathlib import Path

from roibang_v2.workflows.gravity_api_probe import run_gravity_api_probe


class FakeGravityClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_album_tree(self) -> dict:
        self.calls.append("get_album_tree")
        return {
            "code": 0,
            "data": [
                {
                    "id": "album-1",
                    "name": "点点英雄",
                    "children": [{"id": "folder-1", "name": "6月素材"}],
                }
            ],
        }

    def get_album_material_list(self, *, album_id: str, page: int, page_size: int) -> dict:
        self.calls.append(f"get_album_material_list:{album_id}:{page}:{page_size}")
        return {
            "code": 0,
            "data": {
                "total": 2,
                "list": [
                    {
                        "material_id": "12574679499084152",
                        "name": "点点英雄素材A",
                        "file_md5": "14e44adaaef54e81fa256a12b4ff5c24",
                        "status": 1,
                        "album_name": "点点英雄",
                        "folder_name": "6月素材",
                        "refuse_reason_ocean": 0,
                        "refuse_reason_tencent": 0,
                    },
                    {
                        "material_id": "12574679499084153",
                        "name": "点点英雄素材B",
                        "file_md5": "24e44adaaef54e81fa256a12b4ff5c25",
                        "status": 2,
                        "album_name": "点点英雄",
                        "folder_name": "6月素材",
                    },
                ],
            },
        }

    def get_material_detail(self, *, material_id: str) -> dict:
        self.calls.append(f"get_material_detail:{material_id}")
        return {
            "code": 0,
            "data": {
                "material_id": material_id,
                "file_md5": "14e44adaaef54e81fa256a12b4ff5c24",
                "file_url": "https://cdn.example.com/a.mp4",
                "album_name": "点点英雄",
                "folder_name": "6月素材",
                "status": 1,
            },
        }

    def get_material_report(self, *, material_ids: list[str], date_from: str, date_to: str, metrics: list[str]) -> dict:
        self.calls.append(f"get_material_report:{','.join(material_ids)}:{date_from}:{date_to}:{','.join(metrics)}")
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "material_id": material_ids[0],
                        "AdCost": 12.3,
                        "AdShow": 456,
                        "AdClick": 7,
                        "AdConvert": 1,
                    }
                ]
            },
        }

    def get_upload_material_status(self, *, task_id: str) -> dict:
        self.calls.append(f"get_upload_material_status:{task_id}")
        return {"code": 404, "msg": "任务不存在", "data": {}}


def test_gravity_api_probe_verifies_document_fields_without_uploading(tmp_path: Path):
    auth_file = tmp_path / "gravity_token.json"
    auth_file.write_text(
        json.dumps(
            {
                "jwt_token": "secret-token-value",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
                "gravity_super": "false",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = FakeGravityClient()

    result = run_gravity_api_probe(
        auth_file=auth_file,
        runs_dir=tmp_path / "runs",
        probe_scope="readonly_api",
        sample_limit=2,
        client=client,
    )

    assert result["ok"] is True
    assert result["phase"] == "readonly_api_probe"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 5
    assert result["summary"]["upload_material_called"] is False
    assert not any(call == "upload_material" or call.startswith("upload_material:") for call in client.calls)
    assert "secret-token-value" not in json.dumps(result, ensure_ascii=False)

    sections = {section["title"]: section for section in result["sections"]}
    field_rows = {row["核验项"]: row for row in sections["字段核验表"]["table"]["rows"]}
    assert field_rows["素材唯一标识"]["系统结论"] == "已确认引力素材 ID"
    assert field_rows["MD5 跨系统匹配"]["系统结论"] == "已确认 file_md5"
    assert field_rows["素材状态"]["系统结论"] == "已看到 1=可用，2=禁用"
    assert field_rows["拒审字段"]["系统结论"] == "部分素材缺失，缺失按未知处理"
    assert field_rows["素材报表"]["系统结论"] == "已确认可按素材和日期查询"
    assert field_rows["上传任务状态"]["系统结论"] == "接口可只读查询；本次未上传素材"

    sample_rows = sections["样本素材表"]["table"]["rows"]
    assert sample_rows[0]["素材 ID"] == "12574679499084152"
    assert sample_rows[0]["MD5"] == "14e44adaaef54e81fa256a12b4ff5c24"


def test_gravity_api_probe_reads_auth_without_exposing_token(tmp_path: Path):
    auth_file = tmp_path / "gravity_token.json"
    auth_file.write_text(
        json.dumps(
            {
                "jwt_token": "secret-token-value",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
                "gravity_super": "false",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "python3",
            "scripts/run_gravity_api_probe.py",
            "--auth-file",
            str(auth_file),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["workflow"] == "gravity_api_probe"
    assert payload["execution_enabled"] is False
    assert payload["external_api_calls"] == 0
    assert payload["summary"]["auth_file_exists"] is True
    assert payload["summary"]["upload_material_called"] is False
    assert "secret-token-value" not in completed.stdout
    assert "/turbo_engine/api/v1/task/bytedance/upload_material/" not in completed.stdout


def test_gravity_api_probe_blocks_missing_auth_file(tmp_path: Path):
    completed = subprocess.run(
        [
            "python3",
            "scripts/run_gravity_api_probe.py",
            "--auth-file",
            str(tmp_path / "missing.json"),
            "--runs-dir",
            str(tmp_path / "runs"),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ok"] is False
    assert payload["status"] == "blocked"
    assert "未找到引力 Token 文件" in payload["blocking_reasons"][0]
