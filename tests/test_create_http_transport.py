import json
import urllib.error

import pytest

from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.workflows.create_http_transport import build_create_http_transport


def test_create_http_transport_is_disabled_by_default(tmp_path):
    with pytest.raises(RuntimeError, match="disabled"):
        build_create_http_transport(
            {"enabled": False},
            response_dir=tmp_path,
            opener=lambda *_args, **_kwargs: HttpResponse(200, {}),
        )


def test_create_http_transport_requires_mutation_run_id_and_token(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")

    with pytest.raises(RuntimeError, match="allow_mutation"):
        build_create_http_transport(
            {
                "enabled": True,
                "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
                "run_id": "run-001",
            },
            response_dir=tmp_path,
            opener=lambda *_args, **_kwargs: HttpResponse(200, {}),
        )

    with pytest.raises(RuntimeError, match="run_id"):
        build_create_http_transport(
            {
                "enabled": True,
                "allow_mutation": True,
                "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            },
            response_dir=tmp_path,
            opener=lambda *_args, **_kwargs: HttpResponse(200, {}),
        )


def test_create_http_transport_posts_allowed_endpoint_and_redacts_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = []

    def fake_opener(url, body, headers, timeout_seconds, method):
        calls.append(
            {
                "url": url,
                "body": body,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
                "method": method,
            }
        )
        return HttpResponse(200, {"code": 0, "data": {"project_id": "project-001"}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "operator": "tester",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "timeout_seconds": 7,
            "base_url": "https://api.oceanengine.com",
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    response = transport(
        {
            "operation": "create_project",
            "endpoint": "/open_api/v3.0/project/create/",
            "payload": {"advertiser_id": "target-1", "name": "首单测试"},
        }
    )
    audit = json.loads((tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert response == {"code": 0, "data": {"project_id": "project-001"}}
    assert calls == [
        {
            "url": "https://api.oceanengine.com/open_api/v3.0/project/create/",
            "body": {"advertiser_id": "target-1", "name": "首单测试"},
            "headers": {
                "Access-Token": "secret-token",
                "Content-Type": "application/json",
            },
            "timeout_seconds": 7,
            "method": "POST",
        }
    ]
    assert audit["request"]["headers"] == {
        "Access-Token": "<redacted>",
        "Content-Type": "application/json",
    }
    assert audit["run"] == {"run_id": "run-001", "operator": "tester"}
    assert "secret-token" not in json.dumps(audit, ensure_ascii=False)


def test_create_http_transport_token_store_reads_oauth_credentials_from_file(tmp_path):
    store = tmp_path / "tokens.json"
    credentials = tmp_path / "credentials.json"
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
    credentials.write_text(
        json.dumps({"app_id": "app-id-from-file", "app_secret": "app-secret-from-file"}),
        encoding="utf-8",
    )

    def fake_oauth_opener(_url, payload, _timeout_seconds):
        assert payload["app_id"] == "app-id-from-file"
        assert payload["secret"] == "app-secret-from-file"
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

    calls = []

    def fake_opener(url, body, headers, timeout_seconds, method):
        calls.append({"headers": headers, "method": method})
        return HttpResponse(200, {"code": 0, "data": {"list": []}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_store": {
                "enabled": True,
                "store_file": str(store),
                "user_id": "default",
                "auto_refresh": True,
                "credentials_file": str(credentials),
            },
        },
        response_dir=tmp_path / "audit",
        opener=fake_opener,
        oauth_opener=fake_oauth_opener,
    )

    response = transport(
        {
            "operation": "lookup_existing_project",
            "endpoint": "/open_api/v3.0/project/list/",
            "payload": {"advertiser_id": "target-1", "filtering": {}, "page": 1, "page_size": 10},
        }
    )

    assert response["code"] == 0
    assert calls == [{"headers": {"Access-Token": "access-new", "Content-Type": "application/json"}, "method": "GET"}]


def test_create_http_transport_gets_target_material_lookup_and_redacts_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = []

    def fake_opener(url, body, headers, timeout_seconds, method):
        calls.append(
            {
                "url": url,
                "body": body,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
                "method": method,
            }
        )
        return HttpResponse(
            200,
            {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "id": "target-video-001",
                            "material_id": 12345,
                            "video_cover_id": "target-cover-001",
                        }
                    ]
                },
            },
        )

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "operator": "tester",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "base_url": "https://api.oceanengine.com",
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    response = transport(
        {
            "operation": "lookup_target_material",
            "endpoint": "/open_api/2/file/video/get/",
            "payload": {
                "target_advertiser_id": "target-1",
                "source_video_id": "source-video-1",
                "material_id": "12345",
            },
        }
    )
    audit = json.loads((tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert response["data"]["list"][0]["id"] == "target-video-001"
    assert calls == [
        {
            "url": (
                "https://api.oceanengine.com/open_api/2/file/video/get/"
                "?advertiser_id=target-1&filtering=%7B%22material_ids%22%3A%5B12345%5D%7D&page=1&page_size=10"
            ),
            "body": {
                "advertiser_id": "target-1",
                "filtering": {"material_ids": [12345]},
                "page": 1,
                "page_size": 10,
            },
            "headers": {
                "Access-Token": "secret-token",
                "Content-Type": "application/json",
            },
            "timeout_seconds": 20,
            "method": "GET",
        }
    ]
    assert audit["request"]["method"] == "GET"
    assert audit["request"]["headers"]["Access-Token"] == "<redacted>"
    assert "secret-token" not in json.dumps(audit, ensure_ascii=False)


def test_create_http_transport_rejects_unknown_or_mismatched_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
        },
        response_dir=tmp_path,
        opener=lambda *_args, **_kwargs: HttpResponse(200, {"code": 0}),
    )

    with pytest.raises(RuntimeError, match="not in create endpoint allowlist"):
        transport({"operation": "unknown_operation", "endpoint": "/open_api/2/project/delete/", "payload": {}})

    with pytest.raises(RuntimeError, match="does not match operation"):
        transport({"operation": "create_unit", "endpoint": "/open_api/v3.0/project/create/", "payload": {}})


def test_create_http_transport_supports_project_cap_cleanup_requests(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = []

    def fake_opener(url, body, headers, timeout_seconds, method):
        calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds, "method": method})
        return HttpResponse(200, {"code": 0, "data": {"ok": True}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "operator": "tester",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "base_url": "https://api.oceanengine.com",
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    transport(
        {
            "operation": "lookup_disabled_projects",
            "endpoint": "/open_api/v3.0/project/list/",
            "payload": {"advertiser_id": "target-1", "page": 1, "page_size": 100},
        }
    )
    transport(
        {
            "operation": "delete_project",
            "endpoint": "/open_api/2/project/delete/",
            "payload": {"advertiser_id": "target-1", "project_id": "project-001"},
        }
    )

    assert calls[0]["method"] == "GET"
    assert calls[0]["body"] == {
        "advertiser_id": "target-1",
        "filtering": {"project_status": ["PROJECT_STATUS_DISABLE"]},
        "page": 1,
        "page_size": 100,
    }
    assert calls[1]["method"] == "POST"
    assert calls[1]["url"] == "https://api.oceanengine.com/open_api/2/project/delete/"
    assert calls[1]["body"] == {"advertiser_id": "target-1", "project_id": "project-001"}


def test_create_http_transport_posts_activate_unit_status_update(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = []

    def fake_opener(url, body, headers, timeout_seconds, method):
        calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds, "method": method})
        return HttpResponse(200, {"code": 0, "data": {"promotion_ids": [9001]}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "operator": "tester",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "base_url": "https://api.oceanengine.com",
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    response = transport(
        {
            "operation": "activate_unit",
            "endpoint": "/open_api/v3.0/promotion/status/update/",
            "payload": {
                "advertiser_id": "target-1",
                "data": [{"promotion_id": 9001, "opt_status": "ENABLE"}],
            },
        }
    )

    assert response == {"code": 0, "data": {"promotion_ids": [9001]}}
    assert calls == [
        {
            "url": "https://api.oceanengine.com/open_api/v3.0/promotion/status/update/",
            "body": {
                "advertiser_id": "target-1",
                "data": [{"promotion_id": 9001, "opt_status": "ENABLE"}],
            },
            "headers": {
                "Access-Token": "secret-token",
                "Content-Type": "application/json",
            },
            "timeout_seconds": 20,
            "method": "POST",
        }
    ]


def test_create_http_transport_supports_project_schedule_lookup_and_update(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = []

    def fake_opener(url, body, headers, timeout_seconds, method):
        calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds, "method": method})
        return HttpResponse(200, {"code": 0, "data": {"list": []}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "operator": "tester",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "base_url": "https://api.oceanengine.com",
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    transport(
        {
            "operation": "lookup_project_schedule",
            "endpoint": "/open_api/v3.0/project/list/",
            "payload": {
                "advertiser_id": "target-1",
                "filtering": {"ids": ["project-1"]},
                "page": 1,
                "page_size": 1,
            },
        }
    )
    transport(
        {
            "operation": "update_project_week_schedule",
            "endpoint": "/open_api/v3.0/project/week_schedule/update/",
            "payload": {
                "advertiser_id": "target-1",
                "data": [{"project_id": "project-1", "schedule_time": "1" * 336, "schedule_scene": "REALTIME"}],
            },
        }
    )

    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == (
        "https://api.oceanengine.com/open_api/v3.0/project/list/"
        "?advertiser_id=target-1&filtering=%7B%22ids%22%3A%5B%22project-1%22%5D%7D&page=1&page_size=1"
    )
    assert calls[1]["method"] == "POST"
    assert calls[1]["url"] == "https://api.oceanengine.com/open_api/v3.0/project/week_schedule/update/"


def test_create_http_transport_does_not_retry_mutating_requests(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = {"count": 0}

    def fake_opener(_url, _body, _headers, _timeout_seconds, _method):
        calls["count"] += 1
        return HttpResponse(500, {"code": 500, "message": "server error"})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "max_retries": 3,
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    response = transport({"operation": "create_project", "endpoint": "/open_api/v3.0/project/create/", "payload": {}})

    assert response == {"code": 500, "message": "server error"}
    assert calls["count"] == 1
    assert len((tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_create_http_transport_retries_configured_api_code_for_material_bind(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = {"count": 0}
    sleeps = []

    def fake_opener(_url, _body, _headers, _timeout_seconds, _method):
        calls["count"] += 1
        if calls["count"] == 1:
            return HttpResponse(200, {"code": 40100, "message": "系统请求频率超限，请稍后重试。"})
        return HttpResponse(200, {"code": 0, "data": {"task_id": "bind-001"}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "max_retries": 1,
            "retry_sleep_seconds": 0.5,
            "retry_api_codes_by_operation": {"bind_material": [40100]},
        },
        response_dir=tmp_path,
        opener=fake_opener,
        sleeper=sleeps.append,
    )

    response = transport(
        {
            "operation": "bind_material",
            "endpoint": "/open_api/2/file/material/bind/",
            "payload": {
                "source_advertiser_id": "source-1",
                "target_advertiser_ids": ["target-1"],
                "source_video_ids": ["video-1"],
            },
        }
    )
    audit_lines = (tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()

    assert response == {"code": 0, "data": {"task_id": "bind-001"}}
    assert calls["count"] == 2
    assert sleeps == [0.5]
    assert [json.loads(line)["attempt"] for line in audit_lines] == [1, 2]


def test_create_http_transport_retries_transient_error_for_configured_operation(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = {"count": 0}
    sleeps = []

    def fake_opener(_url, _body, _headers, _timeout_seconds, _method):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError(ConnectionResetError(54, "Connection reset by peer"))
        return HttpResponse(200, {"code": 0, "data": {"task_id": "bind-001"}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "max_retries": 1,
            "retry_sleep_seconds": 0.5,
            "retry_transient_operations": ["bind_material"],
        },
        response_dir=tmp_path,
        opener=fake_opener,
        sleeper=sleeps.append,
    )

    response = transport(
        {
            "operation": "bind_material",
            "endpoint": "/open_api/2/file/material/bind/",
            "payload": {},
        }
    )
    audit_lines = (tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()

    assert response == {"code": 0, "data": {"task_id": "bind-001"}}
    assert calls["count"] == 2
    assert sleeps == [0.5]
    assert [json.loads(line)["attempt"] for line in audit_lines] == [1, 2]


def test_create_http_transport_keeps_create_project_non_retryable_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = {"count": 0}

    def fake_opener(_url, _body, _headers, _timeout_seconds, _method):
        calls["count"] += 1
        return HttpResponse(200, {"code": 40100, "message": "系统请求频率超限，请稍后重试。"})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "max_retries": 1,
            "retry_sleep_seconds": 0.5,
            "retry_api_codes_by_operation": {"bind_material": [40100]},
        },
        response_dir=tmp_path,
        opener=fake_opener,
        sleeper=lambda _seconds: None,
    )

    response = transport(
        {"operation": "create_project", "endpoint": "/open_api/v3.0/project/create/", "payload": {}}
    )

    assert response == {"code": 40100, "message": "系统请求频率超限，请稍后重试。"}
    assert calls["count"] == 1


def test_create_http_transport_waits_between_live_create_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    sleeps = []

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "min_interval_seconds": 0.2,
        },
        response_dir=tmp_path,
        opener=lambda *_args, **_kwargs: HttpResponse(200, {"code": 0, "data": {"project_id": "project-001"}}),
        sleeper=sleeps.append,
    )

    transport({"operation": "create_project", "endpoint": "/open_api/v3.0/project/create/", "payload": {}})
    transport({"operation": "create_project", "endpoint": "/open_api/v3.0/project/create/", "payload": {}})

    assert sleeps == [0.2]


def test_create_http_transport_can_wait_by_operation(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    sleeps = []

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "min_interval_seconds": 0.1,
            "min_interval_seconds_by_operation": {
                "lookup_target_material": 0,
                "create_unit": 0.8,
            },
        },
        response_dir=tmp_path,
        opener=lambda *_args, **_kwargs: HttpResponse(200, {"code": 0, "data": {"id": "ok"}}),
        sleeper=sleeps.append,
    )

    transport({"operation": "create_project", "endpoint": "/open_api/v3.0/project/create/", "payload": {}})
    transport({"operation": "lookup_target_material", "endpoint": "/open_api/2/file/video/get/", "payload": {}})
    transport({"operation": "create_unit", "endpoint": "/open_api/v3.0/promotion/create/", "payload": {}})
    transport({"operation": "bind_material", "endpoint": "/open_api/2/file/material/bind/", "payload": {}})

    assert sleeps == [0.8, 0.1]


def test_create_http_transport_returns_http_error_as_response_and_audit(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")

    def fake_opener(_url, _body, _headers, _timeout_seconds, _method):
        raise urllib.error.HTTPError(
            url="https://api.oceanengine.com/open_api/v3.0/project/create/",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "run_id": "run-001",
            "operator": "tester",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    response = transport({"operation": "create_project", "endpoint": "/open_api/v3.0/project/create/", "payload": {}})
    audit = json.loads((tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert response["code"] == 404
    assert response["error_type"] == "HTTPError"
    assert audit["status_code"] == 404
    assert audit["request"]["headers"]["Access-Token"] == "<redacted>"
    assert "secret-token" not in json.dumps(audit, ensure_ascii=False)
