import json
import importlib.util
from pathlib import Path

from roibang_v2.workflows.gravity_token_refresh import run_gravity_token_refresh


def _collector(_request: dict) -> dict:
    return {
        "authorization": "Bearer secret.jwt.token",
        "gravity_cid": "182",
        "gravity_email": "hongen@example.com",
        "gravity_id": "406",
        "gravity_super": "false",
    }


def _load_script(name: str):
    script_path = Path(f"scripts/{name}.py")
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_gravity_token_refresh_blocks_when_credentials_missing(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GRAVITY_USERNAME", raising=False)
    monkeypatch.delenv("GRAVITY_PASSWORD", raising=False)
    token_path = tmp_path / "data" / "gravity_token.json"

    result = run_gravity_token_refresh(
        {"auth_file": str(token_path), "username_env": "GRAVITY_USERNAME", "password_env": "GRAVITY_PASSWORD"},
        runs_dir=tmp_path / "runs",
        collector=_collector,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "缺少环境变量：GRAVITY_USERNAME、GRAVITY_PASSWORD" in result["blocking_reasons"]
    assert token_path.exists() is False
    raw_text = json.dumps(result, ensure_ascii=False)
    assert "secret.jwt.token" not in raw_text
    assert "Bearer secret" not in raw_text


def test_gravity_token_refresh_writes_token_file_without_leaking_token(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GRAVITY_USERNAME", "gravity-user")
    monkeypatch.setenv("GRAVITY_PASSWORD", "gravity-password")
    token_path = tmp_path / "data" / "gravity_token.json"

    result = run_gravity_token_refresh(
        {"auth_file": str(token_path), "username_env": "GRAVITY_USERNAME", "password_env": "GRAVITY_PASSWORD"},
        runs_dir=tmp_path / "runs",
        collector=_collector,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["summary"]["auth_file_exists"] is True
    assert result["summary"]["auth_field_status"] == "完整"
    assert result["summary"]["token_present"] is True
    assert result["summary"]["gravity_cid"] == "182"
    assert result["summary"]["gravity_email"] == "hongen@example.com"
    saved = json.loads(token_path.read_text(encoding="utf-8"))
    assert saved["authorization"] == "Bearer secret.jwt.token"
    assert saved["gravity_id"] == "406"
    raw_text = json.dumps(result, ensure_ascii=False)
    assert "secret.jwt.token" not in raw_text
    assert "gravity-password" not in raw_text
    assert result["artifact_path"].endswith(".json")
    artifact_text = Path(result["artifact_path"]).read_text(encoding="utf-8")
    assert "secret.jwt.token" not in artifact_text
    assert "gravity-password" not in artifact_text


def test_gravity_token_refresh_cli_prints_safe_summary(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("GRAVITY_USERNAME", "gravity-user")
    monkeypatch.setenv("GRAVITY_PASSWORD", "gravity-password")
    runtime_path = tmp_path / "runtime.json"
    runtime_path.write_text(
        json.dumps(
            {
                "environment": "test",
                "phase": "phase1",
                "database_path": str(tmp_path / "roibang.sqlite3"),
                "runs_dir": str(tmp_path / "runs"),
                "fixtures_dir": str(tmp_path / "fixtures"),
                "external_api_enabled": False,
                "execution_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    token_path = tmp_path / "gravity_token.json"
    script = _load_script("run_gravity_token_refresh")
    monkeypatch.setattr(script, "run_gravity_token_refresh", lambda request, *, runs_dir: run_gravity_token_refresh(request, runs_dir=runs_dir, collector=_collector))

    code = script.run_from_args(
        [
            "--config",
            str(runtime_path),
            "--auth-file",
            str(token_path),
            "--username-env",
            "GRAVITY_USERNAME",
            "--password-env",
            "GRAVITY_PASSWORD",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["workflow"] == "gravity_token_refresh"
    assert output["summary"]["auth_file_exists"] is True
    text = json.dumps(output, ensure_ascii=False)
    assert "secret.jwt.token" not in text
    assert "gravity-password" not in text
