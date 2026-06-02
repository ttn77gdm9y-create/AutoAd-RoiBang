from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.services.artifacts import read_json
from roibang_v2.workflows.product_automation_job import load_product_configs


@dataclass(frozen=True)
class RealtimeSnapshot:
    payload: dict[str, Any]
    path: Path | None
    scope: dict[str, Any]
    warnings: list[str]
    required: bool


def _text(value: Any) -> str:
    return str(value or "").strip()


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _number(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "").replace("%", ""))
    except ValueError:
        return 0.0


def _product(configs_dir: str | Path, product_key: str) -> dict[str, Any]:
    if not product_key:
        return {}
    products = load_product_configs(Path(configs_dir) / "products", product_key=product_key)
    return products[0] if products else {}


def _delivery_scopes(product: dict[str, Any]) -> list[dict[str, Any]]:
    automation = product.get("automation") if isinstance(product.get("automation"), dict) else {}
    patrol = automation.get("delivery_patrol") if isinstance(automation.get("delivery_patrol"), dict) else {}
    return _rows(patrol.get("account_scopes"))


def realtime_scope_for_product(configs_dir: str | Path, product_key: str, *, purpose: str) -> dict[str, Any]:
    product = _product(configs_dir, product_key)
    scopes = _delivery_scopes(product)
    if purpose == "dashboard":
        for scope in scopes:
            if _text(scope.get("account_name_contains")):
                return {**scope, "_product_key": product_key}
    if purpose == "suggestions":
        for scope in scopes:
            if _text(scope.get("account_remark_equals")):
                return {**scope, "_product_key": product_key}
    return {}


def default_realtime_product_key(configs_dir: str | Path, *, purpose: str) -> str:
    products = load_product_configs(Path(configs_dir) / "products")
    if purpose == "dashboard":
        products = _prefer_local_product_configs(products)
    for product in products:
        product_key = _text(product.get("product_key"))
        if product_key and realtime_scope_for_product(configs_dir, product_key, purpose=purpose):
            return product_key
    return ""


def realtime_scope_required(configs_dir: str | Path, product_key: str, *, purpose: str) -> bool:
    return bool(realtime_scope_for_product(configs_dir, product_key, purpose=purpose))


def _prefer_local_product_configs(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    local = [product for product in products if ".example." not in _text(product.get("_config_path"))]
    return local or products


def _account_scope(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    scope = summary.get("account_scope") if isinstance(summary.get("account_scope"), dict) else {}
    return dict(scope)


def _scope_matches(payload: dict[str, Any], scope: dict[str, Any]) -> bool:
    if not scope:
        return False
    actual = _account_scope(payload)
    expected_remark = _text(scope.get("account_remark_equals"))
    expected_name = _text(scope.get("account_name_contains"))
    if expected_remark:
        return _text(actual.get("account_remark_equals")) == expected_remark
    if expected_name:
        return _text(actual.get("account_name_contains")) == expected_name
    return False


def _resolve_path(project_root: str | Path, value: Any) -> Path | None:
    text = _text(value)
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path if path.exists() else None
    root = Path(project_root)
    for candidate in [root / path, path]:
        if candidate.exists():
            return candidate
    return None


def _product_job_patrol_payloads(project_root: str | Path, runs_dir: str | Path) -> list[tuple[Path, dict[str, Any]]]:
    directory = Path(runs_dir) / "product_automation_job_delivery_patrol"
    if not directory.exists():
        return []
    rows: list[tuple[Path, dict[str, Any]]] = []
    candidates = sorted([path for path in directory.glob("*.json") if path.name != "latest.json"], reverse=True)
    latest = directory / "latest.json"
    if latest.exists():
        candidates.insert(0, latest)
    for path in candidates[:120]:
        payload = read_json(path)
        for result in _rows(payload.get("results")):
            parsed = result.get("parsed_stdout") if isinstance(result.get("parsed_stdout"), dict) else {}
            artifact_path = _resolve_path(project_root, parsed.get("artifact_path"))
            if artifact_path:
                patrol = read_json(artifact_path)
                if patrol:
                    rows.append((artifact_path, patrol))
                    continue
            if _text(parsed.get("workflow")) == "delivery_patrol":
                rows.append((path, dict(parsed)))
    return rows


def _direct_patrol_payloads(runs_dir: str | Path) -> list[tuple[Path, dict[str, Any]]]:
    directory = Path(runs_dir) / "delivery_patrol"
    if not directory.exists():
        return []
    candidates = sorted([path for path in directory.glob("*.json") if path.name != "latest.json"], reverse=True)
    latest = directory / "latest.json"
    if latest.exists():
        candidates.insert(0, latest)
    return [(path, read_json(path)) for path in candidates[:120]]


def _generated_at(path: Path | None, payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for value in [payload.get("generated_at"), payload.get("created_at"), summary.get("generated_at"), summary.get("created_at")]:
        text = _text(value)
        if text:
            return text
    if not path:
        return ""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return ""


def _spent_account_ids(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for account in _rows(payload.get("accounts")):
        metrics = account.get("metrics") if isinstance(account.get("metrics"), dict) else {}
        today = metrics.get("today") if isinstance(metrics.get("today"), dict) else {}
        if _number(today.get("stat_cost")) > 0:
            advertiser_id = _text(account.get("advertiser_id") or account.get("account_id"))
            if advertiser_id:
                ids.add(advertiser_id)
    return ids


def _filter_to_spent_accounts(payload: dict[str, Any]) -> dict[str, Any]:
    spent_ids = _spent_account_ids(payload)
    if not spent_ids:
        filtered = {**payload, "accounts": [], "projects": [], "promotions": []}
    else:
        filtered = {
            **payload,
            "accounts": [
                account
                for account in _rows(payload.get("accounts"))
                if _text(account.get("advertiser_id") or account.get("account_id")) in spent_ids
            ],
            "projects": [
                project
                for project in _rows(payload.get("projects"))
                if _text(project.get("advertiser_id") or project.get("account_id")) in spent_ids
            ],
            "promotions": [
                promotion
                for promotion in _rows(payload.get("promotions"))
                if _text(promotion.get("advertiser_id") or promotion.get("account_id")) in spent_ids
            ],
        }
    summary = filtered.get("summary") if isinstance(filtered.get("summary"), dict) else {}
    filtered["summary"] = {**summary, "realtime_spent_account_count": len(spent_ids)}
    filtered["realtime_spent_account_ids"] = sorted(spent_ids)
    return filtered


def _snapshot_warnings(scope: dict[str, Any], payload: dict[str, Any], path: Path | None) -> list[str]:
    warnings: list[str] = []
    scope_title = _text(scope.get("title")) or _scope_label(scope)
    if scope_title:
        warnings.append(f"当前读取实时数据范围：{scope_title}。")
    generated_at = _generated_at(path, payload)
    if generated_at:
        warnings.append(f"实时快照生成时间：{generated_at}。")
    if not _spent_account_ids(payload):
        warnings.append("该实时快照中没有今日有消耗账户，首页和建议不会用其它范围数据冒充。")
    return warnings


def _missing_warning(scope: dict[str, Any], *, purpose: str) -> str:
    label = _scope_label(scope) or "产品级实时快照"
    if purpose == "dashboard":
        return f"未找到首页所需的实时数据范围：{label}；不会用其它 latest 或专项口径冒充。"
    return f"未找到建议所需的实时数据范围：{label}；不会基于历史数据单独生成可执行建议。"


def _scope_label(scope: dict[str, Any]) -> str:
    if _text(scope.get("title")):
        return _text(scope.get("title"))
    if _text(scope.get("account_name_contains")):
        return f"账户名包含“{_text(scope.get('account_name_contains'))}”"
    if _text(scope.get("account_remark_equals")):
        return f"账户备注等于“{_text(scope.get('account_remark_equals'))}”"
    return ""


def find_realtime_patrol_snapshot(
    *,
    project_root: str | Path,
    configs_dir: str | Path,
    runs_dir: str | Path,
    product_key: str,
    purpose: str,
) -> RealtimeSnapshot:
    scope = realtime_scope_for_product(configs_dir, product_key, purpose=purpose)
    if not scope:
        return RealtimeSnapshot(payload={}, path=None, scope={}, warnings=[], required=False)

    for path, payload in [*_product_job_patrol_payloads(project_root, runs_dir), *_direct_patrol_payloads(runs_dir)]:
        if payload and _scope_matches(payload, scope):
            filtered = _filter_to_spent_accounts(payload)
            return RealtimeSnapshot(
                payload=filtered,
                path=path,
                scope=scope,
                warnings=_snapshot_warnings(scope, filtered, path),
                required=True,
            )
    return RealtimeSnapshot(
        payload={},
        path=None,
        scope=scope,
        warnings=[_missing_warning(scope, purpose=purpose)],
        required=True,
    )


def linked_suggestions_artifact(project_root: str | Path, patrol_payload: dict[str, Any]) -> Path | None:
    summary = patrol_payload.get("summary") if isinstance(patrol_payload.get("summary"), dict) else {}
    embedded = patrol_payload.get("delivery_patrol_suggestions") if isinstance(patrol_payload.get("delivery_patrol_suggestions"), dict) else {}
    for value in [summary.get("suggestion_artifact_path"), patrol_payload.get("suggestion_artifact_path"), embedded.get("artifact_path")]:
        path = _resolve_path(project_root, value)
        if path:
            return path
    return None


def realtime_account_ids(snapshot: RealtimeSnapshot) -> list[str]:
    return [str(item) for item in snapshot.payload.get("realtime_spent_account_ids", []) if _text(item)]


def realtime_account_names(snapshot: RealtimeSnapshot) -> dict[str, str]:
    names: dict[str, str] = {}
    for account in _rows(snapshot.payload.get("accounts")):
        advertiser_id = _text(account.get("advertiser_id") or account.get("account_id"))
        account_name = _text(account.get("account_name") or account.get("advertiser_name"))
        if advertiser_id and account_name:
            names[advertiser_id] = account_name
    return names
