from __future__ import annotations

from typing import Any


def provider_readiness_contract(
    *,
    provider_adapter_contract: dict[str, Any],
    provider_field_map_contract: dict[str, Any],
    payload_draft_contract: dict[str, Any],
) -> dict[str, Any]:
    adapter_verified = bool(provider_adapter_contract.get("mapping_verified", False))
    field_map_verified = str(provider_field_map_contract.get("status") or "") == "verified"
    drafts_non_executable = int(payload_draft_contract.get("executable_draft_count") or 0) == 0
    live_payload_count_zero = int(payload_draft_contract.get("live_payload_count") or 0) == 0
    provider_payloads_fully_mapped = int(provider_adapter_contract.get("unmapped_payload_field_count") or 0) == 0
    blocking_reasons: list[str] = []
    if not adapter_verified:
        blocking_reasons.append("provider adapter mapping is not verified")
    if not field_map_verified:
        blocking_reasons.append("provider field map is not verified")
    if not provider_payloads_fully_mapped:
        blocking_reasons.append("provider payload drafts contain unmapped internal fields")
    if not drafts_non_executable:
        blocking_reasons.append("payload drafts contain executable entries")
    if not live_payload_count_zero:
        blocking_reasons.append("live payloads are present")

    return {
        "status": "ready" if not blocking_reasons else "not_ready",
        "ready_for_live_execute": not blocking_reasons,
        "provider": str(provider_adapter_contract.get("provider") or provider_field_map_contract.get("provider") or ""),
        "checks": {
            "provider_adapter_mapping_verified": adapter_verified,
            "provider_field_map_verified": field_map_verified,
            "provider_payloads_fully_mapped": provider_payloads_fully_mapped,
            "payload_drafts_non_executable": drafts_non_executable,
            "live_payload_count_zero": live_payload_count_zero,
        },
        "blocking_reasons": blocking_reasons,
    }


def not_ready_provider_readiness_contract(provider: str = "oceanengine") -> dict[str, Any]:
    return {
        "status": "not_ready",
        "ready_for_live_execute": False,
        "provider": provider,
        "checks": {
            "provider_adapter_mapping_verified": False,
            "provider_field_map_verified": False,
            "provider_payloads_fully_mapped": True,
            "payload_drafts_non_executable": True,
            "live_payload_count_zero": True,
        },
        "blocking_reasons": [
            "provider adapter mapping is not verified",
            "provider field map is not verified",
        ],
    }
