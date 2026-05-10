from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


def _approval_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_live_approval")
    return dict(value) if isinstance(value, dict) else dict(request)


def _canonical_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in artifact.items() if key != "artifact_path"}


def artifact_digest(artifact: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(
        _canonical_artifact(artifact),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "algorithm": "sha256",
        "value": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _parse_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _now(now_iso: str | None) -> datetime:
    if now_iso:
        parsed = _parse_time(now_iso)
        if parsed is not None:
            return parsed
    return datetime.now(timezone.utc)


def _runbook_scope(runbook: dict[str, Any]) -> dict[str, Any]:
    value = runbook.get("scope")
    return dict(value) if isinstance(value, dict) else {}


def _requested_scope(approval_request: dict[str, Any]) -> dict[str, Any]:
    value = approval_request.get("scope")
    return dict(value) if isinstance(value, dict) else {}


def _approved_artifacts(approval_request: dict[str, Any]) -> dict[str, Any]:
    value = approval_request.get("approved_artifacts")
    return dict(value) if isinstance(value, dict) else {}


def _digest_contract(
    *,
    approval_request: dict[str, Any],
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
) -> dict[str, Any]:
    approved = _approved_artifacts(approval_request)
    actual = {
        "create_execute": artifact_digest(create_execute_artifact),
        "create_first_live_runbook": artifact_digest(create_first_live_runbook_artifact),
        "create_live_payload_adapter_scaffold": artifact_digest(create_live_payload_adapter_scaffold_artifact),
    }
    rows: dict[str, Any] = {}
    for workflow, actual_digest in actual.items():
        expected = approved.get(workflow) if isinstance(approved.get(workflow), dict) else {}
        rows[workflow] = {
            "expected": {
                "algorithm": str(expected.get("algorithm") or ""),
                "value": str(expected.get("value") or ""),
            },
            "actual": actual_digest,
            "matches": str(expected.get("algorithm") or "") == "sha256"
            and str(expected.get("value") or "") == str(actual_digest["value"]),
        }
    return {
        "all_match": all(bool(row.get("matches", False)) for row in rows.values()),
        "artifacts": rows,
    }


def _violations(
    *,
    approval_request: dict[str, Any],
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    digest_contract: dict[str, Any],
    now: datetime,
) -> list[str]:
    violations: list[str] = []
    if not str(approval_request.get("approval_id") or "").strip():
        violations.append("approval_id is required")
    if not str(approval_request.get("approved_by") or "").strip():
        violations.append("approved_by is required")
    if str(approval_request.get("target_workflow") or "") != "create_live_execute_runner":
        violations.append("target_workflow must be create_live_execute_runner")
    expires_at = _parse_time(str(approval_request.get("expires_at") or ""))
    if expires_at is None:
        violations.append("expires_at is required")
    elif expires_at <= now:
        violations.append("approval has expired")
    if _requested_scope(approval_request) != _runbook_scope(create_first_live_runbook_artifact):
        violations.append("approval scope must match first live runbook scope")
    if str(create_first_live_runbook_artifact.get("status") or "") != "ready_for_human_approval":
        violations.append("first live runbook must be ready_for_human_approval")
    for name, artifact in {
        "create_execute": create_execute_artifact,
        "create_first_live_runbook": create_first_live_runbook_artifact,
        "create_live_payload_adapter_scaffold": create_live_payload_adapter_scaffold_artifact,
    }.items():
        if bool(artifact.get("execution_enabled", False)):
            violations.append(f"{name} execution_enabled must be false")
        if int(artifact.get("external_api_calls") or 0) != 0:
            violations.append(f"{name} external_api_calls must be 0")
    artifacts = digest_contract.get("artifacts") if isinstance(digest_contract.get("artifacts"), dict) else {}
    for workflow, row in artifacts.items():
        if not bool(row.get("matches", False)):
            violations.append(f"approved {workflow} digest does not match current artifact")
    return violations


def _approval_payload(approval_request: dict[str, Any], *, approved: bool) -> dict[str, Any]:
    return {
        "approved": approved,
        "approval_id": str(approval_request.get("approval_id") or ""),
        "approved_by": str(approval_request.get("approved_by") or ""),
        "approved_at": str(approval_request.get("approved_at") or ""),
        "expires_at": str(approval_request.get("expires_at") or ""),
        "target_workflow": str(approval_request.get("target_workflow") or ""),
        "allow_create_http_transport": bool(approval_request.get("allow_create_http_transport", False)) if approved else False,
    }


def _runner_policy_fragment(approval: dict[str, Any]) -> dict[str, Any]:
    if not bool(approval.get("approved", False)):
        return {}
    return {
        "create_live_execute_runner": {
            "allow_create_http_transport": bool(approval.get("allow_create_http_transport", False)),
            "human_approval": {
                "approved": True,
                "approval_id": str(approval.get("approval_id") or ""),
                "approved_by": str(approval.get("approved_by") or ""),
            },
        }
    }


def build_create_live_approval(
    *,
    approval_request: dict[str, Any],
    create_execute_artifact: dict[str, Any],
    create_first_live_runbook_artifact: dict[str, Any],
    create_live_payload_adapter_scaffold_artifact: dict[str, Any],
    now_iso: str | None = None,
) -> dict[str, Any]:
    current_time = _now(now_iso)
    digest_contract = _digest_contract(
        approval_request=approval_request,
        create_execute_artifact=create_execute_artifact,
        create_first_live_runbook_artifact=create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
    )
    violations = _violations(
        approval_request=approval_request,
        create_execute_artifact=create_execute_artifact,
        create_first_live_runbook_artifact=create_first_live_runbook_artifact,
        create_live_payload_adapter_scaffold_artifact=create_live_payload_adapter_scaffold_artifact,
        digest_contract=digest_contract,
        now=current_time,
    )
    approval = _approval_payload(approval_request, approved=not violations)
    return {
        "ok": not violations,
        "workflow": "create_live_approval",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "approved" if not violations else "blocked",
        "approval": approval,
        "scope": _runbook_scope(create_first_live_runbook_artifact),
        "artifact_digest_contract": digest_contract,
        "runner_policy_fragment": _runner_policy_fragment(approval),
        "violations": violations,
        "actions": [],
    }


def run_create_live_approval_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _approval_config(request)
    approval_request = cfg.get("approval_request")
    create_execute = cfg.get("create_execute_artifact")
    runbook = cfg.get("create_first_live_runbook_artifact")
    scaffold = cfg.get("create_live_payload_adapter_scaffold_artifact")
    if not isinstance(approval_request, dict):
        raise ValueError("create live approval requires approval_request")
    if not isinstance(create_execute, dict):
        raise ValueError("create live approval requires create_execute_artifact")
    if not isinstance(runbook, dict):
        raise ValueError("create live approval requires create_first_live_runbook_artifact")
    if not isinstance(scaffold, dict):
        raise ValueError("create live approval requires create_live_payload_adapter_scaffold_artifact")
    payload = build_create_live_approval(
        approval_request=approval_request,
        create_execute_artifact=create_execute,
        create_first_live_runbook_artifact=runbook,
        create_live_payload_adapter_scaffold_artifact=scaffold,
        now_iso=str(cfg.get("now_iso") or "") or None,
    )
    artifact_path = write_run_artifact(runs_dir, "create_live_approval", payload)
    return {**payload, "artifact_path": str(artifact_path)}
