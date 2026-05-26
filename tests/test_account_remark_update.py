import json
from pathlib import Path

from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.account_remark_update import build_account_remark_update_config
from roibang_v2.workflows.account_remark_update import run_account_remark_update


def test_build_account_remark_update_config_writes_expected_actions():
    config = build_account_remark_update_config(
        update_id="diandian-remark",
        advertiser_ids=["1861", "1862"],
        remark="点点英雄-微小-郭靖",
    )

    assert config["account_remark_update"]["update_id"] == "diandian-remark"
    assert config["account_remark_update"]["remark"] == "点点英雄-微小-郭靖"
    assert config["account_remark_update"]["advertiser_ids"] == ["1861", "1862"]
    assert config["account_remark_update"]["http"]["enabled"] is False
    assert config["account_remark_update"]["http"]["body_template"] == {
        "accountId": "__ADVERTISER_ID__",
        "remark": "__REMARK__",
    }
    assert "edit_account_remark" in config["account_remark_update"]["http"]["url"]


def test_account_remark_update_check_only_outputs_preview_without_external_calls(tmp_path: Path):
    request = build_account_remark_update_config(
        update_id="diandian-remark",
        advertiser_ids=["1861", "1862"],
        remark="点点英雄-微小-郭靖",
    )

    result = run_account_remark_update(request, runs_dir=tmp_path, execute=False)

    assert result["ok"] is True
    assert result["status"] == "preview_ready"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0
    assert result["summary"]["account_count"] == 2
    assert result["summary"]["remark"] == "点点英雄-微小-郭靖"
    assert result["readable_reference"]["accounts"][0]["advertiser_id"] == "1861"
    assert Path(result["artifact_path"]).exists()


def test_account_remark_update_execute_blocks_when_http_not_enabled(tmp_path: Path):
    request = build_account_remark_update_config(
        update_id="diandian-remark",
        advertiser_ids=["1861"],
        remark="点点英雄-微小-郭靖",
    )

    result = run_account_remark_update(request, runs_dir=tmp_path, execute=True)

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "http.enabled must be true for execute" in result["blocking_reasons"]
    assert result["external_api_calls"] == 0


def test_account_remark_update_execute_uses_configured_endpoint_and_template(tmp_path: Path):
    calls = []

    def opener(url, body, headers, timeout_seconds):
        calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds})
        return HttpResponse(200, {"code": 0, "message": "ok"})

    request = build_account_remark_update_config(
        update_id="diandian-remark",
        advertiser_ids=["1861", "1862"],
        remark="点点英雄-微小-郭靖",
    )
    request["account_remark_update"]["http"].update(
        {
            "enabled": True,
            "url": "https://business.oceanengine.com/api/test/update_remark",
            "session": {"cookie": "cookie-value", "csrf_token": "csrf-value"},
            "body_template": {
                "account_id": "__ADVERTISER_ID__",
                "advertiser_remark": "__REMARK__",
            },
        }
    )

    result = run_account_remark_update(request, runs_dir=tmp_path, execute=True, opener=opener)

    assert result["ok"] is True
    assert result["status"] == "executed"
    assert result["execution_enabled"] is True
    assert result["external_api_calls"] == 2
    assert [call["body"]["account_id"] for call in calls] == ["1861", "1862"]
    assert all(call["body"]["advertiser_remark"] == "点点英雄-微小-郭靖" for call in calls)
    assert calls[0]["headers"]["Cookie"] == "cookie-value"
    assert calls[0]["headers"]["x-csrftoken"] == "csrf-value"


def test_account_remark_update_execute_records_api_failure_and_continues(tmp_path: Path):
    def opener(url, body, headers, timeout_seconds):
        if body["accountId"] == "1861":
            return HttpResponse(200, {"code": 400, "message": "bad account"})
        return HttpResponse(200, {"code": 0, "message": "ok"})

    request = build_account_remark_update_config(
        update_id="diandian-remark",
        advertiser_ids=["1861", "1862"],
        remark="点点英雄-微小-郭靖",
    )
    request["account_remark_update"]["http"].update(
        {
            "enabled": True,
            "url": "https://business.oceanengine.com/api/test/update_remark",
            "session": {"cookie": "cookie-value", "csrf_token": "csrf-value"},
        }
    )

    result = run_account_remark_update(request, runs_dir=tmp_path, execute=True, opener=opener)

    assert result["ok"] is False
    assert result["status"] == "partial_failed"
    assert result["summary"]["success_count"] == 1
    assert result["summary"]["failed_count"] == 1
    assert result["results"][0]["ok"] is False
    assert result["results"][1]["ok"] is True
