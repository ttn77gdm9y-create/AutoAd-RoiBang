from __future__ import annotations

from typing import Any


def phase1_noop_result(workflow: str, policy: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "phase": "phase1",
        "status": "noop",
        "execution_enabled": False,
        "external_api_calls": 0,
        "policy_version": policy.get("policy_version"),
        "message": "Phase 1 placeholder generated locally; no business action executed.",
    }
