import json

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


def test_create_http_transport_requires_mutation_approval_and_token(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")

    with pytest.raises(RuntimeError, match="allow_mutation"):
        build_create_http_transport(
            {
                "enabled": True,
                "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
                "approval_id": "approval-001",
            },
            response_dir=tmp_path,
            opener=lambda *_args, **_kwargs: HttpResponse(200, {}),
        )

    with pytest.raises(RuntimeError, match="approval_id"):
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

    def fake_opener(url, body, headers, timeout_seconds):
        calls.append(
            {
                "url": url,
                "body": body,
                "headers": headers,
                "timeout_seconds": timeout_seconds,
            }
        )
        return HttpResponse(200, {"code": 0, "data": {"project_id": "project-001"}})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "approval_id": "approval-001",
            "approved_by": "tester",
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
            "endpoint": "/open_api/2/project/create/",
            "payload": {"advertiser_id": "target-1", "name": "首单测试"},
        }
    )
    audit = json.loads((tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()[0])

    assert response == {"code": 0, "data": {"project_id": "project-001"}}
    assert calls == [
        {
            "url": "https://api.oceanengine.com/open_api/2/project/create/",
            "body": {"advertiser_id": "target-1", "name": "首单测试"},
            "headers": {
                "Access-Token": "secret-token",
                "Content-Type": "application/json",
            },
            "timeout_seconds": 7,
        }
    ]
    assert audit["request"]["headers"] == {
        "Access-Token": "<redacted>",
        "Content-Type": "application/json",
    }
    assert audit["approval"] == {"approval_id": "approval-001", "approved_by": "tester"}
    assert "secret-token" not in json.dumps(audit, ensure_ascii=False)


def test_create_http_transport_rejects_unknown_or_mismatched_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "approval_id": "approval-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
        },
        response_dir=tmp_path,
        opener=lambda *_args, **_kwargs: HttpResponse(200, {"code": 0}),
    )

    with pytest.raises(RuntimeError, match="not in create endpoint allowlist"):
        transport({"operation": "delete_project", "endpoint": "/open_api/2/project/delete/", "payload": {}})

    with pytest.raises(RuntimeError, match="does not match operation"):
        transport({"operation": "create_unit", "endpoint": "/open_api/2/project/create/", "payload": {}})


def test_create_http_transport_does_not_retry_mutating_requests(monkeypatch, tmp_path):
    monkeypatch.setenv("ROIBANG_TEST_ACCESS_TOKEN", "secret-token")
    calls = {"count": 0}

    def fake_opener(_url, _body, _headers, _timeout_seconds):
        calls["count"] += 1
        return HttpResponse(500, {"code": 500, "message": "server error"})

    transport = build_create_http_transport(
        {
            "enabled": True,
            "allow_mutation": True,
            "approval_id": "approval-001",
            "token_env": "ROIBANG_TEST_ACCESS_TOKEN",
            "max_retries": 3,
        },
        response_dir=tmp_path,
        opener=fake_opener,
    )

    with pytest.raises(RuntimeError, match="status 500"):
        transport({"operation": "create_project", "endpoint": "/open_api/2/project/create/", "payload": {}})

    assert calls["count"] == 1
    assert len((tmp_path / "create_http_responses.jsonl").read_text(encoding="utf-8").splitlines()) == 1
