import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from roibang_v2.integrations.oceanengine.tokens import (
    OAuthResponse,
    TokenSnapshot,
    exchange_auth_code,
    load_token_snapshot,
    refresh_access_token,
    token_health,
)


def _load_script(name: str):
    script_path = Path("scripts") / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_store(path: Path, *, access: str = "access-old", refresh: str = "refresh-old", expires_in: int = 3600):
    now = datetime(2026, 5, 7, 2, 0, tzinfo=timezone.utc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "tokens": {
                    "default": {
                        "access_token": access,
                        "refresh_token": refresh,
                        "expires_at": (now + timedelta(seconds=expires_in)).isoformat(),
                        "refresh_token_expires_at": (now + timedelta(days=30)).isoformat(),
                        "updated_at": now.isoformat(),
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_token_store_loads_snapshot_without_exposing_secret_in_health(tmp_path):
    store = tmp_path / "tokens.json"
    _write_store(store, access="access-secret", refresh="refresh-secret")

    snapshot = load_token_snapshot(store, user_id="default")
    health = token_health(store, user_id="default", now=datetime(2026, 5, 7, 2, 10, tzinfo=timezone.utc))

    assert snapshot.access_token == "access-secret"
    assert snapshot.refresh_token == "refresh-secret"
    assert health["status"] == "valid"
    assert health["access_token_present"] is True
    assert health["refresh_token_present"] is True
    assert "access-secret" not in json.dumps(health, ensure_ascii=False)
    assert "refresh-secret" not in json.dumps(health, ensure_ascii=False)


def test_token_health_reports_expired_and_missing_without_network(tmp_path):
    missing = token_health(tmp_path / "missing.json", user_id="default")
    assert missing["status"] == "missing_store"

    store = tmp_path / "tokens.json"
    _write_store(store, expires_in=-60)
    expired = token_health(store, user_id="default", now=datetime(2026, 5, 7, 2, 10, tzinfo=timezone.utc))
    assert expired["status"] == "expired"
    assert expired["expires_in_seconds"] < 0


def test_exchange_auth_code_writes_token_store_with_injected_opener(tmp_path):
    store = tmp_path / "tokens.json"
    calls = []

    def fake_opener(url, payload, timeout_seconds):
        calls.append({"url": url, "payload": payload, "timeout_seconds": timeout_seconds})
        return OAuthResponse(
            200,
            {
                "code": 0,
                "data": {
                    "access_token": "access-new",
                    "refresh_token": "refresh-new",
                    "expires_in": 7200,
                    "refresh_token_expires_in": 86400,
                },
            },
        )

    result = exchange_auth_code(
        store_file=store,
        user_id="default",
        app_id="app-id",
        app_secret="app-secret",
        auth_code="auth-code",
        opener=fake_opener,
        now=datetime(2026, 5, 7, 2, 0, tzinfo=timezone.utc),
    )

    snapshot = load_token_snapshot(store, user_id="default")
    assert result["ok"] is True
    assert result["token"]["access_token_present"] is True
    assert "access-new" not in json.dumps(result, ensure_ascii=False)
    assert snapshot.access_token == "access-new"
    assert snapshot.refresh_token == "refresh-new"
    assert calls[0]["payload"] == {
        "app_id": "app-id",
        "secret": "app-secret",
        "grant_type": "auth_code",
        "auth_code": "auth-code",
    }


def test_refresh_access_token_updates_store_with_injected_opener(tmp_path):
    store = tmp_path / "tokens.json"
    _write_store(store, access="access-old", refresh="refresh-old", expires_in=-60)

    def fake_opener(_url, payload, _timeout_seconds):
        assert payload["refresh_token"] == "refresh-old"
        return OAuthResponse(
            200,
            {
                "code": 0,
                "data": {
                    "access_token": "access-refreshed",
                    "refresh_token": "refresh-refreshed",
                    "expires_in": 3600,
                    "refresh_token_expires_in": 86400,
                },
            },
        )

    result = refresh_access_token(
        store_file=store,
        user_id="default",
        app_id="app-id",
        app_secret="app-secret",
        opener=fake_opener,
        now=datetime(2026, 5, 7, 2, 0, tzinfo=timezone.utc),
    )

    snapshot = load_token_snapshot(store, user_id="default")
    assert result["ok"] is True
    assert snapshot.access_token == "access-refreshed"
    assert snapshot.refresh_token == "refresh-refreshed"


def test_refresh_fails_safely_without_refresh_token(tmp_path):
    store = tmp_path / "tokens.json"
    save = {
        "version": 1,
        "tokens": {
            "default": {
                "access_token": "access-only",
                "refresh_token": "",
            }
        },
    }
    store.write_text(json.dumps(save), encoding="utf-8")

    with pytest.raises(RuntimeError, match="refresh_token"):
        refresh_access_token(
            store_file=store,
            user_id="default",
            app_id="app-id",
            app_secret="app-secret",
            opener=lambda *_args: OAuthResponse(200, {"code": 0, "data": {}}),
        )


def test_check_token_cli_prints_redacted_health(tmp_path, capsys):
    store = tmp_path / "tokens.json"
    _write_store(store, access="access-secret", refresh="refresh-secret", expires_in=86400 * 30)
    module = _load_script("check_oceanengine_token.py")

    exit_code = module.run_from_args(["--store-file", str(store), "--user-id", "default"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert '"access_token_present": true' in output
    assert "access-secret" not in output
    assert "refresh-secret" not in output


def test_exchange_cli_requires_credentials_without_printing_auth_code(tmp_path, capsys):
    module = _load_script("exchange_oceanengine_auth_code.py")

    with pytest.raises(RuntimeError, match="app id"):
        module.run_from_args(["--store-file", str(tmp_path / "tokens.json"), "--auth-code", "auth-secret"])

    assert "auth-secret" not in capsys.readouterr().out
