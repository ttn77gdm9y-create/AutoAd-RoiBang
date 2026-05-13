from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_lineage import create_request_payload


_INVALID_PROJECT_NAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _prep_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_phase2_project_naming_prep")
    return dict(value) if isinstance(value, dict) else dict(request)


def _create_request(value: dict[str, Any]) -> dict[str, Any]:
    if isinstance(value.get("create_request"), dict):
        return create_request_payload(value["create_request"])
    return create_request_payload(value)


def _strategy_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_strategy_plan")
    return dict(value) if isinstance(value, dict) else {}


def _preflight_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = policy.get("create_preflight")
    return dict(value) if isinstance(value, dict) else {}


def _naming_policy(policy: dict[str, Any]) -> dict[str, Any]:
    value = _strategy_policy(policy).get("project_naming")
    return dict(value) if isinstance(value, dict) else {}


def _target_accounts(request: dict[str, Any]) -> list[dict[str, Any]]:
    rows = request.get("target_accounts") if isinstance(request.get("target_accounts"), list) else []
    return [row for row in rows if isinstance(row, dict)]


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _project_name_template(request: dict[str, Any], policy: dict[str, Any]) -> tuple[str, str]:
    naming = _naming_policy(policy)
    if str(naming.get("template") or "").strip():
        return str(naming.get("template") or "").strip(), "policy.create_strategy_plan.project_naming.template"
    if str(request.get("project_name_template") or "").strip():
        return str(request.get("project_name_template") or "").strip(), "create_request.project_name_template"
    return "{product}-{project_type}-{advertiser_id}-{index}", "default"


def _target_date_compact(request: dict[str, Any]) -> str:
    return re.sub(r"\D+", "", str(request.get("target_date") or ""))


def _target_date_mmdd(request: dict[str, Any]) -> str:
    compact = _target_date_compact(request)
    return compact[4:8] if len(compact) >= 8 else compact


def _batch_generated_at(request: dict[str, Any]) -> str:
    value = str(request.get("batch_generated_at") or "").strip()
    if value:
        return value
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _batch_code_source(request: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    return {
        "request_id": str(request.get("request_id") or ""),
        "target_date": str(request.get("target_date") or ""),
        "product": str(request.get("product") or ""),
        "project_type": str(request.get("project_type") or ""),
        "advertiser_ids": [
            str(account.get("advertiser_id") or "")
            for account in _target_accounts(request)
            if str(account.get("advertiser_id") or "")
        ],
        "generated_at": generated_at,
    }


def _batch_code(source_fields: dict[str, Any]) -> str:
    canonical = json.dumps(source_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "B" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8].upper()


def _batch_code_contract(request: dict[str, Any]) -> dict[str, Any]:
    generated_at = _batch_generated_at(request)
    source_fields = _batch_code_source(request, generated_at=generated_at)
    return {
        "batch_code": str(request.get("batch_code") or "").strip() or _batch_code(source_fields),
        "algorithm": "sha256_first_8_uppercase",
        "generated_at": generated_at,
        "source_fields": source_fields,
        "freeze_rule": "generate once in plan, then reuse through preflight, dry-run, and execute",
    }


def _normalize_name(name: str, *, replacement: str) -> str:
    normalized = _INVALID_PROJECT_NAME_CHARS.sub(replacement, name)
    normalized = re.sub(r"\s+", replacement, normalized)
    if replacement:
        normalized = re.sub(f"{re.escape(replacement)}+", replacement, normalized)
        normalized = normalized.strip(replacement)
    return normalized.strip()


def _contract(request: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    naming = _naming_policy(policy)
    preflight = _preflight_policy(policy)
    template, source = _project_name_template(request, policy)
    return {
        "status": "needs_review",
        "template_source": source,
        "template": template,
        "index_width": max(_int_value(naming.get("index_width"), 2), 1),
        "invalid_char_replacement": str(naming.get("invalid_char_replacement") or "-"),
        "max_project_name_length": _int_value(preflight.get("max_project_name_length"), 80),
        "project_name_pattern": str(preflight.get("project_name_pattern") or ""),
        "reject_existing_project_names": bool(preflight.get("reject_existing_project_names", False)),
    }


def _sample_names(request: dict[str, Any], contract: dict[str, Any], batch_contract: dict[str, Any]) -> list[dict[str, Any]]:
    template = str(contract.get("template") or "")
    index_width = int(contract.get("index_width") or 2)
    replacement = str(contract.get("invalid_char_replacement") or "-")
    max_length = int(contract.get("max_project_name_length") or 80)
    pattern = str(contract.get("project_name_pattern") or "")
    samples: list[dict[str, Any]] = []
    for account in _target_accounts(request):
        advertiser_id = str(account.get("advertiser_id") or "")
        project_count = max(_int_value(account.get("project_count"), 1), 0)
        for project_index in range(1, project_count + 1):
            values = {
                "owner": str(request.get("owner") or request.get("belonging") or request.get("name_owner") or ""),
                "product": str(request.get("product") or ""),
                "platform": str(request.get("platform") or ""),
                "project_type": str(request.get("project_type") or ""),
                "project_template_name": str(request.get("project_template_name") or request.get("project_type") or ""),
                "advertiser_id": advertiser_id,
                "index": f"{project_index:0{index_width}d}",
                "target_date": str(request.get("target_date") or ""),
                "target_date_compact": _target_date_compact(request),
                "target_date_mmdd": _target_date_mmdd(request),
                "batch_code": str(batch_contract.get("batch_code") or ""),
            }
            try:
                raw_name = template.format(**values)
            except KeyError:
                raw_name = "{product}-{project_type}-{advertiser_id}-{index}".format(**values)
            project_name = _normalize_name(raw_name, replacement=replacement)
            matches_pattern = True
            if pattern:
                try:
                    matches_pattern = re.fullmatch(pattern, project_name) is not None
                except re.error:
                    matches_pattern = False
            samples.append(
                {
                    "advertiser_id": advertiser_id,
                    "project_index": project_index,
                    "project_name": project_name,
                    "length": len(project_name),
                    "matches_pattern": matches_pattern,
                    "valid": bool(project_name) and len(project_name) <= max_length and matches_pattern,
                }
            )
    return samples


def _duplicate_names(samples: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    duplicates: list[dict[str, str]] = []
    reported: set[tuple[str, str]] = set()
    for sample in samples:
        key = (str(sample.get("advertiser_id") or ""), str(sample.get("project_name") or ""))
        if key in seen and key not in reported:
            duplicates.append({"advertiser_id": key[0], "project_name": key[1]})
            reported.add(key)
        seen.add(key)
    return duplicates


def _old_project_reference() -> dict[str, str]:
    return {
        "source": "old_project_memory_and_readme",
        "project_rule": "月日_归属_游戏名_项目模板名_批次码_批内项目序号",
        "example": "0424_郭靖_勇者突进_微小每付男_B163125F3_01",
        "reason_to_review": "old project used a batch code to reduce duplicate names before remote lookup",
    }


def _missing_old_reference_components(template: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if "{owner" not in template and "{belonging" not in template and "{name_owner" not in template:
        rows.append(
            {
                "item": "owner_or_belonging",
                "reason": "current template does not include an owner or belonging field from the old rule",
            }
        )
    if "{batch_code" not in template:
        rows.append(
            {
                "item": "batch_code",
                "reason": "current template does not include a batch code from the old rule",
            }
        )
    return rows


def _phase2_contract() -> dict[str, Any]:
    return {
        "review_only": True,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "next_required_reviews": [
            "project_naming_rules",
            "live_payload_generation",
        ],
    }


def _summary(
    *,
    request: dict[str, Any],
    contract: dict[str, Any],
    samples: list[dict[str, Any]],
    duplicates: list[dict[str, str]],
    missing_old_items: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "request_id": str(request.get("request_id") or ""),
        "template": str(contract.get("template") or ""),
        "sample_name_count": len(samples),
        "duplicate_name_count": len(duplicates),
        "invalid_name_count": sum(1 for sample in samples if not bool(sample.get("valid", False))),
        "missing_old_reference_component_count": len(missing_old_items),
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }


def build_create_phase2_project_naming_prep(
    *,
    create_request: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    request = _create_request(create_request)
    contract = _contract(request, policy)
    batch_contract = _batch_code_contract(request)
    samples = _sample_names(request, contract, batch_contract)
    duplicates = _duplicate_names(samples)
    invalid_samples = [sample for sample in samples if not bool(sample.get("valid", False))]
    missing_old_items = _missing_old_reference_components(str(contract.get("template") or ""))
    violations = []
    if duplicates:
        violations.append("project naming samples contain duplicate names")
    if invalid_samples:
        violations.append("project naming samples contain invalid names")
    return {
        "ok": not violations,
        "workflow": "create_phase2_project_naming_prep",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "blocked" if violations else "needs_review",
        "summary": _summary(
            request=request,
            contract=contract,
            samples=samples,
            duplicates=duplicates,
            missing_old_items=missing_old_items,
        ),
        "phase2_preparation_contract": _phase2_contract(),
        "naming_rule_contract": contract,
        "batch_code_contract": batch_contract,
        "sample_names": samples,
        "duplicate_names": duplicates,
        "invalid_names": invalid_samples,
        "old_project_reference": _old_project_reference(),
        "unresolved_naming_items": missing_old_items,
        "violations": violations,
        "actions": [],
    }


def run_create_phase2_project_naming_prep_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _prep_config(request)
    create_request = cfg.get("create_request") if isinstance(cfg.get("create_request"), dict) else {}
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_phase2_project_naming_prep(create_request=create_request, policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_phase2_project_naming_prep", payload)
    return {**payload, "artifact_path": str(artifact_path)}
