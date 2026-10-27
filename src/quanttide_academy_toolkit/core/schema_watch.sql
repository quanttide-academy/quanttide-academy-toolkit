-- state.db v3/v5：watch 模块（多目标监听与统一游标）。目标 × 群的游标；暂存游标按批次，commit 后才推进。
CREATE TABLE IF NOT EXISTS watch_targets(id INTEGER PRIMARY KEY,key TEXT NOT NULL UNIQUE,name TEXT,
  first_seen TIMESTAMP CHECK(first_seen IS NULL OR first_seen GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  active BOOLEAN NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS watch_cursors(id INTEGER PRIMARY KEY,target_key TEXT NOT NULL,chat_id TEXT NOT NULL,last_ts INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),UNIQUE(target_key,chat_id));
CREATE TABLE IF NOT EXISTS watch_pending_cursors(id INTEGER PRIMARY KEY,batch TEXT NOT NULL,target_key TEXT NOT NULL,chat_id TEXT NOT NULL,last_ts INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),UNIQUE(batch,target_key,chat_id));
