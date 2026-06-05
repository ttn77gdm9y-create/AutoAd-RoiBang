import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.services import atomic_write
from backend.app.main import create_app
from backend.app.services.accounts_store import save_accounts


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(project_root=tmp_path))


def _paste_text() -> str:
    return "\n".join(
        [
            "product_key\tproduct_name\tadvertiser_id\tadvertiser_name\tchannel\towner\taccount_remark\tstatus\tnotes",
            "diandian-hero\t点点英雄\t1866125088740552\t黑旗游戏\t微信\t运营A\t点点英雄-黑旗\tactive\t首批",
            "zuoyi\t你行你先坐\t1856732761394249\t赚亿点点\t微信\t运营B\t坐哪里-赚亿\tpaused\t观察",
        ]
    )


def test_paste_preview_returns_chinese_summary_and_does_not_write(tmp_path):
    client = _client(tmp_path)

    response = client.post("/api/accounts/paste/preview", json={"text": _paste_text()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户导入预览"
    assert {"label": "新增", "value": 2} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["处理方式"] == "新增"
    assert not (tmp_path / "configs" / "accounts" / "product-accounts.local.json").exists()


def test_paste_commit_upserts_accounts_and_updates_existing(tmp_path):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "old",
                        "product_name": "旧产品",
                        "advertiser_id": "1866125088740552",
                        "advertiser_name": "旧账户名",
                        "channel": "微信",
                        "owner": "旧负责人",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.post("/api/accounts/paste/commit", json={"text": _paste_text()})

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "更新", "value": 1} in payload["summary"]["items"]
    assert {"label": "新增", "value": 1} in payload["summary"]["items"]
    saved = json.loads(store.read_text(encoding="utf-8"))
    by_id = {row["advertiser_id"]: row for row in saved["accounts"]}
    assert by_id["1866125088740552"]["product_name"] == "点点英雄"
    assert by_id["1856732761394249"]["status"] == "paused"


def test_paste_preview_reports_missing_required_fields(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/api/accounts/paste/preview",
        json={"text": "product_key\tadvertiser_id\nx\t"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert payload["summary"]["blocking_reasons"]
    assert payload["table"]["rows"][0]["处理方式"] == "错误"


def test_csv_upload_preview_and_commit(tmp_path):
    client = _client(tmp_path)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "product_key",
            "product_name",
            "advertiser_id",
            "advertiser_name",
            "channel",
            "owner",
            "account_remark",
            "status",
            "notes",
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "product_key": "diandian-hero",
            "product_name": "点点英雄",
            "advertiser_id": "1866125088740552",
            "advertiser_name": "黑旗游戏",
            "channel": "微信",
            "owner": "运营A",
            "account_remark": "点点英雄-黑旗",
            "status": "active",
            "notes": "",
        }
    )
    content = buffer.getvalue().encode("utf-8")

    preview = client.post(
        "/api/accounts/import/preview",
        files={"file": ("accounts.csv", content, "text/csv")},
    )
    commit = client.post(
        "/api/accounts/import/commit",
        files={"file": ("accounts.csv", content, "text/csv")},
    )

    assert preview.status_code == 200
    assert preview.json()["summary"]["items"][0] == {"label": "读取行数", "value": 1}
    assert commit.status_code == 200
    assert (tmp_path / "configs" / "accounts" / "product-accounts.local.json").exists()


def test_accounts_endpoint_filters_and_export_returns_csv(tmp_path):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1",
                        "advertiser_name": "A",
                        "channel": "微信",
                        "owner": "运营A",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    },
                    {
                        "product_key": "zuoyi",
                        "product_name": "你行你先坐",
                        "advertiser_id": "2",
                        "advertiser_name": "B",
                        "channel": "微信",
                        "owner": "运营B",
                        "account_remark": "",
                        "status": "paused",
                        "notes": "",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    filtered = client.get("/api/accounts", params={"product_key": "diandian-hero", "status": "active"})
    exported = client.get("/api/accounts/export")

    assert filtered.status_code == 200
    assert filtered.json()["summary"]["items"][0] == {"label": "账户数", "value": 1}
    assert "product_key,product_name,advertiser_id" in exported.text
    assert "点点英雄" in exported.text


def test_accounts_template_download_returns_fillable_csv(tmp_path):
    client = _client(tmp_path)

    response = client.get("/api/accounts/template")

    assert response.status_code == 200
    assert "product-accounts-template.csv" in response.headers["content-disposition"]
    assert response.text.startswith("product_key,product_name,advertiser_id,advertiser_name")
    assert "示例" in response.text


def test_bulk_update_accounts_changes_only_filtered_rows(tmp_path):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1001",
                        "advertiser_name": "黑旗游戏-1",
                        "channel": "",
                        "owner": "",
                        "account_remark": "旧备注",
                        "status": "active",
                        "notes": "",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1002",
                        "advertiser_name": "黑旗游戏-2",
                        "channel": "",
                        "owner": "",
                        "account_remark": "保持",
                        "status": "paused",
                        "notes": "",
                    },
                    {
                        "product_key": "other",
                        "product_name": "其他产品",
                        "advertiser_id": "2001",
                        "advertiser_name": "其他账户",
                        "channel": "",
                        "owner": "",
                        "account_remark": "保持",
                        "status": "active",
                        "notes": "",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.post(
        "/api/accounts/bulk-update",
        json={
            "product_key": "diandian-hero",
            "status": "active",
            "updates": {"channel": "WECHAT_GAME", "owner": "郭靖", "account_remark": "点点英雄-黑旗"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户批量修改完成"
    assert payload["summary"]["status"] == "committed"
    assert {"label": "匹配账户", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["渠道"] == "微信"
    assert payload["table"]["rows"][0]["负责人"] == "郭靖"
    saved = json.loads(store.read_text(encoding="utf-8"))
    by_id = {row["advertiser_id"]: row for row in saved["accounts"]}
    assert by_id["1001"]["channel"] == "微信"
    assert by_id["1001"]["owner"] == "郭靖"
    assert by_id["1001"]["account_remark"] == "点点英雄-黑旗"
    assert by_id["1002"]["account_remark"] == "保持"
    assert by_id["2001"]["owner"] == ""


def test_bulk_update_accounts_preview_does_not_write(tmp_path):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1001",
                        "advertiser_name": "黑旗游戏-1",
                        "channel": "",
                        "owner": "",
                        "account_remark": "旧备注",
                        "status": "active",
                        "notes": "",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.post(
        "/api/accounts/bulk-update/preview",
        json={
            "product_key": "diandian-hero",
            "status": "active",
            "updates": {"owner": "郭靖"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "账户批量修改预览"
    assert payload["summary"]["status"] == "planned"
    assert payload["summary"]["execution_enabled"] is True
    assert {"label": "匹配账户", "value": 1} in payload["summary"]["items"]
    assert payload["table"]["rows"][0]["负责人"] == "郭靖"
    saved = json.loads(store.read_text(encoding="utf-8"))
    assert saved["accounts"][0]["owner"] == ""


def test_bulk_update_accounts_can_disable_selected_account_ids(tmp_path):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1001",
                        "advertiser_name": "账户一",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    },
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1002",
                        "advertiser_name": "账户二",
                        "channel": "微信",
                        "owner": "郭靖",
                        "account_remark": "",
                        "status": "active",
                        "notes": "",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    preview = client.post(
        "/api/accounts/bulk-update/preview",
        json={"advertiser_ids": ["1002"], "updates": {"status": "disabled"}},
    )

    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["summary"]["status"] == "planned"
    assert {"label": "匹配账户", "value": 1} in preview_payload["summary"]["items"]
    assert preview_payload["table"]["rows"][0]["账户 ID"] == "1002"
    assert preview_payload["table"]["rows"][0]["状态"] == "disabled"
    assert json.loads(store.read_text(encoding="utf-8"))["accounts"][1]["status"] == "active"

    commit = client.post(
        "/api/accounts/bulk-update",
        json={"advertiser_ids": ["1002"], "updates": {"status": "disabled"}},
    )

    assert commit.status_code == 200
    saved = json.loads(store.read_text(encoding="utf-8"))
    by_id = {row["advertiser_id"]: row for row in saved["accounts"]}
    assert by_id["1001"]["status"] == "active"
    assert by_id["1002"]["status"] == "disabled"


def test_bulk_update_accounts_blocks_empty_updates(tmp_path):
    client = _client(tmp_path)

    response = client.post("/api/accounts/bulk-update", json={"updates": {}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["status"] == "blocked"
    assert "至少勾选一个要修改的字段" in payload["summary"]["blocking_reasons"]


def test_history_backfill_fills_missing_fields_and_preserves_manual_values(tmp_path):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "",
                        "product_name": "",
                        "advertiser_id": "1001",
                        "advertiser_name": "手工账户名",
                        "channel": "",
                        "owner": "运营A",
                        "account_remark": "",
                        "status": "paused",
                        "notes": "手工备注",
                    },
                    {
                        "product_key": "history-6ed19bac",
                        "product_name": "点点英雄",
                        "advertiser_id": "1004",
                        "advertiser_name": "已有历史账户",
                        "channel": "WECHAT_GAME",
                        "owner": "",
                        "account_remark": "",
                        "status": "active",
                        "notes": "历史数据自动补全",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    runs_dir = tmp_path / "data" / "runs" / "history"
    runs_dir.mkdir(parents=True)
    (runs_dir / "one.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1001",
                        "advertiser_name": "历史账户名",
                        "channel": "微信",
                    },
                    {
                        "operator": "1002",
                        "account_name": "赚亿点点",
                        "brandName": "你行你先坐",
                        "brandId": "2133031",
                        "username": "gh_ee6a2f131422",
                    },
                    {
                        "advertiser_id": "1003",
                        "advertiser_name": "黑旗游戏-2",
                        "product_name": "点点英雄",
                        "channel": "WECHAT_GAME",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.post("/api/accounts/backfill/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["title"] == "历史数据补全账户库"
    assert {"label": "新增", "value": 2} in payload["summary"]["items"]
    assert {"label": "补全", "value": 1} in payload["summary"]["items"]
    saved = json.loads(store.read_text(encoding="utf-8"))
    by_id = {row["advertiser_id"]: row for row in saved["accounts"]}
    assert by_id["1001"]["product_name"] == "点点英雄"
    assert by_id["1001"]["advertiser_name"] == "手工账户名"
    assert by_id["1001"]["owner"] == "运营A"
    assert by_id["1001"]["status"] == "paused"
    assert by_id["1002"]["product_key"] == "brand-2133031"
    assert by_id["1002"]["channel"] == "微信"
    assert by_id["1003"]["product_key"] == "diandian-hero"
    assert by_id["1003"]["channel"] == "微信"
    assert by_id["1004"]["product_key"] == "diandian-hero"
    assert by_id["1004"]["channel"] == "微信"


def test_history_backfill_repairs_id_account_names_from_config_sources(tmp_path):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "product_key": "diandian-hero",
                        "product_name": "点点英雄",
                        "advertiser_id": "1866125088740552",
                        "advertiser_name": "1866125088740552",
                        "channel": "",
                        "owner": "",
                        "account_remark": "",
                        "status": "active",
                        "notes": "历史数据自动补全",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    allowed = tmp_path / "configs" / "allowed-create-accounts.diandian-hero.local.json"
    allowed.write_text(
        json.dumps(
            {
                "product": "点点英雄",
                "channel": "wx",
                "allowed_target_accounts": [
                    {
                        "advertiser_id": "1866125088740552",
                        "account_name": "点点英雄-微小-郭靖-002",
                        "product": "点点英雄",
                        "channel": "wx",
                        "enable": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = _client(tmp_path)

    response = client.post("/api/accounts/backfill/history")

    assert response.status_code == 200
    payload = response.json()
    assert {"label": "补全", "value": 1} in payload["summary"]["items"]
    saved = json.loads(store.read_text(encoding="utf-8"))
    account = saved["accounts"][0]
    assert account["advertiser_name"] == "点点英雄-微小-郭靖-002"
    assert account["channel"] == "微信"


def test_save_accounts_atomic_failure_preserves_existing_store(tmp_path, monkeypatch):
    store = tmp_path / "configs" / "accounts" / "product-accounts.local.json"
    store.parent.mkdir(parents=True)
    original_payload = {
        "accounts": [
            {
                "product_key": "old",
                "product_name": "旧产品",
                "advertiser_id": "1001",
                "advertiser_name": "旧账户",
                "channel": "微信",
                "owner": "",
                "account_remark": "",
                "status": "active",
                "notes": "",
            }
        ]
    }
    store.write_text(json.dumps(original_payload, ensure_ascii=False), encoding="utf-8")

    def fail_replace(_source: Path, _target: Path) -> None:
        raise RuntimeError("replace failed")

    monkeypatch.setattr(atomic_write.os, "replace", fail_replace)

    with pytest.raises(RuntimeError, match="replace failed"):
        save_accounts(
            tmp_path / "configs",
            [
                {
                    "product_key": "new",
                    "product_name": "新产品",
                    "advertiser_id": "2001",
                    "advertiser_name": "新账户",
                    "channel": "微信",
                    "owner": "",
                    "account_remark": "",
                    "status": "active",
                    "notes": "",
                }
            ],
        )

    assert json.loads(store.read_text(encoding="utf-8")) == original_payload
    assert not (store.parent / ".product-accounts.local.json.tmp").exists()
