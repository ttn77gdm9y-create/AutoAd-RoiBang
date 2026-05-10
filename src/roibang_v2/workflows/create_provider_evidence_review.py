from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_provider_field_map import (
    load_provider_field_map,
    provider_field_map_contract,
    provider_field_map_digest,
)


def _review_config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("create_provider_evidence_review")
    return dict(value) if isinstance(value, dict) else dict(request)


def _field_map_path(policy: dict[str, Any]) -> str:
    return str(policy.get("provider_field_map_path") or "").strip()


def _evidence_catalog_path(policy: dict[str, Any]) -> str:
    return str(policy.get("provider_evidence_catalog_path") or "").strip()


def _invalid_catalog(provider: str = "oceanengine") -> dict[str, Any]:
    return {
        "provider": provider,
        "evidence_catalog_version": "",
        "source": "phase2_placeholder_invalid_provider_evidence_catalog",
        "evidence": {},
    }


def _load_provider_evidence_catalog(policy: dict[str, Any], *, provider: str) -> dict[str, Any]:
    path = _evidence_catalog_path(policy)
    if not path:
        return _invalid_catalog(provider)
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _invalid_catalog(provider)
    if not _is_valid_catalog(payload):
        return _invalid_catalog(provider)
    return payload


def _is_valid_catalog(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not str(value.get("provider") or "").strip():
        return False
    if not str(value.get("evidence_catalog_version") or "").strip():
        return False
    evidence = value.get("evidence")
    if not isinstance(evidence, dict):
        return False
    for item in evidence.values():
        if not isinstance(item, dict):
            return False
        if not str(item.get("operation") or "").strip():
            return False
        if not isinstance(item.get("provider_fields"), list):
            return False
        if "reviewed" not in item:
            return False
    return True


def _catalog_evidence(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = catalog.get("evidence") if isinstance(catalog.get("evidence"), dict) else {}
    return {str(key): value for key, value in evidence.items() if isinstance(value, dict)}


def _is_local_only(entry: dict[str, Any]) -> bool:
    mapping_kind = str(entry.get("mapping_kind") or "").strip()
    return mapping_kind in {"local_lookup_key", "local_only"}


def _evidence_refs(entry: dict[str, Any]) -> list[str]:
    refs = entry.get("evidence_refs")
    if not isinstance(refs, list):
        return []
    return [str(item).strip() for item in refs if str(item or "").strip()]


def _status_and_issues(
    *,
    operation: str,
    entry: dict[str, Any],
    evidence_by_ref: dict[str, dict[str, Any]],
) -> tuple[str, list[str]]:
    provider_field = str(entry.get("provider_field") or "").strip()
    if _is_local_only(entry) and not provider_field:
        if bool(entry.get("local_only_confirmed", False)):
            return "local_only_confirmed", []
        return "local_only_needs_confirmation", ["local-only field requires explicit confirmation"]
    if not provider_field:
        return "needs_provider_field", ["provider field is empty"]
    refs = _evidence_refs(entry)
    if not refs:
        return "needs_evidence_ref", ["provider field requires at least one evidence ref"]
    missing_refs = [ref for ref in refs if ref not in evidence_by_ref]
    if missing_refs:
        return "missing_evidence", [f"evidence {ref} is missing from catalog" for ref in missing_refs]
    unreviewed = [ref for ref in refs if not bool(evidence_by_ref[ref].get("reviewed", False))]
    if unreviewed:
        return "needs_evidence_review", [f"evidence {ref} is not reviewed" for ref in unreviewed]
    operation_mismatches = [
        ref
        for ref in refs
        if str(evidence_by_ref[ref].get("operation") or "").strip() != operation
    ]
    if operation_mismatches:
        return "evidence_operation_mismatch", [
            f"evidence {ref} operation does not match {operation}" for ref in operation_mismatches
        ]
    field_missing = [
        ref
        for ref in refs
        if provider_field
        not in {str(item).strip() for item in evidence_by_ref[ref].get("provider_fields") or []}
    ]
    if field_missing:
        return "field_not_in_evidence", [
            f"provider field {provider_field} is not listed in evidence {ref}" for ref in field_missing
        ]
    if not bool(entry.get("verified", False)):
        return "needs_mapping_verification", ["field mapping is not marked verified"]
    return "verified", []


def _field_row(
    *,
    operation: str,
    entry: dict[str, Any],
    evidence_by_ref: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status, issues = _status_and_issues(
        operation=operation,
        entry=entry,
        evidence_by_ref=evidence_by_ref,
    )
    return {
        "internal_field": str(entry.get("internal_field") or ""),
        "provider_field": str(entry.get("provider_field") or ""),
        "mapping_kind": str(entry.get("mapping_kind") or ""),
        "evidence_refs": _evidence_refs(entry),
        "evidence_status": status,
        "evidence_issues": issues,
    }


def _review_sections(
    *,
    field_map: dict[str, Any],
    evidence_by_ref: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    operations = field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}
    sections: list[dict[str, Any]] = []
    for operation, rows in operations.items():
        fields = [
            _field_row(operation=str(operation), entry=entry, evidence_by_ref=evidence_by_ref)
            for entry in rows
            if isinstance(entry, dict)
        ] if isinstance(rows, list) else []
        sections.append({"operation": str(operation), "fields": fields})
    return sections


def _fields(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        field
        for section in sections
        for field in (section.get("fields") if isinstance(section.get("fields"), list) else [])
        if isinstance(field, dict)
    ]


def _is_resolved_status(status: str) -> bool:
    return status in {"verified", "local_only_confirmed"}


def _unresolved_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in sections:
        operation = str(section.get("operation") or "")
        for field in section.get("fields") if isinstance(section.get("fields"), list) else []:
            if not isinstance(field, dict):
                continue
            if _is_resolved_status(str(field.get("evidence_status") or "")):
                continue
            rows.append(
                {
                    "operation": operation,
                    "internal_field": str(field.get("internal_field") or ""),
                    "provider_field": str(field.get("provider_field") or ""),
                    "evidence_status": str(field.get("evidence_status") or ""),
                    "evidence_issues": list(field.get("evidence_issues") or []),
                }
            )
    return rows


def _summary(
    *,
    policy: dict[str, Any],
    field_map: dict[str, Any],
    catalog: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    fields = _fields(sections)
    evidence_by_ref = _catalog_evidence(catalog)
    status_counts: dict[str, int] = {}
    for field in fields:
        status = str(field.get("evidence_status") or "")
        if not status:
            continue
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "provider": str(field_map.get("provider") or ""),
        "field_mapping_version": str(field_map.get("field_mapping_version") or ""),
        "field_map_path": _field_map_path(policy),
        "evidence_catalog_path": _evidence_catalog_path(policy),
        "field_count": len(fields),
        "catalog_evidence_count": len(evidence_by_ref),
        "reviewed_evidence_count": sum(1 for item in evidence_by_ref.values() if bool(item.get("reviewed", False))),
        "ready_field_count": sum(1 for field in fields if str(field.get("evidence_status") or "") == "verified"),
        "unresolved_field_count": sum(
            1 for field in fields if not _is_resolved_status(str(field.get("evidence_status") or ""))
        ),
        "evidence_status_counts": dict(sorted(status_counts.items())),
        "ready_for_live_payload_development": False,
        "ready_for_live_execute": False,
    }


def _phase2_provider_evidence_contract() -> dict[str, Any]:
    return {
        "review_only": True,
        "external_api_allowed": False,
        "live_payload_generation_enabled": False,
        "create_execute_hard_block_required": True,
        "mapping_verified_must_remain_false": True,
    }


def _operator_guide(*, status: str) -> dict[str, Any]:
    if status == "invalid":
        return {
            "status": "needs_fix",
            "title": "平台字段证据配置不可用",
            "ordered_steps": [
                "先修复 provider field map 或 provider evidence catalog JSON。",
                "确认 JSON 结构正确后重新运行 provider evidence review 脚本。",
            ],
            "blocked_until": [
                "证据目录 JSON 可以正常读取",
                "字段映射 JSON 可以正常读取",
                "create_execute 仍保持 hard-blocked",
            ],
            "next_command": (
                "PYTHONPATH=src python3 scripts/run_create_provider_evidence_review.py "
                "--config configs/runtime.example.json --policy policies/strategy.example.json"
            ),
        }
    return {
        "status": "needs_review",
        "title": "平台字段证据仍需人工复核",
        "ordered_steps": [
            "先补证据目录里的 source_url 或 captured_request_ref。",
            "人工核对后，把对应 evidence.reviewed 改为 true，并填写 reviewed_by 和 reviewed_at。",
            "确认 local-only 字段不会进入平台 payload 后，再在字段映射里标记 local_only_confirmed=true。",
            "证据和字段都确认后，才考虑把具体字段 verified 改为 true。",
            "重新运行 provider evidence review 脚本查看剩余项。",
        ],
        "blocked_until": [
            "所有平台字段都有已复核证据",
            "所有 local-only 字段已明确确认",
            "create_execute 仍保持 hard-blocked",
        ],
        "next_command": (
            "PYTHONPATH=src python3 scripts/run_create_provider_evidence_review.py "
            "--config configs/runtime.example.json --policy policies/strategy.example.json"
        ),
    }


def _fill_required(status: str) -> list[str]:
    if status == "needs_evidence_review":
        return [
            "source_url_or_captured_request_ref",
            "reviewed_by",
            "reviewed_at",
            "set_evidence_reviewed_true_after_manual_check",
            "set_field_verified_true_after_evidence_check",
        ]
    if status == "local_only_needs_confirmation":
        return [
            "confirm_field_is_local_only",
            "set_local_only_confirmed_true_after_manual_check",
        ]
    if status == "needs_provider_field":
        return [
            "provider_field",
            "mapping_kind",
            "evidence_refs",
        ]
    if status == "needs_evidence_ref":
        return [
            "evidence_refs",
            "source_url_or_captured_request_ref",
        ]
    if status == "missing_evidence":
        return [
            "add_missing_evidence_catalog_entry",
            "source_url_or_captured_request_ref",
            "reviewed_by",
            "reviewed_at",
        ]
    if status == "needs_mapping_verification":
        return ["set_field_verified_true_after_evidence_check"]
    return []


def _evidence_worksheet(sections: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for section in sections:
        operation = str(section.get("operation") or "")
        for field in section.get("fields") if isinstance(section.get("fields"), list) else []:
            if not isinstance(field, dict):
                continue
            status = str(field.get("evidence_status") or "")
            rows.append(
                {
                    "operation": operation,
                    "internal_field": str(field.get("internal_field") or ""),
                    "provider_field": str(field.get("provider_field") or ""),
                    "mapping_kind": str(field.get("mapping_kind") or ""),
                    "evidence_status": status,
                    "evidence_refs": list(field.get("evidence_refs") or []),
                    "fill_required": _fill_required(status),
                    "do_not_change": [
                        "execution_enabled",
                        "external_api_calls",
                        "actions",
                    ],
                }
            )
    summary = {
        "worksheet_version": "phase2.provider_evidence_worksheet.v1",
        "row_count": len(rows),
        "requires_evidence_review_count": sum(
            1 for row in rows if str(row.get("evidence_status") or "") == "needs_evidence_review"
        ),
        "requires_local_confirmation_count": sum(
            1 for row in rows if str(row.get("evidence_status") or "") == "local_only_needs_confirmation"
        ),
        "requires_provider_field_count": sum(
            1 for row in rows if str(row.get("evidence_status") or "") == "needs_provider_field"
        ),
        "ready_row_count": sum(1 for row in rows if _is_resolved_status(str(row.get("evidence_status") or ""))),
    }
    return {
        "summary": summary,
        "instructions": [
            "逐行补齐 fill_required 里列出的字段或确认项。",
            "不要修改 do_not_change 里的安全字段。",
            "补完后重新运行 create_provider_evidence_review。",
        ],
        "rows": rows,
    }


def _provider_field_gap_report(field_map: dict[str, Any]) -> dict[str, Any]:
    operations = field_map.get("operations") if isinstance(field_map.get("operations"), dict) else {}
    rows: list[dict[str, Any]] = []
    for operation, entries in operations.items():
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("provider_field") or "").strip():
                continue
            if _is_local_only(entry):
                continue
            open_questions = entry.get("open_questions")
            rows.append(
                {
                    "operation": str(operation),
                    "internal_field": str(entry.get("internal_field") or ""),
                    "provider_object": str(entry.get("provider_object") or ""),
                    "value_source": str(entry.get("value_source") or ""),
                    "purpose": str(entry.get("purpose") or ""),
                    "open_questions": [
                        str(item) for item in open_questions if str(item or "").strip()
                    ] if isinstance(open_questions, list) else [],
                    "fill_required": [
                        "provider_field",
                        "mapping_kind",
                        "evidence_refs",
                    ],
                }
            )
    operation_counts: dict[str, int] = {}
    for row in rows:
        operation = str(row.get("operation") or "")
        operation_counts[operation] = operation_counts.get(operation, 0) + 1
    return {
        "summary": {
            "gap_count": len(rows),
            "operation_counts": dict(sorted(operation_counts.items())),
            "ready_for_live_payload_development": False,
        },
        "instructions": [
            "先确认每个 internal_field 是否应拆成多个 provider_field。",
            "不要为了消除 gap 编造 provider_field。",
            "补 provider_field 前必须同步补 evidence_refs。",
        ],
        "rows": rows,
    }


def _gap_resolution_details(row: dict[str, Any]) -> dict[str, Any]:
    operation = str(row.get("operation") or "")
    internal_field = str(row.get("internal_field") or "")
    if operation == "create_project" and internal_field == "project_type":
        return {
            "recommended_action": "confirm_local_template_selector_or_split_to_provider_fields",
            "review_questions": [
                "这个 project_type 是否只用于本地模板选择、项目命名和策略分支？",
                "它是否已经被拆到 landing_type、pricing、inventory_type 等平台字段？",
                "是否有官方文档或已捕获请求证明平台请求体不接收 project_type？",
                "复核证据来自官方文档还是已捕获请求？",
            ],
            "blocked_until": [
                "本地用途已复核",
                "mapping_kind 已确认",
                "如果确认本地字段，local_only_confirmed 必须由人工确认",
                "如果需要进入平台请求体，必须拆成明确 provider_field 并补证据",
            ],
        }
    if internal_field == "field_defaults" or internal_field.startswith("field_defaults."):
        return {
            "recommended_action": "map_field_default_subfield_to_provider_field",
            "review_questions": [
                "这个 field_defaults 子字段对应哪个平台字段？",
                "这个子字段是否只用于本地模板，不应该进入平台请求体？",
                "该 provider_field 是否有官方文档或已捕获请求证据？",
                "复核证据来自官方文档还是已捕获请求？",
            ],
            "blocked_until": [
                "子字段去向已确认",
                "要进入平台请求体时 provider_field 已确认",
                "provider_field 有已复核 evidence_refs",
            ],
        }
    if operation == "bind_material" and internal_field == "source_video_id":
        return {
            "recommended_action": "confirm_material_identifier_or_local_provenance",
            "review_questions": [
                "平台素材绑定请求是否直接接收 source_video_id？",
                "source_video_id 是否只用于本地追溯素材来源？",
                "素材绑定应使用 material_id、source_video_id，还是嵌套素材列表？",
                "复核证据来自官方文档还是已捕获请求？",
            ],
            "blocked_until": [
                "素材绑定平台字段已确认",
                "如果 source_video_id 只用于本地追溯，必须人工确认 local_only",
                "如果 source_video_id 进入平台请求体，必须补 provider_field 和 evidence_refs",
            ],
        }
    return {
        "recommended_action": "decide_split_or_provider_field",
        "review_questions": [
            "这个本地字段是否应该进入平台请求体？",
            "如果进入平台请求体，它是单个字段还是需要拆成多个平台字段？",
            "复核证据来自官方文档还是已捕获请求？",
        ],
        "blocked_until": [
            "provider_field 已确认",
            "mapping_kind 已确认",
            "evidence_refs 已补充并复核",
        ],
    }


def _provider_field_gap_resolution_plan(gap_report: dict[str, Any]) -> dict[str, Any]:
    gap_rows = gap_report.get("rows") if isinstance(gap_report.get("rows"), list) else []
    items: list[dict[str, Any]] = []
    for row in gap_rows:
        if not isinstance(row, dict):
            continue
        details = _gap_resolution_details(row)
        items.append(
            {
                "operation": str(row.get("operation") or ""),
                "internal_field": str(row.get("internal_field") or ""),
                "recommended_action": details["recommended_action"],
                "review_questions": details["review_questions"],
                "blocked_until": details["blocked_until"],
                "do_not_do": [
                    "不要猜 provider_field",
                    "不要把 field_defaults 整包塞进平台请求体",
                    "不要打开 create_execute",
                ],
            }
        )
    return {
        "summary": {
            "plan_version": "phase2.provider_field_gap_resolution.v1",
            "gap_count": len(items),
            "manual_review_required": bool(items),
            "ready_for_live_payload_development": False,
        },
        "instructions": [
            "逐项复核缺口，不要直接填写猜测值。",
            "每项确认后先更新字段映射和证据目录，再重新运行证据复核。",
            "这个计划不是批准产物，不能开启真实执行。",
        ],
        "items": items,
    }


def _project_type_local_usage_review() -> dict[str, Any]:
    local_usage_evidence = [
        {
            "usage_kind": "template_selector",
            "source": "create_phase2_yzt_create_preview._project_type",
            "meaning": "从项目模板名称推导本地 project_type，用于区分 WX_PAY 和 WX_PAY_7R。",
        },
        {
            "usage_kind": "request_validation",
            "source": "create_request._validate_request",
            "meaning": "作为创建请求的必填输入，用来固定本地策略入口。",
        },
        {
            "usage_kind": "project_naming",
            "source": "create_strategy_plan._project_name_entry",
            "meaning": "作为项目命名模板变量参与生成 project_name。",
        },
        {
            "usage_kind": "batch_code_source",
            "source": "create_strategy_plan._batch_code_source",
            "meaning": "作为批次码来源字段，帮助同一批创建保持幂等和可追踪。",
        },
        {
            "usage_kind": "project_naming_prep",
            "source": "create_phase2_project_naming_prep._sample_names",
            "meaning": "在项目命名预检查里作为模板变量生成样例名称。",
        },
        {
            "usage_kind": "dry_run_traceability",
            "source": "create_strategy_plan._build_projects",
            "meaning": "随 dry-run 计划保留，用于本地复盘项目来自哪个模板类型。",
        },
    ]
    blocking_items: list[dict[str, str]] = []
    return {
        "summary": {
            "review_version": "phase2.project_type_local_usage_review.v1",
            "internal_field": "project_type",
            "local_usage_evidence_count": len(local_usage_evidence),
            "blocking_item_count": len(blocking_items),
            "manual_confirmation_required": True,
            "ready_to_mark_local_only": True,
        },
        "local_usage_evidence": local_usage_evidence,
        "blocking_items": blocking_items,
        "operator_decision": {
            "recommended_next_action": "先处理 blocking_items，再决定是否人工确认 local_only。",
            "do_not_auto_confirm": True,
            "do_not_open_create_execute": True,
        },
    }


def _field_gap_convergence_plan(gap_report: dict[str, Any]) -> dict[str, Any]:
    gap_rows = gap_report.get("rows") if isinstance(gap_report.get("rows"), list) else []
    field_defaults_items = [
        {
            "operation": str(row.get("operation") or ""),
            "internal_field": str(row.get("internal_field") or ""),
            "subfield": str(row.get("internal_field") or "").split(".")[-1],
            "recommended_action": "map_to_explicit_provider_field",
            "blocked_until": ["子字段有 provider_field", "provider_field 有已复核证据"],
        }
        for row in gap_rows
        if isinstance(row, dict) and str(row.get("internal_field") or "").startswith("field_defaults.")
    ]
    source_video_id_review = {
        "operation": "bind_material",
        "internal_field": "source_video_id",
        "recommended_mapping_kind": "local_only",
        "local_only_confirmed": False,
        "reason": "保留在本地材料对象中用于源视频追溯，已从禁用请求体 schema 和 dry-run payload 移除。",
        "blocked_until": ["人工确认 local_only_confirmed=true"],
    }
    return {
        "summary": {
            "plan_version": "phase2.field_gap_convergence.v1",
            "project_type_ready_for_manual_local_only_confirmation": True,
            "remaining_provider_field_gap_count": int(gap_report.get("summary", {}).get("gap_count") or 0),
            "field_defaults_split_item_count": len(field_defaults_items),
            "source_video_id_review_required": any(
                isinstance(row, dict)
                and str(row.get("operation") or "") == "bind_material"
                and str(row.get("internal_field") or "") == "source_video_id"
                for row in gap_rows
            ),
            "ready_for_live_payload_development": False,
        },
        "project_type_decision": {
            "operation": "create_project",
            "internal_field": "project_type",
            "recommended_mapping_kind": "local_only",
            "local_only_confirmed": False,
            "reason": "已从禁用请求体 schema 和 dry-run payload 移除，只保留本地模板、命名、批次码和复盘用途。",
            "blocked_until": ["人工确认 local_only_confirmed=true"],
        },
        "field_defaults_split_plan": {
            "items": field_defaults_items,
        },
        "source_video_id_review": source_video_id_review,
        "do_not_do": [
            "不要猜 provider_field",
            "不要把 field_defaults 整包塞进平台请求体",
            "不要打开 create_execute",
        ],
    }


def build_create_provider_evidence_review(*, policy: dict[str, Any]) -> dict[str, Any]:
    field_map = load_provider_field_map(policy)
    field_contract = provider_field_map_contract(field_map, policy)
    field_digest = provider_field_map_digest(field_map)
    catalog = _load_provider_evidence_catalog(policy, provider=str(field_map.get("provider") or "oceanengine"))
    evidence_by_ref = _catalog_evidence(catalog)
    sections = _review_sections(field_map=field_map, evidence_by_ref=evidence_by_ref)
    invalid_field_map = str(field_map.get("source") or "") == "phase1_placeholder_invalid_provider_field_map_config"
    invalid_catalog = str(catalog.get("source") or "") == "phase2_placeholder_invalid_provider_evidence_catalog"
    violations: list[str] = []
    if invalid_field_map:
        violations.append("provider field map config is missing or malformed")
    if invalid_catalog:
        violations.append("provider evidence catalog config is missing or malformed")
    status = "invalid" if violations else "needs_review"
    gap_report = _provider_field_gap_report(field_map)
    return {
        "ok": not violations,
        "workflow": "create_provider_evidence_review",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": _summary(policy=policy, field_map=field_map, catalog=catalog, sections=sections),
        "phase2_provider_evidence_contract": _phase2_provider_evidence_contract(),
        "provider_field_map": field_map,
        "provider_field_map_contract": field_contract,
        "provider_field_map_digest": field_digest,
        "provider_evidence_catalog": catalog,
        "evidence_review_sections": sections,
        "unresolved_evidence_items": _unresolved_items(sections),
        "evidence_worksheet": _evidence_worksheet(sections),
        "provider_field_gap_report": gap_report,
        "provider_field_gap_resolution_plan": _provider_field_gap_resolution_plan(gap_report),
        "project_type_local_usage_review": _project_type_local_usage_review(),
        "field_gap_convergence_plan": _field_gap_convergence_plan(gap_report),
        "operator_guide": _operator_guide(status=status),
        "violations": violations,
        "actions": [],
    }


def run_create_provider_evidence_review_request(
    request: dict[str, Any],
    *,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _review_config(request)
    policy = cfg.get("policy") if isinstance(cfg.get("policy"), dict) else {}
    payload = build_create_provider_evidence_review(policy=policy)
    artifact_path = write_run_artifact(runs_dir, "create_provider_evidence_review", payload)
    return {**payload, "artifact_path": str(artifact_path)}
