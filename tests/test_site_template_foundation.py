import json
from pathlib import Path

from roibang_v2.workflows.site_template_foundation import build_site_template_foundation_plan
from roibang_v2.workflows.site_template_foundation import build_wechat_game_brick
from roibang_v2.workflows.site_template_foundation import find_wechat_game_index
from roibang_v2.workflows.site_template_foundation import run_site_template_foundation_request


def test_build_wechat_game_brick_uses_explicit_instance_id_and_game_path():
    result = build_wechat_game_brick(
        index="idx-game",
        game_path="?turbo_promoted_object_id=abc",
        instance_id="1866127432211587",
    )

    assert result == {
        "type": "WECHAT_GAME",
        "index": "idx-game",
        "wechat_game": {
            "instance_id": 1866127432211587,
            "game_path": "?turbo_promoted_object_id=abc",
        },
    }


def test_find_wechat_game_index_reads_template_bricks():
    assert (
        find_wechat_game_index(
            [
                {"type": "PICTURE", "index": "idx-picture"},
                {"type": "WECHAT_GAME", "index": "idx-game", "wechat_game": {"instance_id": 123}},
            ]
        )
        == "idx-game"
    )


def test_build_site_template_foundation_plan_stays_dry_run_and_uses_partial_brick():
    result = build_site_template_foundation_plan(
        {
            "site_template_foundation": {
                "template_id": "777",
                "source_advertiser_id": "1866125087858183",
                "wechat_game_index": "idx-game",
                "game_instance_id": "1866127432211587",
                "game_path": "?turbo_promoted_object_id=abc",
                "target_advertiser_ids": ["2001", "2002"],
                "publish": False,
            }
        }
    )

    assert result["ok"] is True
    assert result["execution_enabled"] is False
    assert result["summary"]["target_count"] == 2
    assert [request["operation"] for request in result["requests"]] == [
        "create_site_from_template",
        "create_site_from_template",
    ]
    assert result["requests"][0]["payload"]["bricks"] == [
        {
            "type": "WECHAT_GAME",
            "index": "idx-game",
            "wechat_game": {
                "instance_id": 1866127432211587,
                "game_path": "?turbo_promoted_object_id=abc",
            },
        }
    ]


def test_build_site_template_foundation_plan_reads_existing_site_artifact(tmp_path: Path):
    artifact = tmp_path / "handsel.json"
    artifact.write_text(
        json.dumps(
            {
                "success_list": [
                    {"target_advertiser_id": "2001", "site_id": "9001"},
                    {"target_advertiser_id": "2002", "site_id": "9002"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_site_template_foundation_plan(
        {
            "site_template_foundation": {
                "template_id": "777",
                "source_advertiser_id": "1866125087858183",
                "wechat_game_index": "idx-game",
                "game_instance_id": "1866127432211587",
                "game_path": "?turbo_promoted_object_id=abc",
                "site_mapping_artifact": str(artifact),
                "edit_existing": True,
            }
        }
    )

    assert result["ok"] is True
    assert result["summary"]["edit_existing"] is True
    assert result["targets"] == [
        {"advertiser_id": "2001", "site_id": "9001"},
        {"advertiser_id": "2002", "site_id": "9002"},
    ]
    assert result["requests"][0]["payload"]["site_id"] == 9001


def test_run_site_template_foundation_creates_template_sites_and_publishes(tmp_path: Path):
    calls = []

    def fake_transport(request):
        calls.append(request)
        if request["operation"] == "create_site_template":
            return {
                "code": 0,
                "data": {
                    "template_id": "777",
                    "bricks": [{"type": "WECHAT_GAME", "index": "idx-game"}],
                },
            }
        if request["operation"] == "create_site_from_template":
            return {"code": 0, "data": {"site_id": "9001"}}
        if request["operation"] == "publish_site":
            return {"code": 0, "data": {}}
        raise AssertionError(request)

    result = run_site_template_foundation_request(
        {
            "site_template_foundation": {
                "source_advertiser_id": "1866125087858183",
                "source_site_id": "7643710255184904243",
                "template_name": "点点英雄模板",
                "game_instance_id": "1866127432211587",
                "game_path": "?turbo_promoted_object_id=abc",
                "target_advertiser_ids": ["2001"],
                "execute": True,
            }
        },
        config={},
        runs_dir=tmp_path / "runs",
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert result["summary"]["template_id"] == "777"
    assert result["summary"]["wechat_game_index"] == "idx-game"
    assert result["success_list"][0]["site_id"] == "9001"
    assert [call["operation"] for call in calls] == [
        "create_site_template",
        "create_site_from_template",
        "publish_site",
    ]
    create_payload = calls[1]["payload"]
    assert create_payload["template_id"] == 777
    assert create_payload["bricks"][0]["wechat_game"]["instance_id"] == 1866127432211587
    assert json.loads(Path(result["artifact_path"]).read_text(encoding="utf-8"))["workflow"] == "site_template_foundation"


def test_run_site_template_foundation_gets_template_index_when_missing(tmp_path: Path):
    calls = []

    def fake_transport(request):
        calls.append(request)
        if request["operation"] == "get_site_template":
            return {
                "code": 0,
                "data": {"list": [{"bricks": [{"type": "WECHAT_GAME", "index": "idx-game"}]}]},
            }
        if request["operation"] == "create_site_from_template":
            return {"code": 0, "data": {"site_id": "9001"}}
        return {"code": 0, "data": {}}

    result = run_site_template_foundation_request(
        {
            "site_template_foundation": {
                "source_advertiser_id": "1866125087858183",
                "template_id": "777",
                "game_instance_id": "1866127432211587",
                "game_path": "?turbo_promoted_object_id=abc",
                "target_advertiser_ids": ["2001"],
                "execute": True,
                "publish": False,
            }
        },
        config={},
        runs_dir=tmp_path / "runs",
        transport=fake_transport,
    )

    assert result["ok"] is True
    assert [call["operation"] for call in calls] == ["get_site_template", "create_site_from_template"]
    assert result["summary"]["wechat_game_index"] == "idx-game"


def test_build_site_template_foundation_blocks_missing_game_instance_id():
    result = build_site_template_foundation_plan(
        {
            "site_template_foundation": {
                "template_id": "777",
                "source_advertiser_id": "1866125087858183",
                "wechat_game_index": "idx-game",
                "game_path": "?turbo_promoted_object_id=abc",
                "target_advertiser_ids": ["2001"],
            }
        }
    )

    assert result["ok"] is False
    assert "missing game_instance_id" in result["blocking_reasons"]
