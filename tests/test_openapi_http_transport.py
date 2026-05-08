import json
import urllib.error

import pytest

from roibang_v2.fetch.openapi_http import HttpResponse, build_http_transport
from roibang_v2.fetch.openapi_readonly import build_readonly_request
from roibang_v2.fetch.openapi_readonly import validate_readonly_endpoint


def _request():
    request = build_readonly_request(
        "operation_log_search",
        {
            "advertiser_id": "1858371222574218",
            "start_time": "2026-02-10 00:00:00",
            "end_time": "2026-02-10 23:59:59",
            "page": 1,
            "page_size": 20,
        },
    )
    request["date"] = "2026-02-10"
    return request


def test_http_transport_is_disabled_by_default(tmp_path):
    with pytest.raises(RuntimeError, match="disabled"):
        build_http_transport(
            {"enabled": False},
            response_dir=tmp_path,
            opener=lambda *_args, **_kwargs: HttpResponse(200, {}),
        )


def test_http_transport_loads_token_from_env_and_redacts_audit(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")

    def fake_opener(url, query_params, headers, timeout_seconds):
        calls.append(
            {
                "url": url,
                "query_params": query_params,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
            }
        )
        return HttpResponse(200, {"code": 0, "message": "OK", "data": {"logs": []}})

    transport = build_http_transport(
        {
            "enabled": True,
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "timeout_seconds": 9,
            "max_retries": 0,
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    response = transport(_request())
    audit = json.loads((tmp_path / "http_responses.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert response == {"code": 0, "message": "OK", "data": {"logs": []}}
    assert calls[0]["headers"] == {"Access-Token": "secret-token"}
    assert calls[0]["timeout_seconds"] == 9
    assert audit["request"]["headers"] == {"Access-Token": "<redacted>"}
    assert "secret-token" not in json.dumps(audit, ensure_ascii=False)


def test_material_profile_readonly_endpoints_allow_customer_only_paths():
    org_video_request = build_readonly_request(
        "ebp_video_material_get",
        {"advertiser_id": "185", "filtering": {"material_ids": [1001]}, "page": 1, "page_size": 1},
    )
    attributes_request = build_readonly_request(
        "material_attributes_list",
        {
            "account_id": "185",
            "account_type": "AD",
            "filtering": {"material_ids": [1001]},
            "page": 1,
            "page_size": 1,
        },
    )

    assert org_video_request["path"] == "/open_api/v3.0/file/ebp_video/get/"
    assert org_video_request["query_params"]["filtering"] == "{\"material_ids\":[1001]}"
    assert attributes_request["path"] == "/open_api/2/file/material_attributes/list/"
    assert attributes_request["query_params"]["filtering"] == "{\"material_ids\":[1001]}"
    with pytest.raises(ValueError, match="allowlist"):
        validate_readonly_endpoint("agent_video_material_get")


def test_http_transport_retries_retryable_status_and_rate_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    responses = [
        HttpResponse(429, {"code": 429, "message": "rate limited"}),
        HttpResponse(200, {"code": 0, "message": "OK", "data": {"rows": []}}),
        HttpResponse(200, {"code": 0, "message": "OK", "data": {"rows": []}}),
    ]
    sleeps = []

    def fake_opener(_url, _query_params, _headers, _timeout_seconds):
        return responses.pop(0)

    transport = build_http_transport(
        {
            "enabled": True,
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "max_retries": 1,
            "retry_sleep_seconds": 0.5,
            "min_interval_seconds": 0.2,
        },
        response_dir=tmp_path,
        opener=fake_opener,
        sleeper=sleeps.append,
    )

    assert transport(_request())["code"] == 0
    assert transport(_request())["code"] == 0

    assert sleeps == [0.5, 0.2]
    assert len((tmp_path / "http_responses.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_http_transport_retries_transient_connection_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = {"count": 0}
    sleeps = []

    def fake_opener(_url, _query_params, _headers, _timeout_seconds):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError(ConnectionResetError(54, "Connection reset by peer"))
        return HttpResponse(200, {"code": 0, "message": "OK", "data": {"rows": []}})

    transport = build_http_transport(
        {
            "enabled": True,
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "max_retries": 1,
            "retry_sleep_seconds": 0.5,
        },
        response_dir=tmp_path,
        opener=fake_opener,
        sleeper=sleeps.append,
    )

    assert transport(_request())["code"] == 0
    assert calls["count"] == 2
    assert sleeps == [0.5]
    audit_text = (tmp_path / "http_responses.jsonl").read_text(encoding="utf-8")
    assert "Connection reset by peer" in audit_text
    assert "secret-token" not in audit_text


def test_http_transport_loads_and_refreshes_token_from_v2_store(tmp_path):
    store = tmp_path / "tokens.json"
    store.write_text(
        json.dumps(
            {
                "version": 1,
                "tokens": {
                    "default": {
                        "access_token": "access-old",
                        "refresh_token": "refresh-old",
                        "expires_at": "2026-05-01T00:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_oauth_opener(_url, payload, _timeout_seconds):
        assert payload["refresh_token"] == "refresh-old"
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "access_token": "access-new",
                    "refresh_token": "refresh-new",
                    "expires_in": 3600,
                    "refresh_token_expires_in": 86400,
                },
            },
        )

    def fake_opener(_url, _query_params, headers, _timeout_seconds):
        calls.append(headers)
        return HttpResponse(200, {"code": 0, "message": "OK", "data": {"logs": []}})

    transport = build_http_transport(
        {
            "enabled": True,
            "token_store": {
                "enabled": True,
                "store_file": str(store),
                "user_id": "default",
                "auto_refresh": True,
                "app_id": "app-id",
                "app_secret": "app-secret",
            },
            "max_retries": 0,
        },
        response_dir=tmp_path / "audit",
        opener=fake_opener,
        oauth_opener=fake_oauth_opener,
    )

    assert transport(_request())["code"] == 0
    assert calls == [{"Access-Token": "access-new"}]
    audit_text = (tmp_path / "audit" / "http_responses.jsonl").read_text(encoding="utf-8")
    assert "access-new" not in audit_text


def test_http_transport_token_store_reads_oauth_credentials_from_env(monkeypatch, tmp_path):
    store = tmp_path / "tokens.json"
    store.write_text(
        json.dumps(
            {
                "version": 1,
                "tokens": {
                    "default": {
                        "access_token": "access-old",
                        "refresh_token": "refresh-old",
                        "expires_at": "2026-05-01T00:00:00+00:00",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ROIBANG_TEST_APP_ID", "app-id-from-env")
    monkeypatch.setenv("ROIBANG_TEST_APP_SECRET", "app-secret-from-env")

    def fake_oauth_opener(_url, payload, _timeout_seconds):
        assert payload["app_id"] == "app-id-from-env"
        assert payload["secret"] == "app-secret-from-env"
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "access_token": "access-new",
                    "refresh_token": "refresh-new",
                    "expires_in": 3600,
                    "refresh_token_expires_in": 86400,
                },
            },
        )

    transport = build_http_transport(
        {
            "enabled": True,
            "token_store": {
                "enabled": True,
                "store_file": str(store),
                "user_id": "default",
                "auto_refresh": True,
                "app_id_env": "ROIBANG_TEST_APP_ID",
                "app_secret_env": "ROIBANG_TEST_APP_SECRET",
            },
        },
        response_dir=tmp_path / "audit",
        opener=lambda *_args: HttpResponse(200, {"code": 0, "data": {"logs": []}}),
        oauth_opener=fake_oauth_opener,
    )

    assert transport(_request())["code"] == 0
