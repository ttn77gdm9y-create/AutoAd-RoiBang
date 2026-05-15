from __future__ import annotations

import sqlite3
from pathlib import Path


def bootstrap_database(database_path: str | Path) -> None:
    db_path = Path(database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).with_name("schema.sql")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.execute("DROP TABLE IF EXISTS product_source_material_candidates")
        _ensure_column(conn, "material_profiles", "canonical_material_key", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "material_metric_rollups", "canonical_material_key", "TEXT NOT NULL DEFAULT ''")
        for column, definition in {
            "signature": "TEXT NOT NULL DEFAULT ''",
            "duration": "REAL NOT NULL DEFAULT 0",
            "file_size": "REAL NOT NULL DEFAULT 0",
            "create_time": "TEXT NOT NULL DEFAULT ''",
            "tag_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
            "first_seen_at": "TEXT NOT NULL DEFAULT ''",
            "last_seen_at": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(conn, "product_source_materials", column, definition)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_profiles_canonical
              ON material_profiles (canonical_material_key)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS material_profile_lookup_failures (
              material_id TEXT NOT NULL,
              account_id TEXT NOT NULL DEFAULT '',
              endpoint_key TEXT NOT NULL DEFAULT '',
              reason TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'failed',
              fail_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT NOT NULL DEFAULT '',
              request_json TEXT NOT NULL DEFAULT '{}',
              first_failed_at TEXT NOT NULL,
              last_failed_at TEXT NOT NULL,
              PRIMARY KEY (material_id, account_id, endpoint_key, reason)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_profile_lookup_failures_status
              ON material_profile_lookup_failures (status, endpoint_key, account_id, last_failed_at DESC)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS material_duplicate_candidates (
              duplicate_group_key TEXT NOT NULL,
              material_id TEXT NOT NULL,
              duplicate_rule TEXT NOT NULL,
              confidence_label TEXT NOT NULL DEFAULT '',
              confidence_score REAL NOT NULL DEFAULT 0,
              signature TEXT NOT NULL DEFAULT '',
              video_id TEXT NOT NULL DEFAULT '',
              material_kind TEXT NOT NULL DEFAULT 'video',
              name TEXT NOT NULL DEFAULT '',
              duration REAL NOT NULL DEFAULT 0,
              stat_cost_all_history REAL NOT NULL DEFAULT 0,
              reason_json TEXT NOT NULL DEFAULT '{}',
              source TEXT NOT NULL,
              synced_at TEXT NOT NULL,
              PRIMARY KEY (duplicate_group_key, material_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_duplicate_candidates_material
              ON material_duplicate_candidates (material_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_duplicate_candidates_rule
              ON material_duplicate_candidates (duplicate_rule, confidence_score DESC)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS material_attribute_snapshots (
              material_id TEXT NOT NULL,
              account_id TEXT NOT NULL DEFAULT '',
              account_type TEXT NOT NULL DEFAULT 'AD',
              is_ad_high_quality_material INTEGER NOT NULL DEFAULT 0,
              is_ad_low_quality_material INTEGER NOT NULL DEFAULT 0,
              is_ecp_high_quality_material INTEGER NOT NULL DEFAULT 0,
              is_ecp_low_quality_material INTEGER NOT NULL DEFAULT 0,
              is_local_high_quality_material INTEGER NOT NULL DEFAULT 0,
              is_local_low_quality_material INTEGER NOT NULL DEFAULT 0,
              is_first_publish_material INTEGER NOT NULL DEFAULT 0,
              is_inefficient_material INTEGER NOT NULL DEFAULT 0,
              is_carry_material INTEGER NOT NULL DEFAULT 0,
              is_similar_material INTEGER NOT NULL DEFAULT 0,
              is_similar_queue_material INTEGER NOT NULL DEFAULT 0,
              is_similar_expected_queue_material INTEGER NOT NULL DEFAULT 0,
              ad_low_quality_suggestions_json TEXT NOT NULL DEFAULT '[]',
              ecp_low_quality_suggestions_json TEXT NOT NULL DEFAULT '[]',
              local_low_quality_suggestions_json TEXT NOT NULL DEFAULT '[]',
              attributes_modify_time TEXT NOT NULL DEFAULT '',
              payload_json TEXT NOT NULL DEFAULT '{}',
              source TEXT NOT NULL,
              synced_at TEXT NOT NULL,
              PRIMARY KEY (material_id, account_id, account_type)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_attribute_snapshots_flags
              ON material_attribute_snapshots (
                is_ad_low_quality_material,
                is_inefficient_material,
                is_similar_material,
                is_carry_material,
                synced_at DESC
              )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS product_source_material_metric_rollups (
              product TEXT NOT NULL,
              source_advertiser_id TEXT NOT NULL,
              organization_id TEXT NOT NULL DEFAULT '',
              window_key TEXT NOT NULL,
              window_days INTEGER NOT NULL DEFAULT 0,
              period_start TEXT NOT NULL,
              period_end TEXT NOT NULL,
              material_id TEXT NOT NULL,
              material_type TEXT NOT NULL DEFAULT 'video',
              source_video_id TEXT NOT NULL DEFAULT '',
              name TEXT NOT NULL DEFAULT '',
              review_status TEXT NOT NULL DEFAULT '',
              signature TEXT NOT NULL DEFAULT '',
              duration REAL NOT NULL DEFAULT 0,
              file_size REAL NOT NULL DEFAULT 0,
              create_time TEXT NOT NULL DEFAULT '',
              first_seen_metric_date TEXT NOT NULL DEFAULT '',
              effective_create_date TEXT NOT NULL DEFAULT '',
              effective_create_date_source TEXT NOT NULL DEFAULT '',
              tag_ids_json TEXT NOT NULL DEFAULT '[]',
              account_count INTEGER NOT NULL DEFAULT 0,
              project_count INTEGER NOT NULL DEFAULT 0,
              promotion_count INTEGER NOT NULL DEFAULT 0,
              stat_cost REAL NOT NULL DEFAULT 0,
              show_cnt REAL NOT NULL DEFAULT 0,
              click_cnt REAL NOT NULL DEFAULT 0,
              convert_cnt REAL NOT NULL DEFAULT 0,
              active_register REAL NOT NULL DEFAULT 0,
              roi_1day_cost_weighted REAL NOT NULL DEFAULT 0,
              roi_7days_cost_weighted REAL NOT NULL DEFAULT 0,
              source TEXT NOT NULL,
              synced_at TEXT NOT NULL,
              PRIMARY KEY (product, source_advertiser_id, window_key, period_start, period_end, material_id)
            )
            """
        )
        for column, definition in {
            "first_seen_metric_date": "TEXT NOT NULL DEFAULT ''",
            "effective_create_date": "TEXT NOT NULL DEFAULT ''",
            "effective_create_date_source": "TEXT NOT NULL DEFAULT ''",
        }.items():
            _ensure_column(conn, "product_source_material_metric_rollups", column, definition)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_source_material_active
              ON product_source_materials (product, source_advertiser_id, is_active, material_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_product_source_material_rollup_rank
              ON product_source_material_metric_rollups (product, source_advertiser_id, window_key, stat_cost DESC)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS material_source_mappings (
              product TEXT NOT NULL,
              source_advertiser_id TEXT NOT NULL,
              source_material_id TEXT NOT NULL,
              source_video_id TEXT NOT NULL DEFAULT '',
              target_advertiser_id TEXT NOT NULL,
              target_material_id TEXT NOT NULL,
              target_video_id TEXT NOT NULL DEFAULT '',
              source_workflow TEXT NOT NULL DEFAULT '',
              payload_json TEXT NOT NULL DEFAULT '{}',
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              PRIMARY KEY (product, source_advertiser_id, target_advertiser_id, target_material_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_source_mappings_source
              ON material_source_mappings (product, source_advertiser_id, source_material_id)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_material_source_mappings_target
              ON material_source_mappings (target_advertiser_id, target_material_id)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS create_requests (
              request_id TEXT PRIMARY KEY,
              phase TEXT NOT NULL,
              execution_enabled INTEGER NOT NULL,
              request_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS create_strategy_plans (
              plan_id TEXT PRIMARY KEY,
              request_id TEXT NOT NULL,
              phase TEXT NOT NULL,
              execution_enabled INTEGER NOT NULL,
              request_json TEXT NOT NULL,
              plan_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_create_strategy_plans_request
              ON create_strategy_plans (request_id)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS create_idempotency_keys (
              idempotency_key TEXT PRIMARY KEY,
              scope TEXT NOT NULL,
              plan_id TEXT NOT NULL,
              request_id TEXT NOT NULL,
              target_date TEXT NOT NULL,
              advertiser_id TEXT NOT NULL DEFAULT '',
              project_key TEXT NOT NULL DEFAULT '',
              unit_key TEXT NOT NULL DEFAULT '',
              material_id TEXT NOT NULL DEFAULT '',
              phase TEXT NOT NULL,
              status TEXT NOT NULL,
              source_workflow TEXT NOT NULL,
              execution_enabled INTEGER NOT NULL,
              payload_json TEXT NOT NULL DEFAULT '{}',
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_create_idempotency_keys_plan
              ON create_idempotency_keys (plan_id, scope)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_create_idempotency_keys_status
              ON create_idempotency_keys (status, target_date)
            """
        )
        _ensure_provider_id_ledger_plan_scope(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS create_provider_id_ledger (
              entity_type TEXT NOT NULL,
              local_key TEXT NOT NULL,
              provider_id TEXT NOT NULL,
              plan_id TEXT NOT NULL DEFAULT '',
              request_id TEXT NOT NULL DEFAULT '',
              advertiser_id TEXT NOT NULL DEFAULT '',
              parent_local_key TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL,
              source_workflow TEXT NOT NULL,
              execution_enabled INTEGER NOT NULL,
              response_payload_json TEXT NOT NULL DEFAULT '{}',
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              PRIMARY KEY (entity_type, local_key, plan_id, request_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_create_provider_id_ledger_local_key
              ON create_provider_id_ledger (local_key)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_create_provider_id_ledger_plan
              ON create_provider_id_ledger (plan_id, entity_type)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS create_material_bind_ledger (
              bind_key TEXT PRIMARY KEY,
              source_advertiser_id TEXT NOT NULL,
              target_advertiser_ids_json TEXT NOT NULL DEFAULT '[]',
              source_video_ids_json TEXT NOT NULL DEFAULT '[]',
              provider_task_id TEXT NOT NULL DEFAULT '',
              plan_id TEXT NOT NULL DEFAULT '',
              request_id TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL,
              source_workflow TEXT NOT NULL,
              execution_enabled INTEGER NOT NULL,
              response_payload_json TEXT NOT NULL DEFAULT '{}',
              first_seen_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_create_material_bind_ledger_plan
              ON create_material_bind_ledger (plan_id, status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_create_material_bind_ledger_source
              ON create_material_bind_ledger (source_advertiser_id, status)
            """
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _primary_key_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    keyed = sorted((int(row[5]), str(row[1])) for row in rows if int(row[5] or 0) > 0)
    return tuple(name for _position, name in keyed)


def _ensure_provider_id_ledger_plan_scope(conn: sqlite3.Connection) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'create_provider_id_ledger'"
    ).fetchone()
    if not exists or _primary_key_columns(conn, "create_provider_id_ledger") == (
        "entity_type",
        "local_key",
        "plan_id",
        "request_id",
    ):
        return
    conn.execute("ALTER TABLE create_provider_id_ledger RENAME TO create_provider_id_ledger_old_pk")
    conn.execute(
        """
        CREATE TABLE create_provider_id_ledger (
          entity_type TEXT NOT NULL,
          local_key TEXT NOT NULL,
          provider_id TEXT NOT NULL,
          plan_id TEXT NOT NULL DEFAULT '',
          request_id TEXT NOT NULL DEFAULT '',
          advertiser_id TEXT NOT NULL DEFAULT '',
          parent_local_key TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL,
          source_workflow TEXT NOT NULL,
          execution_enabled INTEGER NOT NULL,
          response_payload_json TEXT NOT NULL DEFAULT '{}',
          first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          PRIMARY KEY (entity_type, local_key, plan_id, request_id)
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO create_provider_id_ledger (
          entity_type, local_key, provider_id, plan_id, request_id, advertiser_id,
          parent_local_key, status, source_workflow, execution_enabled,
          response_payload_json, first_seen_at, last_seen_at
        )
        SELECT
          entity_type, local_key, provider_id, plan_id, request_id, advertiser_id,
          parent_local_key, status, source_workflow, execution_enabled,
          response_payload_json, first_seen_at, last_seen_at
        FROM create_provider_id_ledger_old_pk
        """
    )
    conn.execute("DROP TABLE create_provider_id_ledger_old_pk")
