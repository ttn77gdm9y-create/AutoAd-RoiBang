CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow TEXT NOT NULL,
  status TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  advertiser_id TEXT PRIMARY KEY,
  name TEXT,
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_pool (
  advertiser_id TEXT PRIMARY KEY,
  account_name TEXT NOT NULL,
  product TEXT NOT NULL,
  platform TEXT NOT NULL,
  historical_spend REAL NOT NULL DEFAULT 0,
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_account_pool_product_platform
  ON account_pool (product, platform, historical_spend DESC);

CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  advertiser_id TEXT NOT NULL,
  name TEXT,
  status TEXT,
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promotions (
  promotion_id TEXT PRIMARY KEY,
  advertiser_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  name TEXT,
  status TEXT,
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materials (
  material_id TEXT PRIMARY KEY,
  name TEXT,
  material_type TEXT,
  video_id TEXT,
  review_status TEXT,
  cost_lookback REAL NOT NULL DEFAULT 0,
  score REAL NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_materials (
  advertiser_id TEXT NOT NULL,
  material_id TEXT NOT NULL,
  video_id TEXT NOT NULL DEFAULT '',
  material_type TEXT NOT NULL DEFAULT 'video',
  review_status TEXT NOT NULL DEFAULT '',
  cost_lookback REAL NOT NULL DEFAULT 0,
  score REAL NOT NULL DEFAULT 0,
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (advertiser_id, material_id),
  FOREIGN KEY (material_id) REFERENCES materials(material_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_account_materials_available
  ON account_materials (advertiser_id, material_type, review_status, cost_lookback DESC, score DESC);

CREATE TABLE IF NOT EXISTS product_source_materials (
  product TEXT NOT NULL,
  source_advertiser_id TEXT NOT NULL,
  organization_id TEXT NOT NULL DEFAULT '',
  material_id TEXT NOT NULL,
  video_id TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  material_type TEXT NOT NULL DEFAULT 'video',
  review_status TEXT NOT NULL DEFAULT '',
  signature TEXT NOT NULL DEFAULT '',
  duration REAL NOT NULL DEFAULT 0,
  file_size REAL NOT NULL DEFAULT 0,
  create_time TEXT NOT NULL DEFAULT '',
  first_seen_metric_date TEXT NOT NULL DEFAULT '',
  effective_create_date TEXT NOT NULL DEFAULT '',
  effective_create_date_source TEXT NOT NULL DEFAULT '',
  tag_ids_json TEXT NOT NULL DEFAULT '[]',
  is_active INTEGER NOT NULL DEFAULT 1,
  first_seen_at TEXT NOT NULL DEFAULT '',
  last_seen_at TEXT NOT NULL DEFAULT '',
  cost_lookback REAL NOT NULL DEFAULT 0,
  score REAL NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (product, source_advertiser_id, material_id),
  FOREIGN KEY (material_id) REFERENCES materials(material_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_product_source_material_rank
  ON product_source_materials (product, source_advertiser_id, material_type, review_status, cost_lookback DESC, score DESC);

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
);

CREATE INDEX IF NOT EXISTS idx_material_source_mappings_source
  ON material_source_mappings (product, source_advertiser_id, source_material_id);

CREATE INDEX IF NOT EXISTS idx_material_source_mappings_target
  ON material_source_mappings (target_advertiser_id, target_material_id);

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
);

CREATE INDEX IF NOT EXISTS idx_product_source_material_rollup_rank
  ON product_source_material_metric_rollups (product, source_advertiser_id, window_key, stat_cost DESC);

CREATE TABLE IF NOT EXISTS product_gravity_album_bindings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT NOT NULL,
  album_id TEXT NOT NULL,
  album_name TEXT NOT NULL,
  folder_id TEXT NOT NULL DEFAULT '',
  folder_name TEXT NOT NULL DEFAULT '',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(product, album_id, folder_id)
);

CREATE INDEX IF NOT EXISTS idx_product_gravity_album_bindings_product
  ON product_gravity_album_bindings (product, is_active, album_id, folder_id);

CREATE TABLE IF NOT EXISTS gravity_upload_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product TEXT NOT NULL DEFAULT '',
  gravity_material_id TEXT NOT NULL,
  signature TEXT NOT NULL DEFAULT '',
  target_advertiser_id TEXT NOT NULL,
  target_account_name TEXT NOT NULL DEFAULT '',
  gravity_task_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  video_id TEXT NOT NULL DEFAULT '',
  material_id_in_account TEXT NOT NULL DEFAULT '',
  fail_reason TEXT NOT NULL DEFAULT '',
  preview_artifact_path TEXT NOT NULL DEFAULT '',
  response_payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(gravity_material_id, target_advertiser_id)
);

CREATE INDEX IF NOT EXISTS idx_gravity_upload_tasks_status
  ON gravity_upload_tasks (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_gravity_upload_tasks_target
  ON gravity_upload_tasks (target_advertiser_id, status);

CREATE TABLE IF NOT EXISTS material_bindings (
  advertiser_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  promotion_id TEXT NOT NULL,
  material_kind TEXT NOT NULL,
  material_id TEXT NOT NULL,
  video_id TEXT NOT NULL DEFAULT '',
  image_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (promotion_id, material_kind, material_id)
);

CREATE TABLE IF NOT EXISTS material_metric_summaries (
  material_kind TEXT NOT NULL,
  material_id TEXT NOT NULL,
  video_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  promotion_count INTEGER NOT NULL DEFAULT 0,
  project_count INTEGER NOT NULL DEFAULT 0,
  account_count INTEGER NOT NULL DEFAULT 0,
  stat_cost REAL NOT NULL DEFAULT 0,
  active_register REAL NOT NULL DEFAULT 0,
  attribution_convert_cnt REAL NOT NULL DEFAULT 0,
  roi_1day_cost_weighted REAL NOT NULL DEFAULT 0,
  roi_7days_cost_weighted REAL NOT NULL DEFAULT 0,
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (period_start, period_end, material_kind, material_id)
);

CREATE TABLE IF NOT EXISTS material_profiles (
  material_id TEXT PRIMARY KEY,
  canonical_material_key TEXT NOT NULL DEFAULT '',
  material_kind TEXT NOT NULL DEFAULT 'video',
  name TEXT NOT NULL DEFAULT '',
  video_id TEXT NOT NULL DEFAULT '',
  review_status TEXT NOT NULL DEFAULT '',
  create_time TEXT NOT NULL DEFAULT '',
  duration REAL NOT NULL DEFAULT 0,
  cover_url TEXT NOT NULL DEFAULT '',
  source_advertiser_id TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_material_profiles_kind_status
  ON material_profiles (material_kind, review_status, synced_at DESC);

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
);

CREATE INDEX IF NOT EXISTS idx_material_profile_lookup_failures_status
  ON material_profile_lookup_failures (status, endpoint_key, account_id, last_failed_at DESC);

CREATE TABLE IF NOT EXISTS material_daily_metrics (
  metric_date TEXT NOT NULL,
  advertiser_id TEXT NOT NULL,
  project_id TEXT NOT NULL DEFAULT '',
  project_name TEXT NOT NULL DEFAULT '',
  promotion_id TEXT NOT NULL DEFAULT '',
  promotion_name TEXT NOT NULL DEFAULT '',
  material_id TEXT NOT NULL,
  material_kind TEXT NOT NULL DEFAULT 'video',
  stat_cost REAL NOT NULL DEFAULT 0,
  show_cnt REAL NOT NULL DEFAULT 0,
  click_cnt REAL NOT NULL DEFAULT 0,
  convert_cnt REAL NOT NULL DEFAULT 0,
  active_register REAL NOT NULL DEFAULT 0,
  roi_1day REAL NOT NULL DEFAULT 0,
  roi_7days REAL NOT NULL DEFAULT 0,
  metric_payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (metric_date, advertiser_id, project_id, promotion_id, material_id)
);

CREATE INDEX IF NOT EXISTS idx_material_daily_metrics_date_material
  ON material_daily_metrics (metric_date, material_id);

CREATE INDEX IF NOT EXISTS idx_material_daily_metrics_date_account
  ON material_daily_metrics (metric_date, advertiser_id, stat_cost DESC);

CREATE TABLE IF NOT EXISTS project_hourly_metrics (
  metric_date TEXT NOT NULL,
  metric_hour INTEGER NOT NULL,
  advertiser_id TEXT NOT NULL,
  project_id TEXT NOT NULL DEFAULT '',
  project_name TEXT NOT NULL DEFAULT '',
  stat_cost REAL NOT NULL DEFAULT 0,
  show_cnt REAL NOT NULL DEFAULT 0,
  click_cnt REAL NOT NULL DEFAULT 0,
  convert_cnt REAL NOT NULL DEFAULT 0,
  roi_1day REAL NOT NULL DEFAULT 0,
  metric_payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  PRIMARY KEY (metric_date, metric_hour, advertiser_id, project_id)
);

CREATE INDEX IF NOT EXISTS idx_project_hourly_metrics_date_account
  ON project_hourly_metrics (metric_date, advertiser_id, metric_hour, stat_cost DESC);

CREATE TABLE IF NOT EXISTS material_sync_state (
  workflow TEXT NOT NULL,
  sync_date TEXT NOT NULL,
  status TEXT NOT NULL,
  product TEXT NOT NULL DEFAULT '',
  platform TEXT NOT NULL DEFAULT '',
  account_count INTEGER NOT NULL DEFAULT 0,
  material_row_count INTEGER NOT NULL DEFAULT 0,
  artifact_path TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (workflow, sync_date, product, platform)
);

CREATE INDEX IF NOT EXISTS idx_material_sync_state_status
  ON material_sync_state (workflow, status, sync_date);

CREATE TABLE IF NOT EXISTS material_metric_rollups (
  window_key TEXT NOT NULL,
  window_days INTEGER NOT NULL DEFAULT 0,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  canonical_material_key TEXT NOT NULL DEFAULT '',
  material_id TEXT NOT NULL,
  material_kind TEXT NOT NULL DEFAULT 'video',
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
  PRIMARY KEY (window_key, period_start, period_end, material_id)
);

CREATE INDEX IF NOT EXISTS idx_material_metric_rollups_rank
  ON material_metric_rollups (window_key, stat_cost DESC);

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
);

CREATE INDEX IF NOT EXISTS idx_material_duplicate_candidates_material
  ON material_duplicate_candidates (material_id);

CREATE INDEX IF NOT EXISTS idx_material_duplicate_candidates_rule
  ON material_duplicate_candidates (duplicate_rule, confidence_score DESC);

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
);

CREATE INDEX IF NOT EXISTS idx_material_attribute_snapshots_flags
  ON material_attribute_snapshots (
    is_ad_low_quality_material,
    is_inefficient_material,
    is_similar_material,
    is_carry_material,
    synced_at DESC
  );

CREATE TABLE IF NOT EXISTS metric_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  metric_date TEXT NOT NULL,
  cost REAL NOT NULL DEFAULT 0,
  conversions INTEGER NOT NULL DEFAULT 0,
  roi REAL,
  payload_json TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operation_logs (
  operation_id TEXT PRIMARY KEY,
  occurred_at TEXT NOT NULL,
  advertiser_id TEXT NOT NULL DEFAULT '',
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  action TEXT NOT NULL,
  operator TEXT NOT NULL DEFAULT '',
  detail TEXT NOT NULL DEFAULT '',
  before_json TEXT NOT NULL DEFAULT '{}',
  after_json TEXT NOT NULL DEFAULT '{}',
  payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_operation_logs_date_entity
  ON operation_logs (occurred_at, entity_type, entity_id);

CREATE TABLE IF NOT EXISTS strategy_plans (
  plan_id TEXT PRIMARY KEY,
  phase TEXT NOT NULL,
  execution_enabled INTEGER NOT NULL,
  request_json TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS create_requests (
  request_id TEXT PRIMARY KEY,
  phase TEXT NOT NULL,
  execution_enabled INTEGER NOT NULL,
  request_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS create_strategy_plans (
  plan_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  phase TEXT NOT NULL,
  execution_enabled INTEGER NOT NULL,
  request_json TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_create_strategy_plans_request
  ON create_strategy_plans (request_id);

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
);

CREATE INDEX IF NOT EXISTS idx_create_idempotency_keys_plan
  ON create_idempotency_keys (plan_id, scope);

CREATE INDEX IF NOT EXISTS idx_create_idempotency_keys_status
  ON create_idempotency_keys (status, target_date);

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
);

CREATE INDEX IF NOT EXISTS idx_create_provider_id_ledger_local_key
  ON create_provider_id_ledger (local_key);

CREATE INDEX IF NOT EXISTS idx_create_provider_id_ledger_plan
  ON create_provider_id_ledger (plan_id, entity_type);

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
);

CREATE INDEX IF NOT EXISTS idx_create_material_bind_ledger_plan
  ON create_material_bind_ledger (plan_id, status);

CREATE INDEX IF NOT EXISTS idx_create_material_bind_ledger_source
  ON create_material_bind_ledger (source_advertiser_id, status);

CREATE TABLE IF NOT EXISTS source_material_preload_ledger (
  product TEXT NOT NULL,
  source_advertiser_id TEXT NOT NULL,
  target_advertiser_id TEXT NOT NULL,
  source_material_id TEXT NOT NULL,
  source_video_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  batch_key TEXT NOT NULL DEFAULT '',
  response_payload_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (product, source_advertiser_id, target_advertiser_id, source_material_id)
);

CREATE INDEX IF NOT EXISTS idx_source_material_preload_ledger_target
  ON source_material_preload_ledger (target_advertiser_id, status);

CREATE INDEX IF NOT EXISTS idx_source_material_preload_ledger_source
  ON source_material_preload_ledger (product, source_advertiser_id, source_material_id, status);

CREATE TABLE IF NOT EXISTS source_material_bad_videos (
  product TEXT NOT NULL,
  source_advertiser_id TEXT NOT NULL,
  source_video_id TEXT NOT NULL,
  source_material_id TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active',
  source_workflow TEXT NOT NULL DEFAULT '',
  response_payload_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (product, source_advertiser_id, source_video_id)
);

CREATE INDEX IF NOT EXISTS idx_source_material_bad_videos_active
  ON source_material_bad_videos (product, source_advertiser_id, status);
