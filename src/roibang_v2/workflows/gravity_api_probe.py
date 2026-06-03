from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact

WORKFLOW = "gravity_api_probe"

REQUIRED_AUTH_FIELDS = ("jwt_token", "gravity_cid", "gravity_email", "gravity_id")
BASE_URL = "https://api-insight.gravity-engine.com"
REPORT_METRICS = ["AdCost", "AdShow", "AdClick", "AdConvert"]
UPLOAD_STATUS_PROBE_TASK_ID = "readonly-probe-no-upload"
PROBE_SCOPE_LABELS = {
    "local_contract": "本地鉴权与文档字段核验",
    "readonly_api": "外部只读接口探测",
}


class GravityApiHttpClient:
    def __init__(self, auth_payload: dict[str, Any], *, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {str(auth_payload.get('jwt_token') or '').strip()}",
            "gravity_cid": str(auth_payload.get("gravity_cid") or "").strip(),
            "gravity_email": str(auth_payload.get("gravity_email") or "").strip(),
            "gravity_id": str(auth_payload.get("gravity_id") or "").strip(),
            "gravity_super": str(auth_payload.get("gravity_super") or "false").strip() or "false",
            "Content-Type": "application/json",
        }

    def get_album_tree(self) -> dict[str, Any]:
        return self._request("GET", "/turbo_engine/api/v1/asset/material/album/tree/")

    def get_album_material_list(self, *, album_id: str, page: int, page_size: int) -> dict[str, Any]:
        return self._request(
            "POST",
            "/turbo_engine/api/v1/asset/material/album/list/",
            {
                "album_id": album_id,
                "page": page,
                "page_size": page_size,
            },
        )

    def get_material_detail(self, *, material_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"material_id": material_id})
        return self._request("GET", f"/turbo_engine/api/v1/asset/material/manage/local/detail/?{query}")

    def get_material_report(self, *, material_ids: list[str], date_from: str, date_to: str, metrics: list[str]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/report/api/v3/datareport/material_get/",
            {
                "material_ids": material_ids,
                "date_from": date_from,
                "date_to": date_to,
                "metrics": metrics,
            },
        )

    def get_upload_material_status(self, *, task_id: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"task_id": task_id})
        return self._request("GET", f"/turbo_engine/api/v1/task/bytedance/upload_material/status/?{query}")

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"code": exc.code, "msg": raw}
            if isinstance(parsed, dict):
                parsed.setdefault("http_status", exc.code)
                return parsed
            return {"code": exc.code, "msg": raw, "http_status": exc.code}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        return parsed if isinstance(parsed, dict) else {"data": parsed}


def run_gravity_api_probe(
    *,
    auth_file: str | Path,
    runs_dir: str | Path,
    probe_scope: str = "local_contract",
    sample_limit: int | str = 3,
    client: Any | None = None,
) -> dict[str, Any]:
    auth_path = Path(auth_file)
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    auth_payload = _read_auth(auth_path)
    normalized_scope = _normalize_scope(probe_scope)
    normalized_sample_limit = _normalize_sample_limit(sample_limit)
    if auth_payload is None:
        blocking_reasons.append(f"未找到引力 Token 文件：{auth_path}")
        auth_payload = {}
    missing_fields = [field for field in REQUIRED_AUTH_FIELDS if not str(auth_payload.get(field) or "").strip()]
    if missing_fields and not blocking_reasons:
        blocking_reasons.append(f"引力 Token 文件缺少字段：{', '.join(missing_fields)}")
    if str(auth_payload.get("jwt_token") or "").strip():
        warnings.append("已发现本地引力 Token；结果中不会展示 token 明文。")
    if not blocking_reasons:
        warnings.append("本探测不上传素材、不创建广告、不修改投放。")

    endpoint_rows: list[dict[str, Any]] = []
    field_rows = _local_contract_field_rows()
    sample_rows: list[dict[str, Any]] = []
    raw_probe: dict[str, Any] = {"scope": normalized_scope, "endpoint_results": {}}
    external_api_calls = 0
    if not blocking_reasons and normalized_scope == "readonly_api":
        probe_client = client or GravityApiHttpClient(auth_payload)
        probe_result = _probe_readonly_apis(probe_client, sample_limit=normalized_sample_limit)
        endpoint_rows = probe_result["endpoint_rows"]
        field_rows = probe_result["field_rows"]
        sample_rows = probe_result["sample_rows"]
        raw_probe = probe_result["raw"]
        external_api_calls = int(probe_result["external_api_calls"])
        warnings.extend(probe_result["warnings"])
    elif not blocking_reasons:
        endpoint_rows = [
            {
                "接口": "外部只读接口",
                "结果": "未执行",
                "说明": "当前只核验 token 和文档字段，未访问引力外部接口。",
            }
        ]

    ok = not blocking_reasons
    status = "completed" if ok else "blocked"
    payload: dict[str, Any] = {
        "ok": ok,
        "workflow": WORKFLOW,
        "phase": "readonly_api_probe" if normalized_scope == "readonly_api" and ok else "local_contract_probe",
        "status": status,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "execution_enabled": False,
        "external_api_calls": external_api_calls,
        "中文摘要": _summary_text(ok=ok, auth_path=auth_path, missing_fields=missing_fields, scope=normalized_scope, calls=external_api_calls),
        "summary": {
            "auth_file_exists": auth_path.exists(),
            "auth_file": str(auth_path),
            "gravity_cid": str(auth_payload.get("gravity_cid") or ""),
            "gravity_email": str(auth_payload.get("gravity_email") or ""),
            "gravity_id": str(auth_payload.get("gravity_id") or ""),
            "gravity_super": str(auth_payload.get("gravity_super") or "false"),
            "jwt_token_present": bool(str(auth_payload.get("jwt_token") or "").strip()),
            "jwt_token_length": len(str(auth_payload.get("jwt_token") or "")),
            "missing_field_count": len(missing_fields),
            "probe_scope": normalized_scope,
            "probe_scope_label": PROBE_SCOPE_LABELS[normalized_scope],
            "sample_limit": normalized_sample_limit,
            "verified_field_count": sum(1 for row in field_rows if str(row.get("系统结论") or "").startswith("已")),
            "upload_material_called": False,
        },
        "table": {"columns": ["核验项", "系统结论", "依据", "风险处理"], "rows": field_rows},
        "sections": [
            {"title": "接口核验表", "table": {"columns": ["接口", "结果", "说明"], "rows": endpoint_rows}},
            {"title": "字段核验表", "table": {"columns": ["核验项", "系统结论", "依据", "风险处理"], "rows": field_rows}},
            {"title": "样本素材表", "table": {"columns": ["素材 ID", "素材名称", "MD5", "专辑", "文件夹", "状态", "拒审字段"], "rows": sample_rows}},
        ],
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "guardrails": [
            "本探测不上传素材。",
            "本探测不创建广告。",
            "本探测不修改预算、出价或项目状态。",
            "结果中不输出 JWT Token 明文。",
        ],
        "raw": raw_probe,
    }
    payload["artifact_path"] = str(write_run_artifact(runs_dir, WORKFLOW, payload))
    return payload


def _read_auth(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        return {"_parse_error": str(exc)}
    return value if isinstance(value, dict) else {"_parse_error": "Token 文件不是 JSON 对象"}


def _probe_readonly_apis(client: Any, *, sample_limit: int) -> dict[str, Any]:
    warnings: list[str] = []
    endpoint_rows: list[dict[str, Any]] = []
    raw: dict[str, Any] = {"endpoint_results": {}, "scope": "readonly_api", "upload_material_called": False}
    external_api_calls = 0

    album_tree = client.get_album_tree()
    external_api_calls += 1
    raw["endpoint_results"]["album_tree"] = _sanitized_payload(album_tree)
    album_nodes = _album_nodes(album_tree)
    endpoint_rows.append(
        {
            "接口": "专辑树",
            "结果": "可用" if album_nodes else "未拿到专辑",
            "说明": f"发现 {len(album_nodes)} 个专辑/文件夹节点。" if album_nodes else "未发现可用专辑节点。",
        }
    )

    album_id = _first_album_id(album_nodes)
    materials_payload: dict[str, Any] = {}
    materials: list[dict[str, Any]] = []
    if album_id:
        materials_payload = client.get_album_material_list(album_id=album_id, page=1, page_size=sample_limit)
        external_api_calls += 1
        raw["endpoint_results"]["album_material_list"] = _sanitized_payload(materials_payload)
        materials = _material_rows(materials_payload)[:sample_limit]
    endpoint_rows.append(
        {
            "接口": "专辑素材列表",
            "结果": "可用" if materials else "未拿到素材样本",
            "说明": f"分页读取 {len(materials)} 条素材样本。" if materials else "素材列表为空或字段结构待确认。",
        }
    )

    first_material_id = _material_id(materials[0]) if materials else ""
    detail_payload: dict[str, Any] = {}
    if first_material_id:
        detail_payload = client.get_material_detail(material_id=first_material_id)
        external_api_calls += 1
        raw["endpoint_results"]["material_detail"] = _sanitized_payload(detail_payload)
    endpoint_rows.append(
        {
            "接口": "素材详情",
            "结果": "可用" if _dict(detail_payload.get("data")) or _dict(detail_payload.get("result")) else "待继续核验",
            "说明": "已读取首个素材详情。" if detail_payload else "没有素材 ID，未读取详情。",
        }
    )

    report_payload: dict[str, Any] = {}
    if first_material_id:
        date_to = datetime.now().date()
        date_from = date_to - timedelta(days=7)
        report_payload = client.get_material_report(
            material_ids=[first_material_id],
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            metrics=REPORT_METRICS,
        )
        external_api_calls += 1
        raw["endpoint_results"]["material_report"] = _sanitized_payload(report_payload)
    report_ok = _report_has_metrics(report_payload)
    endpoint_rows.append(
        {
            "接口": "素材报表",
            "结果": "可用" if report_ok else "待继续核验",
            "说明": "已按素材和日期读取指标。" if report_ok else "报表为空或指标字段待确认。",
        }
    )

    upload_status_payload = client.get_upload_material_status(task_id=UPLOAD_STATUS_PROBE_TASK_ID)
    external_api_calls += 1
    raw["endpoint_results"]["upload_material_status"] = _sanitized_payload(upload_status_payload)
    endpoint_rows.append(
        {
            "接口": "上传任务状态",
            "结果": "接口存在" if isinstance(upload_status_payload, dict) else "待继续核验",
            "说明": "使用假 task_id 只读查询；未上传素材。" if isinstance(upload_status_payload, dict) else "需要真实 task_id 后验证。",
        }
    )

    if not materials:
        warnings.append("没有拿到素材样本，字段核验只能停留在文档层。")
    field_rows = _field_rows_from_probe(materials, detail_payload, report_payload, upload_status_payload)
    sample_rows = [_sample_material_row(material) for material in materials]
    return {
        "warnings": warnings,
        "endpoint_rows": endpoint_rows,
        "field_rows": field_rows,
        "sample_rows": sample_rows,
        "raw": raw,
        "external_api_calls": external_api_calls,
    }


def _local_contract_field_rows() -> list[dict[str, Any]]:
    return [
        _field_row("素材唯一标识", "待外部只读确认", "文档使用引力素材 ID。", "同步入库前必须确认真实字段名。"),
        _field_row("MD5 跨系统匹配", "待外部只读确认", "文档使用 file_md5 / signature。", "没有 MD5 的素材不能进入创建选材。"),
        _field_row("专辑和文件夹", "待外部只读确认", "文档使用 album_id / folder_id / album_name / folder_name。", "无法确认时不开放产品绑定。"),
        _field_row("素材状态", "待外部只读确认", "文档写 1=可用，2=禁用。", "无法确认时不自动使用素材。"),
        _field_row("拒审字段", "待外部只读确认", "文档写巨量/腾讯拒审次数。", "缺失时按未知处理。"),
        _field_row("素材报表", "待外部只读确认", "文档写可按素材和日期查询。", "无法确认时不写指标汇总。"),
        _field_row("上传任务状态", "待外部只读确认", "文档写 task_id 状态轮询。", "只读阶段不上传素材。"),
    ]


def _field_rows_from_probe(
    materials: list[dict[str, Any]],
    detail_payload: dict[str, Any],
    report_payload: dict[str, Any],
    upload_status_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    detail = _dict(detail_payload.get("data")) or _dict(detail_payload.get("result"))
    sample_pool = [*materials, detail]
    return [
        _field_row(
            "素材唯一标识",
            "已确认引力素材 ID" if any(_material_id(item) for item in sample_pool) else "未确认",
            "样本里存在 material_id / id。",
            "没有素材 ID 的样本不会入库。",
        ),
        _field_row(
            "MD5 跨系统匹配",
            "已确认 file_md5" if any(_material_md5(item) for item in sample_pool) else "未确认",
            "样本里存在 file_md5 / md5 / signature。",
            "没有 MD5 的素材不能匹配巨量账户素材。",
        ),
        _field_row(
            "专辑和文件夹",
            "已确认专辑/文件夹字段" if any(_text(item.get("album_name")) or _text(item.get("folder_name")) for item in sample_pool) else "未确认",
            "样本里存在 album_name / folder_name。",
            "无法确认时不开放产品-专辑绑定。",
        ),
        _field_row(
            "素材状态",
            _status_conclusion(materials),
            f"样本状态值：{', '.join(_status_values(materials)) or '无'}。",
            "未知状态不按可用处理。",
        ),
        _field_row(
            "拒审字段",
            _refuse_conclusion(materials),
            "检查 refuse_reason_ocean / refuse_reason_tencent。",
            "缺失时按未知处理，不当成 0 次拒审。",
        ),
        _field_row(
            "素材报表",
            "已确认可按素材和日期查询" if _report_has_metrics(report_payload) else "未确认",
            "检查 AdCost / AdShow / AdClick / AdConvert。",
            "无法确认时不写表现汇总。",
        ),
        _field_row(
            "上传任务状态",
            "接口可只读查询；本次未上传素材" if isinstance(upload_status_payload, dict) else "需要真实 task_id 后验证",
            "使用假 task_id 查询状态接口。",
            "不会为了验证而上传素材。",
        ),
    ]


def _field_row(item: str, conclusion: str, evidence: str, risk: str) -> dict[str, str]:
    return {"核验项": item, "系统结论": conclusion, "依据": evidence, "风险处理": risk}


def _album_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    roots = data if isinstance(data, list) else data.get("list") if isinstance(data, dict) and isinstance(data.get("list"), list) else []
    nodes: list[dict[str, Any]] = []

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        nodes.append(node)
        children = node.get("children")
        if isinstance(children, list):
            for child in children:
                visit(child)

    for root in roots:
        visit(root)
    return nodes


def _first_album_id(nodes: list[dict[str, Any]]) -> str:
    for node in nodes:
        value = _text(node.get("id") or node.get("album_id"))
        if value:
            return value
    return ""


def _material_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    candidates: Any = []
    if isinstance(data, dict):
        candidates = data.get("list") or data.get("rows") or data.get("items") or data.get("records") or []
    elif isinstance(data, list):
        candidates = data
    return [item for item in candidates if isinstance(item, dict)]


def _material_id(material: dict[str, Any]) -> str:
    return _text(material.get("material_id") or material.get("id") or material.get("素材ID"))


def _material_md5(material: dict[str, Any]) -> str:
    return _text(material.get("file_md5") or material.get("md5") or material.get("signature") or material.get("素材MD5"))


def _sample_material_row(material: dict[str, Any]) -> dict[str, str]:
    refuse_fields = []
    if "refuse_reason_ocean" in material:
        refuse_fields.append(f"巨量：{material.get('refuse_reason_ocean')}")
    if "refuse_reason_tencent" in material:
        refuse_fields.append(f"腾讯：{material.get('refuse_reason_tencent')}")
    return {
        "素材 ID": _material_id(material),
        "素材名称": _text(material.get("name") or material.get("material_name")),
        "MD5": _material_md5(material),
        "专辑": _text(material.get("album_name")),
        "文件夹": _text(material.get("folder_name")),
        "状态": _text(material.get("status")),
        "拒审字段": "；".join(refuse_fields) if refuse_fields else "缺失",
    }


def _status_values(materials: list[dict[str, Any]]) -> list[str]:
    values = sorted({_text(item.get("status")) for item in materials if _text(item.get("status"))})
    return values


def _status_conclusion(materials: list[dict[str, Any]]) -> str:
    values = set(_status_values(materials))
    if {"1", "2"}.issubset(values):
        return "已看到 1=可用，2=禁用"
    if "1" in values:
        return "只看到 1，可用值已确认，禁用值待继续核验"
    if "2" in values:
        return "只看到 2，禁用值已确认，可用值待继续核验"
    return "未确认"


def _refuse_conclusion(materials: list[dict[str, Any]]) -> str:
    if not materials:
        return "未确认"
    present_count = sum(1 for item in materials if "refuse_reason_ocean" in item or "refuse_reason_tencent" in item)
    if present_count == len(materials):
        return "已确认每个样本都有拒审字段"
    if present_count:
        return "部分素材缺失，缺失按未知处理"
    return "未确认"


def _report_has_metrics(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    rows: list[Any] = []
    if isinstance(data, dict):
        rows = data.get("list") or data.get("rows") or data.get("items") or []
    elif isinstance(data, list):
        rows = data
    return any(isinstance(row, dict) and any(metric in row for metric in REPORT_METRICS) for row in rows)


def _sanitized_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {key: _sanitized_payload(value) for key, value in payload.items() if key not in {"jwt_token", "Authorization", "access_token"}}
    if isinstance(payload, list):
        return [_sanitized_payload(item) for item in payload]
    return payload


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_scope(value: str) -> str:
    text = str(value or "").strip()
    return text if text in PROBE_SCOPE_LABELS else "local_contract"


def _normalize_sample_limit(value: int | str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 3
    return min(5, max(1, parsed))


def _summary_text(*, ok: bool, auth_path: Path, missing_fields: list[str], scope: str, calls: int) -> str:
    if ok:
        if scope == "readonly_api":
            return f"引力素材库外部只读探测已完成：访问 {calls} 个只读接口；未上传素材、未创建广告、未修改投放。"
        return f"引力素材库本地鉴权与文档字段核验已完成：{auth_path} 可读取；未访问外部接口，未执行上传、创建或改投放动作。"
    if missing_fields:
        return f"引力素材库本地鉴权探测被阻止：缺少 {', '.join(missing_fields)}。"
    return f"引力素材库本地鉴权探测被阻止：未找到 {auth_path}。"
