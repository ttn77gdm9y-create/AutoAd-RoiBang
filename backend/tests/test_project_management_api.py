import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_product_accounts(root: Path, *, status_1002: str = "disabled") -> None:
    _write_json(
        root / "configs" / "accounts" / "product-accounts.local.json",
        {
            "accounts": [
                {
                    "product_key": "demo-game",
                    "product_name": "演示游戏",
                    "advertiser_id": "1001",
                    "advertiser_name": "演示账户一",
                    "channel": "微信",
                    "owner": "郭靖",
                    "account_remark": "",
                    "status": "active",
                    "notes": "",
                },
                {
                    "product_key": "demo-game",
                    "product_name": "演示游戏",
                    "advertiser_id": "1002",
                    "advertiser_name": "演示账户二",
                    "channel": "微信",
                    "owner": "郭靖",
                    "account_remark": "",
                    "status": status_1002,
                    "notes": "本地停用",
                },
            ]
        },
    )


def _project_management_request() -> dict:
    return {
        "project_update_id": "delete-p2",
        "advertiser_ids": "1001\n1002",
        "action_type": "delete_project",
        "name_contains": "7R",
        "spend_window": "last_3_days",
        "metric_field": "stat_cost",
        "metric_op": "lte",
        "metric_value": "100",
        "metric_filters": [
            {"field": "stat_cost", "op": "lte", "value": "100"},
        ],
        "output_path": "configs/project-updates/delete-p2.local.json",
    }


def _write_project_update(root: Path) -> str:
    path = root / "configs" / "project-updates" / "delete-p2.local.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "project_update_id": "delete-p2",
                "operator": "郭靖",
                "allowed_target_accounts_path": "configs/control-allowed-accounts.local.json",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "1001",
                        "entity_type": "project",
                        "project_id": "p-1",
                        "project_name": "7R-测试-1",
                    },
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "1002",
                        "entity_type": "project",
                        "project_id": "p-2",
                        "project_name": "7R-测试-2",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return "configs/project-updates/delete-p2.local.json"


def _write_suggestion_project_update(root: Path, *, patch: dict | None = None) -> str:
    path = root / "configs" / "project-updates" / "suggestions-demo.local.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "中文摘要": "根据规则建议生成项目管理动作 JSON，涉及 1 个账户、2 个动作；只生成配置，不执行真实业务动作。",
        "project_update_id": "suggestions-demo",
        "operator": "运营A",
        "product_key": "demo-game",
        "product_name": "演示游戏",
        "source_artifact": "data/runs/delivery_patrol_suggestions/20260528T100001Z.json",
        "generated_at": "2026-05-29T10:00:00+00:00",
        "accounts": [{"account_id": "1001", "account_name": "演示账户一"}],
        "risk_summary": "包含删除项目 1 个、暂停项目 1 个；执行前必须人工核对账户、项目、动作和来源建议。",
        "dry_run_required": True,
        "execution_allowed": False,
        "source": {"workflow": "delivery_patrol_suggestions", "artifact_path": "data/runs/delivery_patrol_suggestions/20260528T100001Z.json"},
        "execution": {"enabled": False, "status": "planned_only"},
        "actions": [
            {
                "action_type": "delete_project",
                "中文动作": "删除项目",
                "advertiser_id": "1001",
                "account_name": "演示账户一",
                "entity_type": "project",
                "project_id": "p-delete",
                "project_name": "演示游戏-旧项目",
                "reason": "项目已关闭且两天无计费时间转化，建议删除。",
                "source_suggestion_id": "delete-1",
            },
            {
                "action_type": "status_update",
                "中文动作": "暂停项目",
                "advertiser_id": "1001",
                "account_name": "演示账户一",
                "entity_type": "project",
                "project_id": "p-close",
                "project_name": "演示游戏-关闭候选",
                "reason": "累计消耗达到阈值但计费时间转化为 0，建议暂停项目。",
                "source_suggestion_id": "close-1",
                "opt_status": "DISABLE",
            },
        ],
        "restore_actions": [],
    }
    if patch:
        payload.update(patch)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return "configs/project-updates/suggestions-demo.local.json"


def test_project_management_config_preview_returns_chinese_summary(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json=_project_management_request(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置预览"
    assert payload["summary"]["status"] == "planned"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "动作", "value": "删除项目"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    assert {"label": "输出 JSON", "value": "configs/project-updates/delete-p2.local.json"} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "动作", "项目名包含", "数据窗口", "筛选条件", "目标值", "输出 JSON"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "未配置账户名",
        "动作": "删除项目",
        "项目名包含": "7R",
        "数据窗口": "近 3 天",
        "筛选条件": "消耗 小于等于 100",
        "目标值": "",
        "输出 JSON": "configs/project-updates/delete-p2.local.json",
    }
    assert isinstance(payload["raw"]["command"], list)
    assert payload["raw"]["command"][1] == "scripts/run_project_realtime_filter_config.py"
    assert "--execute" not in payload["raw"]["command"]


def test_project_management_config_preview_blocks_missing_accounts(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={"project_update_id": "bad", "advertiser_ids": "", "action_type": "delete_project"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置预览"
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "必须明确填写本次账户 ID" in payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"] == []


def test_project_management_config_preview_blocks_disabled_product_accounts(tmp_path):
    _write_product_accounts(tmp_path, status_1002="disabled")
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json=_project_management_request(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "账户已在产品账户库停用：演示账户二（1002）" in payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"] == []


def test_project_management_config_preview_blocks_missing_required_choices(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={
            "project_update_id": "",
            "advertiser_ids": "",
            "action_type": "",
            "spend_window": "",
            "metric_filters": [],
            "output_path": "",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == [
        "必须明确选择项目管理动作",
        "必须明确填写本次账户 ID",
    ]


def test_project_management_config_preview_all_projects_without_metric_filters(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={
            "project_update_id": "close-all-projects",
            "advertiser_ids": "1001\n1002",
            "action_type": "status_update",
            "name_contains": "",
            "spend_window": "",
            "metric_filters": [{"field": "", "op": "", "value": ""}],
            "opt_status": "DISABLE",
            "output_path": "configs/project-updates/close-all-projects.local.json",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert {"label": "数据窗口", "value": "未使用"} in payload["summary"]["items"]
    assert {"label": "筛选条件", "value": "账户范围内全部可操作项目"} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["数据窗口"] == "未使用"
    assert payload["table"]["rows"][0]["筛选条件"] == "账户范围内全部可操作项目"
    assert "--spend-window" not in payload["raw"]["command"]
    assert "--metric-filter" not in payload["raw"]["command"]
    assert "--opt-status" in payload["raw"]["command"]
    assert "DISABLE" in payload["raw"]["command"]


def test_project_management_config_preview_requires_window_only_for_metric_filters(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={
            **_project_management_request(),
            "spend_window": "",
            "metric_filters": [{"field": "stat_cost", "op": "gt", "value": "1"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["blocking_reasons"] == ["使用数据筛选时必须明确选择数据窗口"]


def test_project_management_config_preview_auto_fills_internal_id_and_output_path(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={
            **_project_management_request(),
            "project_update_id": "",
            "output_path": "",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert "必须明确填写配置 ID" not in payload["summary"]["blocking_reasons"]
    assert "必须明确填写项目管理 JSON 输出路径" not in payload["summary"]["blocking_reasons"]
    config_id = next(item["value"] for item in payload["summary"]["items"] if item["label"] == "配置 ID")
    output_json = next(item["value"] for item in payload["summary"]["items"] if item["label"] == "输出 JSON")
    assert config_id.startswith("project-update-")
    assert output_json == f"configs/project-updates/{config_id}.local.json"


def test_project_management_config_preview_supports_and_metric_filters(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={
            **_project_management_request(),
            "metric_field": "",
            "metric_op": "",
            "metric_value": "",
            "metric_filters": [
                {"field": "stat_cost", "op": "lte", "value": "500"},
                {"field": "billing_convert_cnt", "op": "eq", "value": "0"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "planned"
    assert {"label": "筛选条件", "value": "消耗 小于等于 500 且 计费时间转化数 等于 0"} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["筛选条件"] == "消耗 小于等于 500 且 计费时间转化数 等于 0"
    assert payload["raw"]["command"].count("--metric-filter") == 2
    assert "stat_cost:lte:500" in payload["raw"]["command"]
    assert "billing_convert_cnt:eq:0" in payload["raw"]["command"]


def test_project_management_config_preview_blocks_missing_action_target_value(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/preview",
        json={
            **_project_management_request(),
            "action_type": "budget_update",
            "budget": "",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == ["调整预算必须明确填写目标预算"]


def test_project_management_config_generate_starts_frontend_task(tmp_path, monkeypatch):
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.project_management.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post("/api/project-management/config/generate", json=_project_management_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理配置生成任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is False
    assert {"label": "动作", "value": "删除项目"} in payload["summary"]["items"]
    assert {"label": "账户数", "value": 2} in payload["summary"]["items"]
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "project_management_config_generate"
    assert task["command"][1] == "scripts/run_project_realtime_filter_config.py"
    assert "--execute" not in task["command"]
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "project_management_config_generate"

    operation_payload = client.get(
        "/api/operations",
        params={"operation_type": "project_management_config_generate"},
    ).json()
    operation_rows = operation_payload["table"]["rows"]
    assert len(operation_rows) == 1
    assert operation_rows[0]["关联任务"] == task["task_id"]
    assert operation_rows[0]["操作"] == "项目管理配置生成"
    assert operation_rows[0]["状态"] == "排队中"
    assert operation_rows[0]["账户数"] == 2
    assert operation_payload["raw"]["rows"][0]["result_status"] == "queued"


def test_project_management_config_generate_keeps_blocked_summary_without_task(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/config/generate",
        json={"project_update_id": "bad", "advertiser_ids": "", "action_type": "delete_project"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "task" not in payload
    assert not (tmp_path / "data" / "runs" / "frontend_tasks").exists()


def test_project_management_execute_preview_reads_project_update_summary(tmp_path):
    project_update_path = _write_project_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理执行预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "配置 ID", "value": "delete-p2"} in payload["summary"]["items"]
    assert {"label": "动作数", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["columns"] == ["账户 ID", "账户名", "项目 ID", "项目名", "动作", "目标值"]
    assert payload["table"]["rows"][0] == {
        "账户 ID": "1001",
        "账户名": "未配置账户名",
        "项目 ID": "p-1",
        "项目名": "7R-测试-1",
        "动作": "删除项目",
        "目标值": "",
    }
    assert payload["raw"]["execute_command"][1] == "scripts/run_project_update_execute.py"
    assert "--execute" in payload["raw"]["execute_command"]
    assert "--yes" in payload["raw"]["execute_command"]


def test_project_management_execute_preview_blocks_disabled_product_accounts(tmp_path):
    _write_product_accounts(tmp_path, status_1002="paused")
    project_update_path = _write_project_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "账户已在产品账户库暂停：演示账户二（1002）" in payload["summary"]["blocking_reasons"]
    assert payload["summary"]["execution_enabled"] is False


def test_project_management_execute_preview_accepts_suggestion_json_with_chinese_summary_and_account_names(tmp_path):
    project_update_path = _write_suggestion_project_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path, "config_source": "suggestions_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理执行预览"
    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "配置来源", "value": "投放建议工作台生成的项目管理配置"} in payload["summary"]["items"]
    assert {
        "label": "中文摘要",
        "value": "根据规则建议生成项目管理动作 JSON，涉及 1 个账户、2 个动作；只生成配置，不执行真实业务动作。",
    } in payload["summary"]["items"]
    assert {"label": "产品", "value": "演示游戏（demo-game）"} in payload["summary"]["items"]
    assert {"label": "来源建议", "value": "data/runs/delivery_patrol_suggestions/20260528T100001Z.json"} in payload["summary"]["items"]
    assert {
        "label": "风险摘要",
        "value": "包含删除项目 1 个、暂停项目 1 个；执行前必须人工核对账户、项目、动作和来源建议。",
    } in payload["summary"]["items"]
    assert {"label": "删除项目", "value": 1} in payload["summary"]["items"]
    assert {"label": "暂停项目", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["rows"][1] == {
        "账户 ID": "1001",
        "账户名": "演示账户一",
        "项目 ID": "p-close",
        "项目名": "演示游戏-关闭候选",
        "动作": "暂停项目",
        "目标值": "关闭",
    }
    assert payload["raw"]["execute_command"][1] == "scripts/run_project_update_execute.py"
    assert "--execute" in payload["raw"]["execute_command"]
    assert "--yes" in payload["raw"]["execute_command"]


def test_project_management_execute_preview_blocks_repeated_suggestion_config(tmp_path):
    project_update_path = _write_suggestion_project_update(tmp_path)
    _write_json(
        tmp_path / "data" / "runs" / "project_update_execute" / "20260528T110000Z.json",
        {
            "workflow": "project_update_execute",
            "status": "completed",
            "project_update_path": project_update_path,
            "summary": {
                "project_update_id": "suggestions-demo",
                "action_count": 2,
                "updated_project_count": 2,
                "failed_project_count": 0,
            },
            "results": [
                {
                    "operation": "delete_project",
                    "advertiser_id": "1001",
                    "project_count": 1,
                    "requested_project_count": 1,
                    "failed_project_count": 0,
                    "project_ids": ["p-delete"],
                    "requested_project_ids": ["p-delete"],
                    "error_list": [],
                    "status": "completed",
                },
                {
                    "operation": "update_project_status",
                    "advertiser_id": "1001",
                    "project_count": 1,
                    "requested_project_count": 1,
                    "failed_project_count": 0,
                    "project_ids": ["p-close"],
                    "requested_project_ids": ["p-close"],
                    "error_list": [],
                    "status": "completed",
                },
            ],
        },
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path, "config_source": "suggestions_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "这份投放建议生成的项目管理配置已经执行完成，不能重复确认执行。" in payload["summary"]["blocking_reasons"]


def test_project_management_execute_preview_blocks_suggestion_json_missing_chinese_summary(tmp_path):
    project_update_path = _write_suggestion_project_update(tmp_path, patch={"中文摘要": ""})
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path, "config_source": "suggestions_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["summary"]["blocking_reasons"] == ["建议生成的项目管理 JSON 缺少中文摘要"]


def test_project_management_execute_preview_blocks_suggestion_json_missing_account_name(tmp_path):
    project_update_path = _write_suggestion_project_update(
        tmp_path,
        patch={
            "accounts": [{"account_id": "1001", "account_name": ""}],
            "actions": [
                {
                    "action_type": "delete_project",
                    "advertiser_id": "1001",
                    "entity_type": "project",
                    "project_id": "p-delete",
                    "project_name": "演示游戏-旧项目",
                }
            ],
        },
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path, "config_source": "suggestions_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["blocking_reasons"] == ["建议生成的项目管理 JSON 缺少账户名：1001"]


def test_project_management_execute_preview_blocks_suggestion_json_marked_execution_allowed(tmp_path):
    project_update_path = _write_suggestion_project_update(tmp_path, patch={"execution_allowed": True})
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path, "config_source": "suggestions_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["blocking_reasons"] == ["建议生成的项目管理 JSON 必须保持 execution_allowed=false，由项目管理确认入口控制真实执行"]


def test_project_management_execute_preview_blocks_suggestion_json_with_execution_enabled(tmp_path):
    project_update_path = _write_suggestion_project_update(
        tmp_path,
        patch={"execution": {"enabled": True, "status": "planned_only"}},
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": project_update_path, "config_source": "suggestions_generated"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["blocking_reasons"] == [
        "建议生成的项目管理 JSON 必须保持 execution.enabled=false，由项目管理确认入口控制真实执行"
    ]


def test_project_management_execute_preview_blocks_missing_config(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": "configs/project-updates/missing.local.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "项目管理 JSON 不存在" in payload["summary"]["blocking_reasons"][0]


def test_project_management_execute_preview_blocks_missing_project_id(tmp_path):
    project_update_path = tmp_path / "configs" / "project-updates" / "delete-missing-project.local.json"
    project_update_path.parent.mkdir(parents=True)
    project_update_path.write_text(
        json.dumps(
            {
                "project_update_id": "delete-missing-project",
                "actions": [
                    {
                        "action_type": "delete_project",
                        "advertiser_id": "1001",
                        "project_name": "7R-测试",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute/preview",
        json={"project_update_path": "configs/project-updates/delete-missing-project.local.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["execution_enabled"] is False
    assert "第 1 条删除项目缺少项目 ID" in payload["summary"]["blocking_reasons"]


def test_project_management_execute_requires_confirmation(tmp_path):
    project_update_path = _write_project_update(tmp_path)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute",
        json={"confirmation": "我已确认", "project_update_path": project_update_path},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "真实执行前必须输入：确认执行"


def test_project_management_execute_starts_allowlisted_task(tmp_path, monkeypatch):
    project_update_path = _write_project_update(tmp_path)
    started = {}

    def fake_start_runner(command, *, cwd):
        started["command"] = command
        started["cwd"] = str(cwd)
        return 4321

    monkeypatch.setattr("backend.app.services.project_management.start_runner", fake_start_runner, raising=False)
    client = TestClient(create_app(project_root=tmp_path))

    response = client.post(
        "/api/project-management/execute",
        json={"confirmation": "确认执行", "project_update_path": project_update_path},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "项目管理执行任务"
    assert payload["summary"]["status"] == "queued"
    assert payload["summary"]["execution_enabled"] is True
    task = payload["task"]
    assert task["pid"] == 4321
    assert task["operation_type"] == "project_update_execute"
    assert task["command"][1] == "scripts/run_project_update_execute.py"
    assert "--execute" in task["command"]
    assert "--yes" in task["command"]
    task_path = tmp_path / "data" / "runs" / task["artifact_path"]
    assert task_path.exists()
    assert started["command"] == ["python3", "scripts/run_frontend_task.py", "--task", str(task_path)]

    tasks = client.get("/api/tasks").json()["items"]
    assert tasks[0]["task_id"] == task["task_id"]
    assert tasks[0]["operation_type"] == "project_update_execute"

    operation_payload = client.get("/api/operations", params={"operation_type": "project_update_execute"}).json()
    operation_rows = operation_payload["table"]["rows"]
    assert len(operation_rows) == 1
    assert operation_rows[0]["关联任务"] == task["task_id"]
    assert operation_rows[0]["操作"] == "项目管理真实执行"
    assert operation_rows[0]["状态"] == "排队中"
    assert operation_rows[0]["账户数"] == 2
    raw_row = operation_payload["raw"]["rows"][0]
    assert raw_row["result_status"] == "queued"
    assert raw_row["execute_artifact_path"] == project_update_path
