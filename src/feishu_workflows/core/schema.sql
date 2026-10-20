-- state.db 表结构 v5。表名复数；每表 id INTEGER PRIMARY KEY（等价 BIGINT）+ created_at/updated_at/is_deleted/deleted_at；
-- 时间列声明 TIMESTAMP，CHECK 仅允许 YYYY-MM-DDTHH:MM:SS.mmmZ；布尔列声明 BOOLEAN，CHECK 仅允许 0/1；状态值英文。reply_logs、write_action_logs 只追加。
CREATE TABLE IF NOT EXISTS schema_migrations(id INTEGER PRIMARY KEY,version INTEGER NOT NULL UNIQUE,name TEXT,
  applied_at TIMESTAMP CHECK(applied_at IS NULL OR applied_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS watched_chats(id INTEGER PRIMARY KEY,chat_id TEXT NOT NULL UNIQUE,name TEXT,
  first_seen TIMESTAMP CHECK(first_seen IS NULL OR first_seen GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  last_checked TIMESTAMP CHECK(last_checked IS NULL OR last_checked GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  active BOOLEAN NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,message_id TEXT NOT NULL UNIQUE,chat_id TEXT,sender TEXT,ts INTEGER,text TEXT,topic_id INTEGER,batch TEXT,
  pushed BOOLEAN NOT NULL DEFAULT 0 CHECK(pushed IN (0,1)),sender_tenant_key TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY,fingerprint TEXT NOT NULL UNIQUE,title TEXT,status TEXT,relation TEXT,todoist_id TEXT,sources TEXT,batch TEXT,note TEXT,origin TEXT,ext_id TEXT,keywords TEXT,
  confirmed BOOLEAN NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1)),
  confirmed_at TIMESTAMP CHECK(confirmed_at IS NULL OR confirmed_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  confirmed_version TEXT,item_json TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS rejections(id INTEGER PRIMARY KEY,fingerprint TEXT NOT NULL UNIQUE,title TEXT,reason TEXT,
  at TIMESTAMP CHECK(at IS NULL OR at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS run_locks(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,owner TEXT,expires INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS writes(id INTEGER PRIMARY KEY,fingerprint TEXT NOT NULL UNIQUE,provider TEXT,parent_id TEXT,subs_done TEXT,status TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS write_actions(id INTEGER PRIMARY KEY,key TEXT NOT NULL UNIQUE,batch TEXT,fingerprint TEXT,version TEXT,kind TEXT,idx INTEGER,payload TEXT,ext_id TEXT,status TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS write_action_logs(id INTEGER PRIMARY KEY,key TEXT NOT NULL,status TEXT NOT NULL,ext_id TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
CREATE TABLE IF NOT EXISTS reply_logs(id INTEGER PRIMARY KEY,batch TEXT,raw TEXT,parsed TEXT,versions TEXT,
  at TIMESTAMP CHECK(at IS NULL OR at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(created_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) CHECK(updated_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'),
  is_deleted BOOLEAN NOT NULL DEFAULT 0 CHECK(is_deleted IN (0,1)),
  deleted_at TIMESTAMP CHECK(deleted_at IS NULL OR deleted_at GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9].[0-9][0-9][0-9]Z'));
