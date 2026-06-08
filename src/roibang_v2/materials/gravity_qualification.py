from __future__ import annotations

from typing import Any


ELIGIBLE_STATUS = "可铺货"
INELIGIBLE_STATUS = "不可用"
UPLOADED_STATUS = "已铺货"
NOT_UPLOADED_STATUS = "未铺货"


def qualify_gravity_material(row: dict[str, Any]) -> dict[str, Any]:
    reasons = _qualification_reasons(row)
    video_id = _text(row.get("video_id"))
    has_performance = any(
        _float_value(row.get(key)) > 0
        for key in ("stat_cost", "show_cnt", "click_cnt", "convert_cnt", "cost_lookback")
    )
    return {
        "qualification_status": INELIGIBLE_STATUS if reasons else ELIGIBLE_STATUS,
        "qualification_reasons": reasons,
        "qualification_reason": "；".join(reasons),
        "is_eligible_for_next_step": not reasons,
        "upload_status": UPLOADED_STATUS if video_id else NOT_UPLOADED_STATUS,
        "is_uploaded": bool(video_id),
        "has_performance": has_performance,
    }


def qualification_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    qualified = [_with_qualification(row) for row in rows]
    return {
        "material_count": len(qualified),
        "eligible_count": sum(1 for row in qualified if row["is_eligible_for_next_step"]),
        "ineligible_count": sum(1 for row in qualified if not row["is_eligible_for_next_step"]),
        "missing_md5_count": sum(1 for row in qualified if not _text(row.get("signature"))),
        "uploaded_count": sum(1 for row in qualified if row["is_uploaded"]),
        "not_uploaded_count": sum(1 for row in qualified if not row["is_uploaded"]),
        "has_performance_count": sum(1 for row in qualified if row["has_performance"]),
    }


def matches_qualification_filter(row: dict[str, Any], status_filter: str) -> bool:
    status = _text(status_filter)
    if not status:
        return True
    qualified = _with_qualification(row)
    if status == "active":
        return int(row.get("is_active") or 0) == 1
    if status == "inactive":
        return int(row.get("is_active") or 0) == 0
    if status == "eligible":
        return bool(qualified["is_eligible_for_next_step"])
    if status == "ineligible":
        return not bool(qualified["is_eligible_for_next_step"])
    if status == "missing_md5":
        return not _text(row.get("signature"))
    if status == "uploaded":
        return bool(qualified["is_uploaded"])
    if status == "not_uploaded":
        return not bool(qualified["is_uploaded"])
    if status == "has_performance":
        return bool(qualified["has_performance"])
    return True


def _with_qualification(row: dict[str, Any]) -> dict[str, Any]:
    if "qualification_status" in row:
        return row
    return {**row, **qualify_gravity_material(row)}


def _qualification_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not _text(row.get("material_id")):
        reasons.append("缺少引力素材 ID")
    if int(row.get("is_active") or 0) != 1:
        reasons.append("本地已停用")
    status_text = _text(row.get("review_status") or row.get("gravity_status"))
    gravity_status = _text(row.get("gravity_status"))
    if _is_disabled_status(status_text, gravity_status):
        reasons.append("引力状态为禁用")
    elif any(word in status_text for word in ("拒审", "审核不通过", "不通过")):
        reasons.append("素材已拒审")
    if not _text(row.get("signature")):
        reasons.append("缺少 MD5")
    return _dedupe(reasons)


def _is_disabled_status(status_text: str, gravity_status: str) -> bool:
    lowered = status_text.lower()
    gravity_lowered = gravity_status.lower()
    if gravity_lowered == "2":
        return True
    return lowered in {"2", "disabled", "disable", "inactive", "false", "禁用", "停用"} or any(
        word in status_text for word in ("禁用", "停用")
    )


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _float_value(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", ""))
    except ValueError:
        return 0.0


def _text(value: Any) -> str:
    return str(value or "").strip()
