import json
from pathlib import Path

import pytest

from roibang_v2.fetch.openapi_http import HttpResponse
from roibang_v2.fetch.workbench_material_center import (
    WorkbenchMaterialCenterError,
    fetch_video_materials,
)


def _session_file(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "cookie": "sessionid=secret-session; csrftoken=secret-cookie-token",
                "csrf_token": "secret-csrf-token",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _response(materials, *, page=1, has_more=False, total=1):
    return HttpResponse(
        200,
        {
            "code": 0,
            "msg": "",
            "data": {
                "materials": materials,
                "page_info": {"has_more": has_more, "page": page, "limit": len(materials), "total_count": str(total)},
            },
        },
    )


def test_material_center_fetch_paginates_and_redacts_browser_session(tmp_path):
    calls = []
    responses = [
        _response(
            [
                {
                    "material_id": "7634377721926238234",
                    "title": "推送视频_XX-0428-SP-AI+武将闯关-ZY",
                    "vid": "v02033g10000d7pc492ljht7a62rfm80",
                    "audit_result": {"status": 3},
                    "material_properties": [1004, 1],
                    "video_duration": 32.903,
                    "metrics": {"stat_cost": "0.07"},
                }
            ],
            page=1,
            has_more=True,
            total=2,
        ),
        _response(
            [
                {
                    "material_id": "7632149633851801636",
                    "title": "推送视频_B",
                    "vid": "v2",
                    "metrics": {"stat_cost": "0.00"},
                }
            ],
            page=2,
            has_more=False,
            total=2,
        ),
    ]

    def opener(url, body, headers, timeout_seconds):
        calls.append({"url": url, "body": body, "headers": headers, "timeout_seconds": timeout_seconds})
        return responses.pop(0)

    result = fetch_video_materials(
        {
            "enabled": True,
            "session_file": str(_session_file(tmp_path / "session.json")),
            "limit": 1,
            "max_pages": 2,
            "response_audit_dir": str(tmp_path / "audit"),
            "scene": "333430303336343739",
        },
        advertiser_id="1856647523922953",
        statistic_start_time="2026-05-01 00:00:00",
        statistic_end_time="2026-05-08 23:59:59",
        opener=opener,
    )

    assert [call["body"]["page"] for call in calls] == [1, 2]
    assert calls[0]["body"]["order_field"] == "create_time"
    assert calls[0]["body"]["fields"]
    assert calls[0]["url"].endswith("?aadvid=1856647523922953")
    assert calls[0]["headers"]["Cookie"].startswith("sessionid=secret-session")
    assert result["summary"]["transport_calls"] == 2
    assert result["summary"]["rows_received"] == 2
    assert result["summary"]["total_count"] == 2
    assert result["materials"][0]["advertiser_id"] == "1856647523922953"
    assert result["materials"][0]["material_id"] == "7634377721926238234"

    audit_text = (tmp_path / "audit" / "material_center_video_material_list.jsonl").read_text(encoding="utf-8")
    audit = json.loads(audit_text.splitlines()[0])
    assert audit["request"]["headers"] == {"Cookie": "<redacted>", "x-csrftoken": "<redacted>"}
    assert "secret-session" not in audit_text
    assert "secret-csrf-token" not in audit_text


def test_material_center_fetch_honors_nested_limits_max_pages(tmp_path):
    calls = []

    def opener(_url, body, _headers, _timeout_seconds):
        calls.append(body["page"])
        return _response(
            [{"material_id": f"m-{body['page']}", "title": "A"}],
            page=body["page"],
            has_more=True,
            total=999,
        )

    result = fetch_video_materials(
        {
            "enabled": True,
            "session_file": str(_session_file(tmp_path / "session.json")),
            "limit": 10,
            "limits": {"max_pages": 1},
            "response_audit_dir": str(tmp_path / "audit"),
        },
        advertiser_id="1856647523922953",
        statistic_start_time="2026-05-01 00:00:00",
        statistic_end_time="2026-05-08 23:59:59",
        opener=opener,
    )

    assert calls == [1]
    assert result["summary"]["transport_calls"] == 1
    assert result["summary"]["rows_received"] == 1


def test_material_center_fetch_filters_created_at_range_and_stops_when_sorted_older(tmp_path):
    calls = []
    responses = [
        _response(
            [
                {"material_id": "today-1", "title": "A", "created_at": "2026-05-08T15:00:00+08:00"},
                {"material_id": "today-2", "title": "B", "created_at": "2026-05-08T09:00:00+08:00"},
            ],
            page=1,
            has_more=True,
            total=4,
        ),
        _response(
            [
                {"material_id": "older-1", "title": "C", "created_at": "2026-05-07T23:59:59+08:00"},
                {"material_id": "older-2", "title": "D", "created_at": "2026-05-07T12:00:00+08:00"},
            ],
            page=2,
            has_more=True,
            total=4,
        ),
    ]

    def opener(_url, body, _headers, _timeout_seconds):
        calls.append(body["page"])
        return responses.pop(0)

    result = fetch_video_materials(
        {
            "enabled": True,
            "session_file": str(_session_file(tmp_path / "session.json")),
            "limit": 2,
            "max_pages": 10,
            "created_at_range": {
                "start": "2026-05-08 00:00:00",
                "end": "2026-05-08 23:59:59",
            },
            "stop_when_created_before_range": True,
            "response_audit_dir": str(tmp_path / "audit"),
        },
        advertiser_id="1856647523922953",
        statistic_start_time="2026-05-08 00:00:00",
        statistic_end_time="2026-05-08 23:59:59",
        opener=opener,
    )

    assert calls == [1, 2]
    assert [row["material_id"] for row in result["materials"]] == ["today-1", "today-2"]
    assert result["summary"]["rows_received"] == 4
    assert result["summary"]["rows_importable"] == 2
    assert result["summary"]["stopped_by_created_at_range"] is True


def test_material_center_fetch_fails_closed_when_disabled(tmp_path):
    with pytest.raises(WorkbenchMaterialCenterError, match="disabled"):
        fetch_video_materials(
            {"enabled": False, "session_file": str(_session_file(tmp_path / "session.json"))},
            advertiser_id="1856647523922953",
            statistic_start_time="2026-05-01 00:00:00",
            statistic_end_time="2026-05-08 23:59:59",
            opener=lambda *_args: _response([]),
        )
