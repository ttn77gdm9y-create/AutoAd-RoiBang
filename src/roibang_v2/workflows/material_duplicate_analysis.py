from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from roibang_v2.runs import write_run_artifact


@dataclass(frozen=True)
class MaterialProfile:
    material_id: str
    material_kind: str
    name: str
    video_id: str
    duration: float
    signature: str
    stat_cost_all_history: float


@dataclass(frozen=True)
class DuplicateCandidate:
    duplicate_group_key: str
    material: MaterialProfile
    duplicate_rule: str
    confidence_label: str
    confidence_score: float
    reason: dict[str, Any]


def _config(request: dict[str, Any]) -> dict[str, Any]:
    value = request.get("material_duplicate_analysis")
    return dict(value) if isinstance(value, dict) else dict(request)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rules(cfg: dict[str, Any]) -> list[str]:
    values = cfg.get("rules")
    if values is None:
        return ["signature"]
    if not isinstance(values, list) or not values:
        raise ValueError("material_duplicate_analysis.rules must be a non-empty list")
    allowed = {"signature", "name_duration"}
    rules: list[str] = []
    for value in values:
        rule = str(value).strip()
        if rule not in allowed:
            raise ValueError(f"unsupported material duplicate analysis rule: {rule}")
        rules.append(rule)
    return rules


def _min_group_size(cfg: dict[str, Any]) -> int:
    value = int(cfg.get("min_group_size", 2))
    if value < 2:
        raise ValueError("material_duplicate_analysis.min_group_size must be at least 2")
    return value


def _duration_tolerance_seconds(cfg: dict[str, Any]) -> float:
    value = float(cfg.get("duration_tolerance_seconds", 0.25))
    if value < 0:
        raise ValueError("material_duplicate_analysis.duration_tolerance_seconds must be non-negative")
    return value


def _payload(row: str) -> dict[str, Any]:
    try:
        data = json.loads(row or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _signature(payload: dict[str, Any]) -> str:
    return _first_text(
        payload,
        "signature",
        "md5",
        "material_signature",
        "file_signature",
        "video_signature",
        "content_signature",
    )


_EXTENSION_RE = re.compile(r"\.(mp4|mov|m4v|avi|webm|mkv|jpg|jpeg|png|webp)$", re.IGNORECASE)
_NAME_SEPARATORS_RE = re.compile(r"[\s_\-—–.()（）\[\]【】]+")


def _normalized_name(name: str) -> str:
    text = _EXTENSION_RE.sub("", name.strip().lower())
    text = _NAME_SEPARATORS_RE.sub("", text)
    return text


def _load_profiles(conn: sqlite3.Connection) -> list[MaterialProfile]:
    cost_rows = conn.execute(
        """
        SELECT material_id, ROUND(COALESCE(SUM(stat_cost), 0), 4)
        FROM material_metric_rollups
        WHERE window_key = 'all_history'
        GROUP BY material_id
        """
    ).fetchall()
    cost_by_material = {str(material_id): float(cost or 0) for material_id, cost in cost_rows}
    rows = conn.execute(
        """
        SELECT material_id, material_kind, name, video_id, duration, payload_json
        FROM material_profiles
        WHERE TRIM(material_id) != ''
        ORDER BY material_id
        """
    ).fetchall()
    profiles: list[MaterialProfile] = []
    for material_id, material_kind, name, video_id, duration, payload_json in rows:
        material_id_text = str(material_id or "").strip()
        payload = _payload(str(payload_json or "{}"))
        profiles.append(
            MaterialProfile(
                material_id=material_id_text,
                material_kind=str(material_kind or "video").strip() or "video",
                name=str(name or "").strip(),
                video_id=str(video_id or "").strip(),
                duration=float(duration or 0),
                signature=_signature(payload),
                stat_cost_all_history=cost_by_material.get(material_id_text, 0.0),
            )
        )
    return profiles


def _signature_candidates(
    profiles: list[MaterialProfile],
    *,
    min_group_size: int,
) -> list[DuplicateCandidate]:
    grouped: dict[str, list[MaterialProfile]] = defaultdict(list)
    for profile in profiles:
        if profile.signature:
            grouped[profile.signature].append(profile)
    candidates: list[DuplicateCandidate] = []
    for signature, materials in grouped.items():
        if len(materials) < min_group_size:
            continue
        group_key = f"signature:{signature}"
        for material in materials:
            candidates.append(
                DuplicateCandidate(
                    duplicate_group_key=group_key,
                    material=material,
                    duplicate_rule="signature",
                    confidence_label="high",
                    confidence_score=0.95,
                    reason={"signature": signature, "group_size": len(materials)},
                )
            )
    return candidates


def _name_duration_candidates(
    profiles: list[MaterialProfile],
    *,
    min_group_size: int,
    duration_tolerance_seconds: float,
) -> list[DuplicateCandidate]:
    grouped: dict[str, list[MaterialProfile]] = defaultdict(list)
    for profile in profiles:
        name_key = _normalized_name(profile.name)
        if name_key and profile.duration > 0:
            grouped[name_key].append(profile)

    candidates: list[DuplicateCandidate] = []
    for name_key, materials in grouped.items():
        sorted_materials = sorted(materials, key=lambda item: (item.duration, item.material_id))
        clusters: list[list[MaterialProfile]] = []
        for material in sorted_materials:
            placed = False
            for cluster in clusters:
                anchor = cluster[0].duration
                if abs(material.duration - anchor) <= duration_tolerance_seconds:
                    cluster.append(material)
                    placed = True
                    break
            if not placed:
                clusters.append([material])
        for cluster in clusters:
            if len(cluster) < min_group_size:
                continue
            anchor = cluster[0].duration
            group_key = f"name_duration:{name_key}:{anchor:.2f}"
            for material in cluster:
                candidates.append(
                    DuplicateCandidate(
                        duplicate_group_key=group_key,
                        material=material,
                        duplicate_rule="name_duration",
                        confidence_label="medium",
                        confidence_score=0.65,
                        reason={
                            "normalized_name": name_key,
                            "duration_anchor": round(anchor, 4),
                            "duration_tolerance_seconds": duration_tolerance_seconds,
                            "group_size": len(cluster),
                        },
                    )
                )
    return candidates


def build_material_duplicate_candidates(
    request: dict[str, Any],
    *,
    db_path: str | Path,
) -> list[DuplicateCandidate]:
    cfg = _config(request)
    rules = _rules(cfg)
    min_group_size = _min_group_size(cfg)
    duration_tolerance_seconds = _duration_tolerance_seconds(cfg)
    with sqlite3.connect(db_path) as conn:
        profiles = _load_profiles(conn)

    candidates: list[DuplicateCandidate] = []
    if "signature" in rules:
        candidates.extend(_signature_candidates(profiles, min_group_size=min_group_size))
    if "name_duration" in rules:
        candidates.extend(
            _name_duration_candidates(
                profiles,
                min_group_size=min_group_size,
                duration_tolerance_seconds=duration_tolerance_seconds,
            )
        )
    return sorted(candidates, key=lambda item: (item.duplicate_group_key, item.material.material_id))


def _write_candidates(
    *,
    conn: sqlite3.Connection,
    candidates: list[DuplicateCandidate],
    source: str,
    synced_at: str,
) -> int:
    conn.execute("DELETE FROM material_duplicate_candidates")
    for candidate in candidates:
        material = candidate.material
        conn.execute(
            """
            INSERT INTO material_duplicate_candidates (
              duplicate_group_key, material_id, duplicate_rule,
              confidence_label, confidence_score, signature, video_id,
              material_kind, name, duration, stat_cost_all_history,
              reason_json, source, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(duplicate_group_key, material_id) DO UPDATE SET
              duplicate_rule=excluded.duplicate_rule,
              confidence_label=excluded.confidence_label,
              confidence_score=excluded.confidence_score,
              signature=excluded.signature,
              video_id=excluded.video_id,
              material_kind=excluded.material_kind,
              name=excluded.name,
              duration=excluded.duration,
              stat_cost_all_history=excluded.stat_cost_all_history,
              reason_json=excluded.reason_json,
              source=excluded.source,
              synced_at=excluded.synced_at
            """,
            (
                candidate.duplicate_group_key,
                material.material_id,
                candidate.duplicate_rule,
                candidate.confidence_label,
                candidate.confidence_score,
                material.signature,
                material.video_id,
                material.material_kind,
                material.name,
                material.duration,
                material.stat_cost_all_history,
                json.dumps(candidate.reason, ensure_ascii=False, sort_keys=True),
                source,
                synced_at,
            ),
        )
    return len(candidates)


def run_material_duplicate_analysis_request(
    request: dict[str, Any],
    *,
    db_path: str | Path,
    runs_dir: str | Path,
) -> dict[str, Any]:
    cfg = _config(request)
    rules = _rules(cfg)
    candidates = build_material_duplicate_candidates(request, db_path=db_path)
    synced_at = _utc_now()
    with sqlite3.connect(db_path) as conn:
        profile_count = int(conn.execute("SELECT COUNT(*) FROM material_profiles").fetchone()[0] or 0)
        material_count = int(
            conn.execute("SELECT COUNT(DISTINCT material_id) FROM material_profiles").fetchone()[0] or 0
        )
        rows_written = _write_candidates(
            conn=conn,
            candidates=candidates,
            source="material_duplicate_analysis",
            synced_at=synced_at,
        )

    duplicate_groups = {candidate.duplicate_group_key for candidate in candidates}
    duplicate_materials = {candidate.material.material_id for candidate in candidates}
    payload = {
        "ok": True,
        "workflow": "material_duplicate_analysis",
        "phase": "phase1",
        "execution_enabled": False,
        "external_api_calls": 0,
        "summary": {
            "profile_count": profile_count,
            "material_count": material_count,
            "duplicate_group_count": len(duplicate_groups),
            "duplicate_material_count": len(duplicate_materials),
            "rows_written": rows_written,
            "rules": rules,
        },
        "guardrails": {
            "external_api_calls": 0,
            "business_actions": [],
            "writes": ["material_duplicate_candidates", "run_artifact"],
            "main_metric_tables_unchanged": True,
        },
    }
    artifact_path = write_run_artifact(runs_dir, "material_duplicate_analysis", payload)
    payload["artifact_path"] = str(artifact_path)
    return payload
