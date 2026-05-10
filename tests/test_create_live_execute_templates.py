import json
from pathlib import Path

from roibang_v2.config import load_runtime_config


LIVE_RUNTIME_TEMPLATE = Path("configs/runtime.create-live.local.example.json")
LIVE_POLICY_TEMPLATE = Path("policies/create-live-execute.local.example.json")
SCHEDULER_TEMPLATE = Path("configs/scheduler/roibang-v2.jobs.example.json")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_live_create_runtime_template_is_explicit_execute_config():
    config = load_runtime_config(LIVE_RUNTIME_TEMPLATE)

    assert config.phase == "phase2"
    assert config.external_api_enabled is True
    assert config.execution_enabled is True
    assert config.database_path == Path("data/roibang_v2.sqlite3")
    assert config.runs_dir == Path("data/runs")


def test_live_create_policy_template_is_minimal_direct_execute_contract():
    policy = _load_json(LIVE_POLICY_TEMPLATE)
    live_api = policy["create_execute"]["live_api"]
    payload_schema = policy["create_execute"]["payload_schema"]
    runner = policy["create_live_execute_runner"]
    transport = runner["create_http_transport"]

    assert live_api == {
        "enabled": True,
        "transport": "openapi_http",
        "endpoints": {
            "create_project": "/open_api/2/project/create/",
            "bind_material": "/open_api/2/file/material/bind/",
            "lookup_target_material": "/open_api/2/file/video/get/",
            "create_unit": "/open_api/2/promotion/create/",
        },
    }
    assert payload_schema["live_payload_generation_enabled"] is True
    assert runner["allow_create_http_transport"] is True
    assert runner["require_provider_field_mapping"] is True
    assert transport["enabled"] is True
    assert transport["allow_mutation"] is True
    assert transport["approval_id"]
    assert transport["token_env"] == "OCEANENGINE_ACCESS_TOKEN"
    assert "token" not in json.dumps(policy).replace("token_env", "")


def test_live_create_templates_are_not_scheduler_defaults():
    scheduler = SCHEDULER_TEMPLATE.read_text(encoding="utf-8")

    assert str(LIVE_RUNTIME_TEMPLATE) not in scheduler
    assert str(LIVE_POLICY_TEMPLATE) not in scheduler
