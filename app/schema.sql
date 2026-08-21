PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY,
  account_name TEXT NOT NULL,
  plan TEXT NOT NULL,
  status TEXT NOT NULL,
  csm TEXT,
  contract_file TEXT,
  premium_support INTEGER NOT NULL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(account_id),
  carrier TEXT,
  status TEXT NOT NULL,
  booked_at TEXT NOT NULL,
  pickup_window_start TEXT,
  pickup_window_end TEXT,
  pickup_actual_at TEXT,
  shipment_fee_inr REAL,
  carrier_fault INTEGER,
  customer_fault INTEGER,
  cancellation_requested_at TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
  ticket_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(account_id),
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  subject TEXT NOT NULL,
  description TEXT NOT NULL,
  channel TEXT,
  assigned_to TEXT,
  last_customer_message_at TEXT,
  historical_resolution TEXT
);

CREATE TABLE IF NOT EXISTS account_policy_facts (
  account_id TEXT NOT NULL REFERENCES accounts(account_id),
  scenario TEXT NOT NULL,
  fact_name TEXT NOT NULL,
  fact_value TEXT NOT NULL,
  source_document TEXT NOT NULL,
  source_section TEXT NOT NULL,
  PRIMARY KEY (account_id, scenario, fact_name)
);

CREATE TABLE IF NOT EXISTS document_chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  document_name TEXT NOT NULL,
  document_type TEXT NOT NULL,
  customer_id TEXT,
  status TEXT NOT NULL,
  effective_date TEXT,
  section TEXT NOT NULL,
  scenario_tags TEXT NOT NULL,
  text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS actions (
  action_id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  account_id TEXT NOT NULL,
  ticket_id TEXT,
  order_id TEXT,
  payload_json TEXT NOT NULL,
  prepared_by TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  confirmed_at TEXT,
  executed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
  log_id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  user TEXT NOT NULL,
  query_text TEXT,
  account_id TEXT,
  tools_used_json TEXT,
  evidence_json TEXT,
  decision_json TEXT,
  action_id TEXT,
  confidence TEXT
);

CREATE TABLE IF NOT EXISTS staff_users (
  user_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  assigned_account_ids TEXT NOT NULL
);
