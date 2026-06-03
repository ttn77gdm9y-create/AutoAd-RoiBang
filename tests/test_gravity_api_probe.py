import json
import subprocess
from pathlib import Path


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
    assert "secret-token-value" not in completed.stdout
    assert "upload_material" not in completed.stdout


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
