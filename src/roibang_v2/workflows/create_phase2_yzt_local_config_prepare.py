from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


DEFAULT_EXAMPLE_CONFIG = Path("configs/create/yzt-wx-mini-game.preview.example.json")
DEFAULT_LOCAL_CONFIG = Path("configs/create/yzt-wx-mini-game.preview.local.json")


def _command(script: str, *, local_path: str) -> str:
    return (
        f"PYTHONPATH=src python3 scripts/{script} "
        "--config configs/runtime.example.json "
        f"--preview-config {local_path} "
        "--policy policies/strategy.example.json"
    )


def _editable_fields() -> list[dict[str, str]]:
    return [
        {"field": "template_name", "english_meaning": "template name，模板名", "meaning": "选择项目模板，比如微小每付7R男。"},
        {"field": "owner", "english_meaning": "owner，归属人", "meaning": "项目名里的归属。"},
        {"field": "target_date", "english_meaning": "target date，目标日期", "meaning": "投放日期，用来生成项目名前缀。"},
        {"field": "batch_generated_at", "english_meaning": "batch generated at，批次生成时间", "meaning": "用来稳定生成批次码。"},
        {"field": "defaults.daily_budget", "english_meaning": "daily budget，日预算", "meaning": "账户没有单独填写时使用的默认预算。"},
        {"field": "defaults.project_count", "english_meaning": "project count，项目数量", "meaning": "每个账户默认创建几个项目。"},
        {"field": "defaults.units_per_project", "english_meaning": "units per project，每项目单元数", "meaning": "每个项目默认创建几个单元。"},
        {"field": "roi_coefficient", "english_meaning": "ROI coefficient，ROI系数", "meaning": "只有7R模板需要填写。"},
        {"field": "accounts[].advertiser_id", "english_meaning": "advertiser ID，广告账户ID", "meaning": "把占位账户替换成真实目标账户ID。"},
        {"field": "accounts[].project_count", "english_meaning": "project count，项目数量", "meaning": "单个账户覆盖项目数量，可不填。"},
        {"field": "accounts[].daily_budget", "english_meaning": "daily budget，日预算", "meaning": "单个账户覆盖预算，可不填。"},
    ]


def _operator_guide(*, local_path: str, created: bool) -> dict[str, Any]:
    return {
        "title": "勇者突进本地私有配置填写指南",
        "status": "created" if created else "already_exists",
        "editable_fields": _editable_fields(),
        "ordered_steps": [
            f"打开并编辑 {local_path}。",
            "把 target-advertiser-id 这种占位账户换成真实账户ID。",
            "确认模板、归属、日期、预算、项目数、单元数和ROI系数。",
            "保存后先运行一键准备检查。",
            "准备检查通过后，再运行预览和完整本地预演。",
        ],
        "next_commands": [
            _command("run_create_phase2_yzt_preparation_check.py", local_path=local_path),
            _command("run_create_phase2_yzt_create_preview.py", local_path=local_path),
            _command("run_create_phase2_yzt_dry_chain.py", local_path=local_path),
        ],
    }


def prepare_yzt_local_preview_config(
    *,
    example_path: str | Path = DEFAULT_EXAMPLE_CONFIG,
    local_path: str | Path = DEFAULT_LOCAL_CONFIG,
) -> dict[str, Any]:
    example = Path(example_path)
    local = Path(local_path)
    created = False
    violations: list[str] = []

    if not example.exists():
        violations.append(f"示例配置不存在：{example}")
    elif not local.exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example, local)
        created = True

    ok = not violations
    status = "created" if created else "already_exists"
    if not ok:
        status = "missing_example"

    return {
        "ok": ok,
        "workflow": "create_phase2_yzt_local_config_prepare",
        "phase": "phase2_preparation",
        "execution_enabled": False,
        "external_api_calls": 0,
        "status": status,
        "summary": {
            "example_config": str(example),
            "local_config": str(local),
            "local_config_exists": local.exists(),
            "created": created,
        },
        "safety_notes": [
            "configs/create/*.local.json 已被 git 忽略；local 的意思是本地私有，不要提交真实账户。",
            "example 的意思是示例；example 配置只放占位账户，保持可提交。",
            "这个脚本只复制本地文件，不调用外部接口，不创建项目。",
            "create_execute 继续 hard-block；hard-block 的意思是硬阻断，真实创建执行仍然关闭。",
        ],
        "operator_guide": _operator_guide(local_path=str(local), created=created),
        "violations": violations,
        "human_next_steps": (
            ["打开本地私有配置并填写真实账户，然后运行一键准备检查。"]
            if created
            else ["本地私有配置已存在；直接编辑它，不会自动覆盖。"]
        )
        if ok
        else ["先确认示例配置路径是否正确。"],
        "actions": [],
    }
