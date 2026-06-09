import json
import sqlite3
from pathlib import Path

from roibang_v2.fetch import gravity_material_library
from roibang_v2.db.bootstrap import bootstrap_database
from roibang_v2.fetch.gravity_material_library import GravityMaterialClient
from roibang_v2.workflows.gravity_material_sync import run_gravity_material_sync_request


class FakeGravityMaterialClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_album_tree(self) -> dict:
        self.calls.append("get_album_tree")
        return {
            "code": 0,
            "data": [
                {
                    "id": "album-1",
                    "name": "点点英雄专辑",
                    "children": [{"id": "folder-1", "name": "6月新素材"}],
                }
            ],
        }

    def get_album_material_list(self, *, album_id: str, page: int, page_size: int, folder_id: str = "") -> dict:
        self.calls.append(f"get_album_material_list:{album_id}:{folder_id}:{page}:{page_size}")
        if page > 1:
            return {"code": 0, "data": {"list": [], "total": 2}}
        return {
            "code": 0,
            "data": {
                "total": 2,
                "list": [
                    {
                        "type": "material",
                        "material": {
                            "id": "gravity-m-1",
                            "file_name": "素材A",
                            "file_md5": "md5-a",
                            "status": 1,
                            "album_id": album_id,
                            "album_name": "点点英雄专辑",
                            "folder_id": folder_id,
                            "folder_name": "6月新素材",
                            "video_duration_second": 15,
                            "file_size": 2048,
                            "create_time": "2026-06-01T10:00:00+08:00",
                        },
                    },
                    {
                        "type": "material",
                        "material": {
                            "id": "gravity-m-2",
                            "file_name": "素材B",
                            "file_md5": "md5-b",
                            "status": 2,
                            "album_id": album_id,
                            "album_name": "点点英雄专辑",
                            "folder_id": folder_id,
                            "folder_name": "6月新素材",
                        },
                    },
                ],
            },
        }

    def get_material_report(self, *, material_ids: list[str], date_from: str, date_to: str, metrics: list[str]) -> dict:
        self.calls.append(f"get_material_report:{','.join(material_ids)}:{date_from}:{date_to}")
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "material_id": "gravity-m-1",
                        "AdCost": 12.5,
                        "AdShow": 100,
                        "AdClick": 5,
                        "AdConvert": 1,
                    }
                ]
            },
        }

    def get_album_material_report(
        self,
        *,
        album_id: str,
        date_from: str,
        date_to: str,
        page: int,
        page_size: int,
        metrics: list[str],
        gravity_metrics: list[str],
        folder_id: str = "",
    ) -> dict:
        self.calls.append(f"get_album_material_report:{album_id}:{folder_id}:{date_from}:{date_to}:{page}:{page_size}")
        if page > 1:
            return {"code": 0, "data": {"list": [], "page_info": {"page": page, "total_page": 1}}}
        cost = 12.5 if date_from == "2026-05-26" else 30.5
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "gravity_material_id": "gravity-m-1",
                        "material_id": "",
                        "file_name": "素材A",
                        "file_md5": "md5-a",
                        "AdCost": cost,
                        "AdShow": 100,
                        "AdClick": 5,
                        "AdConvert": 1,
                        "AdAppActivate": 1,
                        "AppFirstDayPayROI": "5.30%",
                    }
                ],
                "page_info": {"page": 1, "page_size": page_size, "total_number": 1, "total_page": 1},
            },
        }


class NestedFolderGravityMaterialClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_album_tree(self) -> dict:
        self.calls.append("get_album_tree")
        return {
            "code": 0,
            "data": {
                "tree": [
                    {
                        "id": "album-1",
                        "label": "黑旗-6480咸鱼-微小合集",
                        "children": [
                            {"id": "folder-a", "label": "基础素材"},
                            {"id": "folder-b", "label": "外包"},
                        ],
                    }
                ]
            },
        }

    def get_album_material_list(self, *, album_id: str, page: int, page_size: int, folder_id: str = "") -> dict:
        self.calls.append(f"get_album_material_list:{album_id}:{folder_id}:{page}:{page_size}")
        if page > 1:
            return {"code": 0, "data": {"list": [], "page_info": {"page": page, "total_page": 1}}}
        if album_id == "album-1" and not folder_id:
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"type": 2, "group": {"id": "folder-a", "name": "基础素材", "material_num": 1}},
                        {"type": 2, "group": {"id": "folder-b", "name": "外包", "material_num": 1}},
                    ],
                    "page_info": {"page": 1, "page_size": page_size, "total_number": 2, "total_page": 1},
                },
            }
        if album_id == "folder-a" and not folder_id:
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "type": 1,
                            "material": {
                                "id": "gravity-folder-a-m-1",
                                "file_name": "基础素材A",
                                "file_md5": "md5-folder-a",
                                "status": 1,
                                "video_duration_second": 12,
                            },
                        }
                    ],
                    "page_info": {"page": 1, "page_size": page_size, "total_number": 1, "total_page": 1},
                },
            }
        if album_id == "folder-b" and not folder_id:
            return {
                "code": 0,
                "data": {
                    "list": [
                        {"type": 2, "group": {"id": "folder-b-child", "name": "郭靖", "material_num": 1}},
                    ],
                    "page_info": {"page": 1, "page_size": page_size, "total_number": 1, "total_page": 1},
                },
            }
        if album_id == "folder-b-child" and not folder_id:
            return {
                "code": 0,
                "data": {
                    "list": [
                        {
                            "type": 1,
                            "material": {
                                "id": "gravity-folder-b-m-1",
                                "file_name": "外包素材B",
                                "file_md5": "md5-folder-b",
                                "status": 1,
                                "video_duration_second": 18,
                            },
                        }
                    ],
                    "page_info": {"page": 1, "page_size": page_size, "total_number": 1, "total_page": 1},
                },
            }
        return {"code": 0, "data": {"list": [], "page_info": {"page": 1, "total_page": 1}}}

    def get_material_report(self, *, material_ids: list[str], date_from: str, date_to: str, metrics: list[str]) -> dict:
        self.calls.append(f"get_material_report:{','.join(material_ids)}:{date_from}:{date_to}")
        return {"code": 0, "data": {"list": []}}

    def get_album_material_report(
        self,
        *,
        album_id: str,
        date_from: str,
        date_to: str,
        page: int,
        page_size: int,
        metrics: list[str],
        gravity_metrics: list[str],
        folder_id: str = "",
    ) -> dict:
        self.calls.append(f"get_album_material_report:{album_id}:{folder_id}:{date_from}:{date_to}:{page}:{page_size}")
        return {"code": 0, "data": {"list": [], "page_info": {"page": page, "total_page": 1}}}


class EmptyNestedFolderGravityMaterialClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_album_tree(self) -> dict:
        self.calls.append("get_album_tree")
        return {"code": 0, "data": {"tree": [{"id": "album-1", "label": "黑旗-6480咸鱼-微小合集"}]}}

    def get_album_material_list(self, *, album_id: str, page: int, page_size: int, folder_id: str = "") -> dict:
        self.calls.append(f"get_album_material_list:{album_id}:{folder_id}:{page}:{page_size}")
        if page > 1:
            return {"code": 0, "data": {"list": [], "page_info": {"page": page, "total_page": 1}}}
        if album_id == "album-1":
            return {
                "code": 0,
                "data": {
                    "list": [{"type": 2, "group": {"id": "empty-folder", "name": "空文件夹", "material_num": 0}}],
                    "page_info": {"page": 1, "page_size": page_size, "total_number": 1, "total_page": 1},
                },
            }
        return {"code": 0, "data": {"list": [], "page_info": {"page": 1, "total_page": 1}}}

    def get_material_report(self, *, material_ids: list[str], date_from: str, date_to: str, metrics: list[str]) -> dict:
        self.calls.append(f"get_material_report:{','.join(material_ids)}:{date_from}:{date_to}")
        return {"code": 0, "data": {"list": []}}

    def get_album_material_report(
        self,
        *,
        album_id: str,
        date_from: str,
        date_to: str,
        page: int,
        page_size: int,
        metrics: list[str],
        gravity_metrics: list[str],
        folder_id: str = "",
    ) -> dict:
        self.calls.append(f"get_album_material_report:{album_id}:{folder_id}:{date_from}:{date_to}:{page}:{page_size}")
        return {"code": 0, "data": {"list": [], "page_info": {"page": page, "total_page": 1}}}


class PagedAlbumReportGravityMaterialClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_album_tree(self) -> dict:
        self.calls.append("get_album_tree")
        return {"code": 0, "data": [{"id": "album-1", "name": "黑旗-6480咸鱼-微小合集"}]}

    def get_album_material_list(self, *, album_id: str, page: int, page_size: int, folder_id: str = "") -> dict:
        self.calls.append(f"get_album_material_list:{album_id}:{folder_id}:{page}:{page_size}")
        if page > 1:
            return {"code": 0, "data": {"list": [], "page_info": {"page": page, "total_page": 1}}}
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "type": 1,
                        "material": {
                            "id": "gravity-m-1",
                            "file_name": "素材A",
                            "file_md5": "md5-a",
                            "status": 1,
                            "file_type": "video",
                            "create_time": "2026-06-01 10:00:00",
                        },
                    },
                    {
                        "type": 1,
                        "material": {
                            "id": "gravity-m-2",
                            "file_name": "素材B",
                            "file_md5": "md5-b",
                            "status": 1,
                            "file_type": "video",
                            "create_time": "2026-06-01 11:00:00",
                        },
                    },
                ],
                "page_info": {"page": 1, "page_size": page_size, "total_number": 2, "total_page": 1},
            },
        }

    def get_material_report(self, *, material_ids: list[str], date_from: str, date_to: str, metrics: list[str]) -> dict:
        self.calls.append(f"legacy_get_material_report:{','.join(material_ids)}:{date_from}:{date_to}")
        return {"code": 0, "data": {"list": []}}

    def get_album_material_report(
        self,
        *,
        album_id: str,
        date_from: str,
        date_to: str,
        page: int,
        page_size: int,
        metrics: list[str],
        gravity_metrics: list[str],
        folder_id: str = "",
    ) -> dict:
        self.calls.append(f"get_album_material_report:{album_id}:{folder_id}:{date_from}:{date_to}:{page}:{page_size}")
        base = 7 if date_from == "2026-05-26" else 30
        material_id = "gravity-m-1" if page == 1 else "gravity-m-2"
        return {
            "code": 0,
            "data": {
                "list": [
                    {
                        "gravity_material_id": material_id,
                        "material_id": "",
                        "file_md5": f"md5-{material_id[-1]}",
                        "file_name": f"素材{material_id[-1]}",
                        "file_type": "video",
                        "album_id": int(album_id.replace("album-", "")) if album_id.replace("album-", "").isdigit() else album_id,
                        "album_name": "黑旗-6480咸鱼-微小合集",
                        "folder_id": 345703,
                        "folder_name": "老素材",
                        "create_time": "2026-04-30 21:37:15",
                        "AdCost": str(base + page / 10),
                        "AdShow": base * 100 + page,
                        "AdClick": base * 10 + page,
                        "AdConvert": base + page,
                        "AppFirstDayPayROI": f"{base + page}.30%",
                    }
                ],
                "page_info": {"page": page, "page_size": page_size, "total_number": 2, "total_page": 2},
            },
        }


def test_gravity_material_client_uses_authorization_header_as_saved():
    client = GravityMaterialClient(
        {
            "authorization": "document-token-value",
            "gravity_cid": "182",
            "gravity_email": "hongen@example.com",
            "gravity_id": "406",
            "gravity_super": "false",
        }
    )

    assert client.headers["Authorization"] == "document-token-value"


def test_gravity_material_client_requests_album_material_report_like_browser_curl(monkeypatch):
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"code": 0, "data": {"list": [], "page_info": {"total_page": 1}}}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(gravity_material_library.urllib.request, "urlopen", fake_urlopen)
    client = GravityMaterialClient(
        {
            "authorization": "document-token-value",
            "gravity_cid": "182",
            "gravity_email": "hongen@example.com",
            "gravity_id": "406",
            "gravity_super": "false",
        },
        base_url="https://api-insight.gravity-engine.com",
    )

    result = client.get_album_material_report(
        album_id="334580",
        folder_id="360675",
        date_from="2026-06-01",
        date_to="2026-06-07",
        page=2,
        page_size=100,
        metrics=["AdCost", "AdShow", "AdClick", "AdConvert"],
        gravity_metrics=["AppFirstDayPayROI"],
    )

    assert result["code"] == 0
    assert captured["url"] == "https://api-insight.gravity-engine.com/report/api/v3/datareport/material_get/"
    assert captured["method"] == "POST"
    body = captured["body"]
    assert body == {
        "data_dims": ["material"],
        "date_dims": "total",
        "filters": [
            {"field": "ad_platform", "operator": "EQUALS", "values": ["aggregate"]},
            {"field": "album_id", "operator": "IN", "values": [334580]},
            {"field": "folder_id", "operator": "IN", "values": [360675]},
        ],
        "metrics_list": ["AdCost", "AdShow", "AdClick", "AdConvert"],
        "gravity_metrics_list": ["AppFirstDayPayROI"],
        "stat_list": [],
        "date_list": ["2026-06-01", "2026-06-07"],
        "relate_dims": [],
        "order_by": [],
        "page": 2,
        "page_size": 100,
    }


def test_gravity_material_sync_imports_bound_album_materials_without_uploading(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO product_gravity_album_bindings (
              product, album_id, album_name, folder_id, folder_name, is_active
            ) VALUES ('点点英雄', 'album-1', '黑旗-奇门（塔防）', 'folder-1', '6月新素材', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO materials (
              material_id, name, material_type, video_id, review_status,
              cost_lookback, score, payload_json, source, synced_at
            ) VALUES ('old-gravity', '旧素材', 'video', '', '可用', 0, 0, '{}', 'gravity_engine', 'old')
            """
        )
        conn.execute(
            """
            INSERT INTO product_source_materials (
              product, source_advertiser_id, organization_id, material_id,
              video_id, name, material_type, review_status, signature,
              duration, file_size, create_time, tag_ids_json, is_active,
              first_seen_at, last_seen_at, cost_lookback, score,
              payload_json, source, synced_at
            ) VALUES (
              '点点英雄', 'gravity_engine_182', '182', 'old-gravity',
              '', '旧素材', 'video', '可用', 'old-md5',
              0, 0, '', '[]', 1,
              'old', 'old', 0, 0,
              '{}', 'gravity_engine', 'old'
            )
            """
        )
    client = FakeGravityMaterialClient()

    result = run_gravity_material_sync_request(
        {
            "auth": {
                "authorization": "token",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
                "gravity_super": "false",
            },
            "page_size": 2,
            "max_pages": 3,
            "report_date_range": {"start": "2026-05-02", "end": "2026-06-01"},
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        client=client,
    )

    assert result["ok"] is True
    assert result["workflow"] == "gravity_material_sync"
    assert result["execution_enabled"] is False
    assert result["summary"]["materials_received"] == 2
    assert result["summary"]["active_materials_imported"] == 1
    assert result["summary"]["inactive_materials_skipped"] == 1
    assert result["summary"]["inactive_product_source_materials"] == 1
    assert "upload" not in " ".join(client.calls)
    assert result["中文摘要"] == "更新引力素材完成：读取 1 个绑定，保存 1 个可用素材资料，跳过 1 个禁用素材；未下载素材文件、未上传素材、未创建广告。"

    with sqlite3.connect(db_path) as conn:
        imported = conn.execute(
            """
            SELECT source_advertiser_id, organization_id, material_id, video_id,
                   name, review_status, signature, is_active, source
            FROM product_source_materials
            WHERE product = '点点英雄'
            ORDER BY material_id
            """
        ).fetchall()
        assert imported == [
            ("gravity_engine_182", "182", "gravity-m-1", "", "素材A", "可用", "md5-a", 1, "gravity_engine"),
            ("gravity_engine_182", "182", "old-gravity", "", "旧素材", "可用", "old-md5", 0, "gravity_engine"),
        ]
        rollups = conn.execute(
            """
            SELECT window_key, window_days, material_id, stat_cost, show_cnt, click_cnt, convert_cnt, active_register,
                   ROUND(roi_1day_cost_weighted, 3)
            FROM product_source_material_metric_rollups
            WHERE product = '点点英雄' AND material_id = 'gravity-m-1'
            ORDER BY window_days
            """
        ).fetchall()
        assert rollups == [
            ("last_7d", 7, "gravity-m-1", 12.5, 100, 5, 1, 1, 0.053),
            ("last_30d", 30, "gravity-m-1", 30.5, 100, 5, 1, 1, 0.053),
        ]


def test_gravity_material_sync_reads_paged_album_reports_for_7d_and_30d(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO product_gravity_album_bindings (
              product, album_id, album_name, folder_id, folder_name, is_active
            ) VALUES ('点点英雄', 'album-1', '黑旗-6480咸鱼-微小合集', '', '', 1)
            """
        )
    client = PagedAlbumReportGravityMaterialClient()

    result = run_gravity_material_sync_request(
        {
            "auth": {
                "authorization": "token",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
            },
            "target_album_names": ["黑旗-6480咸鱼-微小合集"],
            "page_size": 10,
            "report_page_size": 1,
            "report_date_range": {"start": "2026-05-02", "end": "2026-06-01"},
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        client=client,
    )

    assert result["ok"] is True
    assert result["summary"]["rollup_rows_written"] == 4
    assert result["summary"]["report_pages_read"] == 4
    assert result["summary"]["report_rows_received"] == 4
    assert not any(call.startswith("legacy_get_material_report") for call in client.calls)
    assert "get_album_material_report:album-1::2026-05-26:2026-06-01:1:1" in client.calls
    assert "get_album_material_report:album-1::2026-05-26:2026-06-01:2:1" in client.calls
    assert "get_album_material_report:album-1::2026-05-02:2026-06-01:1:1" in client.calls
    assert "get_album_material_report:album-1::2026-05-02:2026-06-01:2:1" in client.calls

    with sqlite3.connect(db_path) as conn:
        rollups = conn.execute(
            """
            SELECT window_key, window_days, period_start, period_end, material_id,
                   stat_cost, show_cnt, click_cnt, convert_cnt, roi_1day_cost_weighted
            FROM product_source_material_metric_rollups
            WHERE product = '点点英雄'
            ORDER BY window_days, material_id
            """
        ).fetchall()

    normalized_rollups = [(*row[:9], round(row[9], 3)) for row in rollups]
    assert normalized_rollups == [
        ("last_7d", 7, "2026-05-26", "2026-06-01", "gravity-m-1", 7.1, 701, 71, 8, 0.083),
        ("last_7d", 7, "2026-05-26", "2026-06-01", "gravity-m-2", 7.2, 702, 72, 9, 0.093),
        ("last_30d", 30, "2026-05-02", "2026-06-01", "gravity-m-1", 30.1, 3001, 301, 31, 0.313),
        ("last_30d", 30, "2026-05-02", "2026-06-01", "gravity-m-2", 30.2, 3002, 302, 32, 0.323),
    ]


def test_gravity_material_sync_drills_bound_album_folders_before_importing(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO product_gravity_album_bindings (
              product, album_id, album_name, folder_id, folder_name, is_active
            ) VALUES ('点点英雄', 'album-1', '黑旗-6480咸鱼-微小合集', '', '', 1)
            """
        )
    client = NestedFolderGravityMaterialClient()

    result = run_gravity_material_sync_request(
        {
            "auth": {
                "authorization": "token",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
            },
            "target_album_names": ["黑旗-6480咸鱼-微小合集"],
            "page_size": 10,
            "max_pages": 3,
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        client=client,
    )

    assert result["ok"] is True
    assert result["summary"]["materials_received"] == 2
    assert result["summary"]["active_materials_imported"] == 2
    assert result["summary"]["folders_scanned"] == 3
    assert result["table"]["rows"][0]["扫描文件夹"] == 3
    assert result["table"]["rows"][0]["发现素材"] == 2
    assert "get_album_material_list:folder-a::1:10" in client.calls
    assert "get_album_material_list:folder-b-child::1:10" in client.calls

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT material_id, name, signature, json_extract(payload_json, '$.folder_name')
            FROM product_source_materials
            WHERE product = '点点英雄' AND source = 'gravity_engine'
            ORDER BY material_id
            """
        ).fetchall()
    assert rows == [
        ("gravity-folder-a-m-1", "基础素材A", "md5-folder-a", "基础素材"),
        ("gravity-folder-b-m-1", "外包素材B", "md5-folder-b", "郭靖"),
    ]


def test_gravity_material_sync_warns_when_scan_finds_no_materials(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO product_gravity_album_bindings (
              product, album_id, album_name, folder_id, folder_name, is_active
            ) VALUES ('点点英雄', 'album-1', '黑旗-6480咸鱼-微小合集', '', '', 1)
            """
        )
    client = EmptyNestedFolderGravityMaterialClient()

    result = run_gravity_material_sync_request(
        {
            "auth": {
                "authorization": "token",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
            },
            "target_album_names": ["黑旗-6480咸鱼-微小合集"],
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        client=client,
    )

    assert result["ok"] is True
    assert result["summary"]["materials_received"] == 0
    assert result["summary"]["folders_scanned"] == 1
    assert "已扫描 1 个文件夹，但没有发现素材" in result["中文摘要"]
    assert any("已扫描 1 个文件夹，但没有发现素材" in warning for warning in result["warnings"])


def test_gravity_material_sync_blocks_when_no_active_bindings(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)

    result = run_gravity_material_sync_request(
        {
            "auth": {
                "authorization": "token",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        client=FakeGravityMaterialClient(),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "请先在引力素材库页面绑定产品和专辑" in result["blocking_reasons"][0]


def test_gravity_material_sync_blocks_active_binding_outside_target_album_scope(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO product_gravity_album_bindings (
              product, album_id, album_name, folder_id, folder_name, is_active
            ) VALUES ('点点英雄', 'album-other', '其他游戏素材', '', '', 1)
            """
        )
    client = FakeGravityMaterialClient()

    result = run_gravity_material_sync_request(
        {
            "auth": {
                "authorization": "token",
                "gravity_cid": "182",
                "gravity_email": "hongen@example.com",
                "gravity_id": "406",
            }
        },
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        client=client,
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "不在允许同步的引力专辑范围内" in result["blocking_reasons"][0]
    assert client.calls == []


def test_gravity_material_sync_blocks_missing_auth_file_with_chinese_reason(tmp_path: Path):
    db_path = tmp_path / "data" / "roibang_v2.sqlite3"
    bootstrap_database(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO product_gravity_album_bindings (
              product, album_id, album_name, folder_id, folder_name, is_active
            ) VALUES ('点点英雄', 'album-1', '点点英雄专辑', '', '', 1)
            """
        )

    result = run_gravity_material_sync_request(
        {"auth_file": str(tmp_path / "missing-token.json")},
        db_path=db_path,
        runs_dir=tmp_path / "runs",
        client=FakeGravityMaterialClient(),
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert "未找到引力 Token 文件" in result["blocking_reasons"][0]
    assert not any("缺少字段" in reason for reason in result["blocking_reasons"])
    assert result["external_api_calls"] == 0
