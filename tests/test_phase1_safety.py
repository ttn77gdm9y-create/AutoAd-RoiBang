from roibang_v2.workflows.placeholders import phase1_noop_result
from roibang_v2.config import load_runtime_config


def test_phase1_placeholder_cannot_execute_business_actions():
    result = phase1_noop_result("strategy_plan", {"policy_version": "test"})

    assert result["phase"] == "phase1"
    assert result["status"] == "noop"
    assert result["execution_enabled"] is False
    assert result["external_api_calls"] == 0


def test_openapi_execute_runtime_allows_readonly_external_api_only():
    config = load_runtime_config("configs/runtime.openapi-execute.local.example.json")

    assert config.external_api_enabled is True
    assert config.execution_enabled is False
    assert config.phase == "phase1"
