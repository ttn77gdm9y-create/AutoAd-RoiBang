import json
from pathlib import Path

import pytest

from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.fetch.workbench_account_discovery import (
    WorkbenchAccountDiscoveryError,
    discover_spending_accounts,
)


def _secret_file(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "cookie": "sessionid=secret-session; csrftoken=secret-cookie-token",
                "csrf_token": "secret-csrf-token",
                "ebpid": "1851650746645060",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _response(items, *, page=1, has_more=False, total=481):
    return HttpResponse(
        200,
        {
            "code": 0,
            "data": {
                "list": items,
                "pagination": {"page": page, "limit": 100, "total": total, "hasMore": has_more},
            },
            "msg": "",
        },
    )


def test_workbench_discovery_parses_sorted_spending_accounts_and_redacts_audit(tmp_path):
    calls = []

    def opener(url, body, headers, timeout_seconds):
        calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds})
        return _response(
            [
                {
                    "advertiser_id": "1856647524935691",
                    "advertiser_name": "黑旗-勇者突进-微小-傲星-155",
                    "advertiser_remark": "勇者突进-微小-郭靖",
                    "metrics": {"stat_cost": "8,130.95", "ctr": "1.23%"},
                },
                {
                    "advertiser_id": "1858371347608587",
                    "advertiser_name": "黑旗-勇者突进-微小-傲星-451",
                    "metrics": {"stat_cost": "0.00"},
                },
            ],
            has_more=True,
        )

    result = discover_spending_accounts(
        {
            "enabled": True,
            "session_file": str(_secret_file(tmp_path / "session.json")),
            "keyword": "勇者突进-微小",
            "limit": 100,
            "stop_when_sorted_cost_reaches_zero": True,
            "response_audit_dir": str(tmp_path / "audit"),
        },
        target_date="2026-05-01",
        min_spend=0,
        opener=opener,
    )

    assert result["active_account_ids"] == ["1856647524935691"]
    assert result["accounts"][0]["stat_cost"] == 8130.95
    assert result["accounts"][0]["ctr"] == 1.23
    assert result["summary"]["transport_calls"] == 1
    assert result["summary"]["rows_received"] == 2
    assert calls[0]["body"]["offset"] == 1
    assert calls[0]["body"]["orderField"] == "stat_cost"
    assert calls[0]["headers"]["Cookie"].startswith("sessionid=secret-session")
    assert calls[0]["headers"]["x-csrftoken"] == "secret-csrf-token"

    audit_text = (tmp_path / "audit" / "workbench_account_list.jsonl").read_text(encoding="utf-8")
    audit = json.loads(audit_text.splitlines()[0])
    assert audit["request"]["headers"] == {"Cookie": "<redacted>", "x-csrftoken": "<redacted>"}
    assert "secret-session" not in audit_text
    assert "secret-csrf-token" not in audit_text


def test_workbench_discovery_paginates_until_no_more_when_all_rows_positive(tmp_path):
    responses = [
        _response(
            [
                {"advertiser_id": "a1", "advertiser_name": "A1", "metrics": {"stat_cost": "12.50"}},
            ],
            page=1,
            has_more=True,
            total=2,
        ),
        _response(
            [
                {"advertiser_id": "a2", "advertiser_name": "A2", "metrics": {"stat_cost": "1.00"}},
            ],
            page=2,
            has_more=False,
            total=2,
        ),
    ]
    offsets = []

    def opener(_url, body, _headers, _timeout_seconds):
        offsets.append(body["offset"])
        return responses.pop(0)

    result = discover_spending_accounts(
        {
            "enabled": True,
            "session_file": str(_secret_file(tmp_path / "session.json")),
            "keyword": "勇者突进-微小",
            "limit": 100,
            "response_audit_dir": str(tmp_path / "audit"),
        },
        target_date="2026-05-01",
        min_spend=0,
        opener=opener,
    )

    assert result["active_account_ids"] == ["a1", "a2"]
    assert offsets == [1, 2]
    assert result["summary"]["candidate_account_count"] == 2
    assert result["summary"]["active_account_count"] == 2


def test_workbench_discovery_stops_at_configured_max_pages(tmp_path):
    offsets = []

    def opener(_url, body, _headers, _timeout_seconds):
        offsets.append(body["offset"])
        return _response(
            [
                {
                    "advertiser_id": f"a{body['offset']}",
                    "advertiser_name": f"A{body['offset']}",
                    "metrics": {"stat_cost": "12.50"},
                },
            ],
            page=body["offset"],
            has_more=True,
            total=300,
        )

    result = discover_spending_accounts(
        {
            "enabled": True,
            "session_file": str(_secret_file(tmp_path / "session.json")),
            "keyword": "勇者突进-微小",
            "limit": 100,
            "max_pages": 2,
            "response_audit_dir": str(tmp_path / "audit"),
        },
        target_date="2026-05-01",
        min_spend=0,
        opener=opener,
    )

    assert offsets == [1, 2]
    assert result["active_account_ids"] == ["a1", "a2"]
    assert result["summary"]["transport_calls"] == 2


def test_workbench_discovery_can_restrict_results_to_local_account_pool(tmp_path):
    def opener(_url, _body, _headers, _timeout_seconds):
        return _response(
            [
                {"advertiser_id": "in-pool", "advertiser_name": "In Pool", "metrics": {"stat_cost": "12.50"}},
                {"advertiser_id": "outside-pool", "advertiser_name": "Outside", "metrics": {"stat_cost": "9.00"}},
            ],
            has_more=False,
            total=2,
        )

    result = discover_spending_accounts(
        {
            "enabled": True,
            "session_file": str(_secret_file(tmp_path / "session.json")),
            "keyword": "勇者突进-微小",
            "allowed_account_ids": ["in-pool"],
            "response_audit_dir": str(tmp_path / "audit"),
        },
        target_date="2026-05-01",
        min_spend=0,
        opener=opener,
    )

    assert result["active_account_ids"] == ["in-pool"]
    assert result["summary"]["candidate_account_count"] == 1
    assert result["summary"]["rows_received"] == 2


def test_workbench_discovery_fails_closed_when_disabled(tmp_path):
    with pytest.raises(WorkbenchAccountDiscoveryError, match="disabled"):
        discover_spending_accounts(
            {"enabled": False, "session_file": str(_secret_file(tmp_path / "session.json"))},
            target_date="2026-05-01",
            min_spend=0,
            opener=lambda *_args: _response([]),
        )
