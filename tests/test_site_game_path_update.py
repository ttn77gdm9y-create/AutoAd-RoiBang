import json
from pathlib import Path

from roibang_v2.workflows.site_game_path_update import build_site_game_path_update_plan
from roibang_v2.workflows.site_game_path_update import normalize_site_update_bricks
from roibang_v2.workflows.site_game_path_update import run_site_game_path_update_request
from roibang_v2.workflows.site_game_path_update import update_wechat_game_bricks


def test_update_wechat_game_bricks_sets_path_and_instance_id():
    bricks = [
        {"name": "XrPicture", "url": "https://example.com/a.png"},
        {"name": "XrWechatGame", "instance_id": 1, "game_path": ""},
    ]

    updated, count = update_wechat_game_bricks(
        bricks,
        game_path="?turbo_promoted_object_id=abc",
        instance_id="123",
    )

    assert count == 1
    assert updated[1]["instance_id"] == 123
    assert updated[1]["game_path"] == "?turbo_promoted_object_id=abc"
    assert bricks[1]["game_path"] == ""


def test_normalize_site_update_bricks_converts_color_objects():
    bricks = [
        {
            "name": "XrWechatGame",
            "setting": {
                "title": {"color": {"color": "#222"}},
                "label": {"color": {"color": "#444"}},
                "button": {
                    "color": {"color": "#fff"},
                    "background_color": {"color": "#FE2C55"},
                    "border_color": {"color": "#FE2C55"},
                },
                "background": {"color": {"color": "rgba(255, 255, 255, 1)"}},
            },
        }
    ]

    result = normalize_site_update_bricks(bricks)

    assert result[0]["setting"]["title"]["color"] == "#222"
    assert result[0]["setting"]["label"]["color"] == "#444"
    assert result[0]["setting"]["button"]["color"] == "#fff"
    assert result[0]["setting"]["button"]["background_color"] == "#FE2C55"
    assert result[0]["setting"]["button"]["border_color"] == "#FE2C55"
    assert result[0]["setting"]["background"]["color"] == "rgba(255, 255, 255, 1)"


def test_build_site_game_path_update_plan_reads_handsel_artifact(tmp_path: Path):
    artifact = tmp_path / "handsel.json"
    artifact.write_text(
        json.dumps(
            {
                "success_list": [
                    {"target_advertiser_id": "1861", "site_id": "site-1"},
                    {"target_advertiser_id": "1862", "site_id": "site-2"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_site_game_path_update_plan(
        {
            "site_game_path_update": {
                "handsel_artifact": str(artifact),
                "game_path": "?turbo_promoted_object_id=abc",
            }
        }
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["summary"]["site_count"] == 2


def test_run_site_game_path_update_executes_read_update_publish(tmp_path: Path):
    site_calls = []
    api_calls = []

    def fake_api_transport(request):
        api_calls.append(request)
        return {"code": 0, "data": {"list": [{"name": "点点英雄", "instance_id": "123"}]}}

    def fake_site_transport(request):
        site_calls.append(request)
        if request["operation"] == "read_site":
            return {
                "code": 0,
                "data": {
                    "name": "点点英雄落地页",
                    "bricks": [{"name": "XrWechatGame", "instance_id": 1, "game_path": ""}],
                },
            }
        return {"code": 0, "message": "OK", "data": {}}

    result = run_site_game_path_update_request(
        {
            "site_game_path_update": {
                "sites": [{"advertiser_id": "1861", "site_id": "site-1"}],
                "game_path": "?turbo_promoted_object_id=abc",
                "execute": True,
                "allow_unsafe_full_site_update": True,
            }
        },
        config={},
        runs_dir=tmp_path / "runs",
        site_transport=fake_site_transport,
        api_transport=fake_api_transport,
    )

    assert result["ok"] is True
    assert result["summary"]["success_count"] == 1
    assert [call["operation"] for call in api_calls] == ["list_wechat_game"]
    assert [call["operation"] for call in site_calls] == ["read_site", "update_site", "publish_site"]
    update_payload = site_calls[1]["payload"]
    assert update_payload["bricks"][0]["game_path"] == "?turbo_promoted_object_id=abc"
    assert update_payload["bricks"][0]["instance_id"] == 123
    assert json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "site_game_path_update"


def test_run_site_game_path_update_tries_shared_game_search(tmp_path: Path):
    api_calls = []

    def fake_api_transport(request):
        api_calls.append(request)
        search_type = request["payload"]["filtering"]["search_type"]
        if search_type == "CREATE_ONLY":
            return {"code": 0, "data": {"list": []}}
        return {"code": 0, "data": {"list": [{"name": "点点英雄", "instance_id": "456"}]}}

    def fake_site_transport(request):
        if request["operation"] == "read_site":
            return {"code": 0, "data": {"bricks": [{"name": "XrWechatGame"}]}}
        return {"code": 0, "data": {}}

    result = run_site_game_path_update_request(
        {
            "site_game_path_update": {
                "sites": [{"advertiser_id": "1861", "site_id": "site-1"}],
                "game_path": "?turbo_promoted_object_id=abc",
                "execute": True,
                "allow_unsafe_full_site_update": True,
            }
        },
        config={},
        runs_dir=tmp_path / "runs",
        site_transport=fake_site_transport,
        api_transport=fake_api_transport,
    )

    assert result["ok"] is True
    assert [call["payload"]["filtering"]["search_type"] for call in api_calls] == ["CREATE_ONLY", "SHARE_ONLY"]
    assert result["success_list"][0]["instance_id"] == "456"


def test_run_site_game_path_update_blocks_unsafe_execute_by_default(tmp_path: Path):
    result = run_site_game_path_update_request(
        {
            "site_game_path_update": {
                "sites": [{"advertiser_id": "1861", "site_id": "site-1"}],
                "game_path": "?turbo_promoted_object_id=abc",
                "execute": True,
            }
        },
        config={},
        runs_dir=tmp_path / "runs",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "unsafe full site update is disabled; use site_template_foundation instead" in result["blocking_reasons"]
