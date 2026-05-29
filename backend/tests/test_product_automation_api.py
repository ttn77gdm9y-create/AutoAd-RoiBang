import csv
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_product_fixture(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "configs" / "allowed-create-accounts.demo.local.json",
        {
            "allowed_target_accounts": [
                {"advertiser_id": "1001", "account_name": "演示账户一", "enable": True},
                {"advertiser_id": "1002", "account_name": "演示账户二", "enable": False},
            ]
        },
    )
    _write_json(
        tmp_path / "configs" / "products" / "demo-game.local.json",
        {
            "product_key": "demo-game",
            "product": "演示游戏",
            "platform": "WECHAT_GAME",
            "source_advertiser_id": "source-1",
            "source_advertiser_name": "演示源素材账户",
            "organization_id": "org-1",
            "allowed_target_accounts_path": "configs/allowed-create-accounts.demo.local.json",
            "automation": {
                "enabled": True,
                "account_discovery": {
                    "account_name_keyword": "演示游戏",
                    "account_remark_equals": "演示游戏-微小",
                },
                "source_material_preload": {"enabled": True, "target_scope": "allowed_accounts"},
                "source_material_rollup": {"enabled": True},
            },
        },
    )


def test_product_automation_overview_lists_product_configs_with_chinese_labels(tmp_path: Path):
    _write_product_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.get("/api/product-automation/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "产品自动化配置"
    assert payload["summary"]["execution_enabled"] is False
    row = payload["table"]["rows"][0]
    assert row["产品"] == "演示游戏"
    assert row["源素材账户名"] == "演示源素材账户"
    assert row["源素材账户 ID"] == "source-1"
    assert row["允许创建账户"] == 1
    assert row["预推送目标"] == "允许创建账户名单"
    assert "源素材预推送" in row["启用定时任务"]
    assert payload["raw"]["jobs"][0]["label"] == "每日素材明细同步"


def test_product_automation_save_defaults_preload_to_allowed_accounts(tmp_path: Path):
    client = _client(tmp_path)
    body = {
        "product_key": "new-game",
        "product": "新游戏",
        "platform": "WECHAT_GAME",
        "source_advertiser_name": "新游戏源素材账户",
        "source_advertiser_id": "source-2",
        "organization_id": "org-2",
        "allowed_target_accounts_path": "configs/allowed-create-accounts.new.local.json",
        "account_name_keyword": "新游戏",
        "account_remark_equals": "新游戏-微小",
        "enabled_jobs": ["material_daily_sync", "source_material_preload"],
    }

    response = client.post("/api/product-automation/config/save", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "committed"
    saved = json.loads((tmp_path / "configs/products/new-game.local.json").read_text(encoding="utf-8"))
    assert saved["source_advertiser_name"] == "新游戏源素材账户"
    assert saved["automation"]["source_material_preload"]["enabled"] is True
    assert saved["automation"]["source_material_preload"]["target_scope"] == "allowed_accounts"
    assert saved["automation"]["material_daily_sync"]["enabled"] is True


def test_product_automation_allowed_accounts_template_downloads_xlsx(tmp_path: Path):
    from openpyxl import load_workbook

    client = _client(tmp_path)

    response = client.get(
        "/api/product-automation/allowed-accounts/template",
        params={"product_key": "demo-game", "product": "演示游戏"},
    )

    assert response.status_code == 200
    assert "allowed-create-accounts-template.demo-game.xlsx" in response.headers["content-disposition"]
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    sheet = workbook.active
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    assert headers == ["产品名", "产品 Key", "账户名", "账户 ID", "是否启用", "备注"]
    first_row = [cell.value for cell in next(sheet.iter_rows(min_row=2, max_row=2))]
    assert first_row[0] == "演示游戏"
    assert first_row[1] == "demo-game"


def test_product_automation_allowed_accounts_upload_writes_json_and_returns_path(tmp_path: Path):
    client = _client(tmp_path)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["产品名", "产品 Key", "账户名", "账户 ID", "是否启用", "备注"])
    writer.writeheader()
    writer.writerow({"产品名": "演示游戏", "产品 Key": "demo-game", "账户名": "演示账户一", "账户 ID": "1001", "是否启用": "是", "备注": "郭靖账户"})
    writer.writerow({"产品名": "演示游戏", "产品 Key": "demo-game", "账户名": "演示账户二", "账户 ID": "1002", "是否启用": "否", "备注": "暂停"})

    response = client.post(
        "/api/product-automation/allowed-accounts/import",
        params={"product_key": "demo-game", "product": "演示游戏", "platform": "WECHAT_GAME"},
        files={"file": ("allowed.csv", buffer.getvalue().encode("utf-8"), "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "允许创建账户名单已生成"
    assert {"label": "启用账户", "value": 1} in payload["summary"]["items"]
    assert payload["raw"]["allowed_target_accounts_path"] == "configs/allowed-create-accounts.demo-game.local.json"
    saved_path = tmp_path / "configs" / "allowed-create-accounts.demo-game.local.json"
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved["product"] == "演示游戏"
    assert saved["allowed_target_accounts"] == [
        {
            "account_name": "演示账户一",
            "account_remark": "郭靖账户",
            "advertiser_id": "1001",
            "enable": True,
            "platform": "WECHAT_GAME",
            "product": "演示游戏",
            "product_key": "demo-game",
        }
    ]


def test_product_automation_dry_run_writes_request_without_execute(tmp_path: Path):
    _write_product_fixture(tmp_path)
    client = _client(tmp_path)

    response = client.post(
        "/api/product-automation/dry-run",
        json={"product_key": "demo-game", "job": "source_material_preload", "target_date": "yesterday"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "产品自动化预演"
    assert payload["summary"]["execution_enabled"] is False
    assert payload["table"]["rows"][0]["真实执行"] == "否"
    command = payload["table"]["rows"][0]["脚本命令"]
    assert "--execute" not in command
    assert "--yes" not in command
    request_path = Path(payload["table"]["rows"][0]["请求 JSON"])
    assert request_path.exists()
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert request_payload["source_material_preload_to_accounts"]["target_accounts"]["accounts"][0]["account_name"] == "演示账户一"
