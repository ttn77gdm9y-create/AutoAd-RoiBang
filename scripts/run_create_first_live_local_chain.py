#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from roibang_v2.config import load_json, load_runtime_config
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.runs import write_run_artifact
from roibang_v2.workflows.create_first_live_local_chain import run_create_first_live_local_chain_request
from roibang_v2.workflows.create_first_live_local_chain import create_plan_to_preview_config
from roibang_v2.workflows.create_plan_contract import validate_create_plan


PLACEHOLDER_IDS = {
    "source-advertiser-id",
    "target-advertiser-id",
    "target-advertiser-id-2",
}

DEFAULT_PREVIEW_CONFIG = "configs/create/yzt-wx-mini-game.preview.local.json"


def _is_example_config(path: str) -> bool:
    name = Path(path).name
    return name.endswith(".example.json") or ".example." in name


def _iter_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for row in value.values():
            yield from _iter_strings(row)
    elif isinstance(value, list):
        for row in value:
            yield from _iter_strings(row)


def _placeholder_values(preview_config: dict) -> list[str]:
    rows: list[str] = []
    for value in _iter_strings(preview_config):
        normalized = value.strip().lower()
        if normalized in PLACEHOLDER_IDS or normalized.startswith("target-advertiser-id"):
            rows.append(value)
    return sorted(set(rows))


def _preview_config_violations(*, preview_config_path: str, preview_config: dict) -> list[str]:
    violations: list[str] = []
    if _is_example_config(preview_config_path):
        violations.append(
            "首单本地链路不能使用示例配置 .example.json；请使用本地真实配置，例如 configs/create/yzt-wx-mini-game.preview.local.json。"
        )
    placeholders = _placeholder_values(preview_config)
    if placeholders:
        violations.append(f"首单本地链路配置里仍有占位 ID：{', '.join(placeholders)}；请先换成真实源素材账户和目标账户。")
    return violations


def _blocked_preview_config_result(*, config, violations: list[str]) -> dict:
    payload = {
        "ok": False,
        "workflow": "create_first_live_local_chain",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": "blocked",
        "summary": {
            "selected_account_count": 0,
            "project_count": 0,
            "unit_count": 0,
            "material_count": 0,
            "ready_for_approval_chain": False,
            "ready_for_live_execute": False,
        },
        "scope_guard": {
            "ok": False,
            "project_count": 0,
            "unit_count": 0,
            "material_count": 0,
            "max_project_count": 0,
            "max_unit_count": 0,
            "max_material_count": 0,
            "violations": violations,
        },
        "first_live_scope": {
            "max_project_count": 0,
            "max_unit_count": 0,
            "max_material_count": 0,
            "derived_preview_config": {},
        },
        "chain_steps": [],
        "artifacts": {"dry_chain": ""},
        "preparation_check": {},
        "dry_chain": {},
        "create_plan_validation": {},
        "approved_for_execute": False,
        "human_next_steps": violations,
        "violations": violations,
        "actions": [],
    }
    artifact_path = write_run_artifact(config.runs_dir, "create_first_live_local_chain", payload)
    return {**payload, "artifact_path": str(artifact_path)}


def _print_result(result: dict) -> None:
    print(
        json.dumps(
            {
                "ok": result["ok"],
                "workflow": result["workflow"],
                "phase": result["phase"],
                "execution_enabled": result["execution_enabled"],
                "external_api_calls": result["external_api_calls"],
                "status": result["status"],
                "summary": result["summary"],
                "scope_guard": result["scope_guard"],
                "chain_steps": result["chain_steps"],
                "artifacts": result["artifacts"],
                "approved_for_execute": result["approved_for_execute"],
                "human_next_steps": result["human_next_steps"],
                "artifact_path": result["artifact_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_from_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run first-live local-only create chain.")
    parser.add_argument("--config", default="configs/runtime.example.json")
    parser.add_argument("--plan", default="")
    parser.add_argument("--preview-config", default=DEFAULT_PREVIEW_CONFIG)
    parser.add_argument("--policy", default="policies/strategy.example.json")
    args = parser.parse_args(argv)

    config = load_runtime_config(args.config)
    if config.external_api_enabled or config.execution_enabled:
        raise RuntimeError("首单本地链路要求 external_api_enabled=false 且 execution_enabled=false")

    bootstrap_database(config.database_path)
    policy = load_json(args.policy)
    create_plan = None
    preview_config_path = args.preview_config
    if str(args.plan or "").strip():
        try:
            create_plan = load_json(args.plan)
        except FileNotFoundError:
            result = _blocked_preview_config_result(
                config=config,
                violations=[f"缺少创建计划文件：{args.plan}；请先生成或填写 create_plan local JSON。"],
            )
            _print_result(result)
            return 1
        validation = validate_create_plan(create_plan, policy=policy, db_path=config.database_path)
        violations = []
        if _is_example_config(args.plan):
            violations.append("首单本地链路不能使用示例 create_plan .example.json；请使用 configs/create-plans/*.local.json。")
        violations.extend(str(item) for item in validation.get("violations") or [])
        if violations:
            result = _blocked_preview_config_result(config=config, violations=violations)
            result["create_plan_validation"] = validation
            result["first_live_scope"]["derived_preview_config"] = create_plan_to_preview_config(create_plan)
            _print_result(result)
            return 1
        preview_config = create_plan_to_preview_config(create_plan)
        preview_config_path = args.plan
    else:
        try:
            preview_config = load_json(args.preview_config).get("yzt_create_preview") or {}
        except FileNotFoundError:
            result = _blocked_preview_config_result(
                config=config,
                violations=[
                    f"缺少首单本地真实配置：{args.preview_config}；请先创建本地配置，不能使用 .example.json 示例配置。"
                ],
            )
            _print_result(result)
            return 1
        violations = _preview_config_violations(preview_config_path=args.preview_config, preview_config=preview_config)
        if violations:
            result = _blocked_preview_config_result(config=config, violations=violations)
            _print_result(result)
            return 1

    result = run_create_first_live_local_chain_request(
        {
            "create_first_live_local_chain": {
                "preview_config": preview_config,
                "create_plan": create_plan if isinstance(create_plan, dict) else None,
                "preview_config_path": preview_config_path,
                "policy": policy,
            }
        },
        db_path=config.database_path,
        runs_dir=config.runs_dir,
    )
    _print_result(result)
    return 0 if result["ok"] else 1


def main() -> int:
    return run_from_args()


if __name__ == "__main__":
    raise SystemExit(main())
