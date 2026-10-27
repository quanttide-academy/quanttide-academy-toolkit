-- state.db v4/v5：org 模块（部门 ↔ 群对齐）。计划按 plan_id（sha256）存；每次写操作前后各记一行日志，op_key 为幂等键。
CREATE TABLE IF NOT EXISTS org_plans(id INTEGER PRIMARY KEY,plan_id TEXT NOT NULL UNIQUE,items_json TEXT NOT NULL,held_json TEXT,status TEXT NOT NULL DEFAULT 'pending',
  approved_items TEXT,approval_text TEXT,
  approved_at TIMESTAMP CHECK(approved_at IS NULL OR approved_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  applied_at TIMESTAMP CHECK(applied_at IS NULL OR applied_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS org_ops(id INTEGER PRIMARY KEY,plan_id TEXT NOT NULL,idx INTEGER NOT NULL,op_key TEXT NOT NULL,phase TEXT NOT NULL,request_digest TEXT NOT NULL,result TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),UNIQUE(op_key,phase));
CREATE TABLE IF NOT EXISTS org_approvals(id INTEGER PRIMARY KEY,message_id TEXT NOT NULL UNIQUE,plan_id TEXT NOT NULL,sender TEXT NOT NULL,chat_id TEXT NOT NULL,
  sent_at TIMESTAMP NOT NULL CHECK(sent_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  text TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
