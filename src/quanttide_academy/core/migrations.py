"""state.db 版本迁移（v1~v5）：v5 启用 TIMESTAMP/BOOLEAN CHECK、sent_at 转 Z 文本、合并并删除旧游标表；迁移前由代码强制在线备份。"""

import contextlib
import datetime
import re
import sqlite3
import tempfile
import time
from pathlib import Path

from quanttide_academy import settings
from quanttide_academy.core import config
from quanttide_academy.watch import targets

SCHEMA, SCHEMA_V3, SCHEMA_V4 = (
    Path(__file__).resolve().parent / f for f in ("schema.sql", "schema_watch.sql", "schema_org.sql")
)
LATEST = 5
NAMES = {
    1: "baseline",
    2: "plural-tables-timestamps-english-status",
    3: "watch-targets-cursors",
    4: "org-plans-ops",
    5: "v5-timestamps-booleans-merge-cursors",
}
ORG_TABLES, WATCH_TABLES = (
    "org_plans org_ops org_approvals".split(),
    "watch_targets watch_cursors watch_pending_cursors".split(),
)
TABLES = "watched_chats messages topics rejections run_locks writes write_actions write_action_logs reply_logs".split()
LEGACY_CURSORS = tuple(
    f"CREATE TABLE IF NOT EXISTS {t}(id INTEGER PRIMARY KEY,{c},created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),is_deleted BOOLEAN NOT NULL DEFAULT 0,deleted_at TEXT{u})"
    for t, c, u in (
        ("cursors", "chat_id TEXT NOT NULL UNIQUE,last_ts INTEGER", ""),
        ("pending_cursors", "batch TEXT NOT NULL,chat_id TEXT NOT NULL,last_ts INTEGER", ",UNIQUE(batch,chat_id)"),
    )
)
RENAMED = {"run_lock": "run_locks", "replies": "reply_logs"}
STATUS_V2 = {
    "待确认": "pending",
    "已写入": "written",
    "已否决": "rejected",
    "仅知悉": "fyi",
    "已在跟进": "following",
    "已结束": "closed",
}


class LockHeld(RuntimeError):
    pass


class BackupFailed(RuntimeError):
    pass


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _norm_ts(v, req=False):
    if v is None or str(v).strip() == "":
        return _now() if req else None
    s = str(v).strip()
    if isinstance(v, (int, float)) or s.isdigit():
        sec, ms = divmod(int(v), 1000) if int(v) >= 10**11 else (int(v), 0)
        return f"{datetime.datetime.fromtimestamp(sec, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}Z"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z", s):
        return s if "." in s else s[:-1] + ".000Z"
    dt = datetime.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    return (dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)).astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


def _verify_backup(db: Path, bak: Path):
    bak = Path(bak)
    if not bak.is_file() or bak.resolve() == Path(db).resolve():
        raise BackupFailed(f"无效的备份文件：{bak}")
    try:
        with contextlib.closing(sqlite3.connect(str(bak))) as chk:
            ok = chk.execute("pragma integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as e:
        raise BackupFailed(f"备份校验失败：{e}") from e
    if ok != "ok":
        raise BackupFailed(f"备份 integrity_check 未通过：{ok}")


def backup(db: Path, bdir: Path | None = None) -> Path:
    db = Path(db)
    tmp = Path(tempfile.gettempdir()).resolve()
    bdir = Path(
        bdir
        or (
            db.resolve().parent / "backups"
            if (settings.is_test() or tmp in db.resolve().parents)
            else settings.default_data_dir()
        )
    )
    bdir.mkdir(parents=True, exist_ok=True)
    stem = f"backup-state-{time.strftime('%Y%m%d-%H%M%S')}"
    bak = next(
        bdir / f"{stem}{f'-{i}' if i else ''}.db"
        for i in range(1000)
        if not (bdir / f"{stem}{f'-{i}' if i else ''}.db").exists()
    )
    try:
        with contextlib.closing(sqlite3.connect(str(db))) as src, contextlib.closing(sqlite3.connect(str(bak))) as dst:
            src.backup(dst)
    except sqlite3.DatabaseError as e:
        raise BackupFailed(f"备份失败：{e}") from e
    _verify_backup(db, bak)
    return bak


def _create_all(d, upto=LATEST):
    raw = ";".join(
        f.read_text(encoding="utf-8") for f in [SCHEMA, SCHEMA_V3, SCHEMA_V4][: 1 + (upto >= 3) + (upto >= 4)]
    )
    if upto < 5:
        raw = (
            re.sub(r"\s*CHECK\((?:[^()]+|\([^()]*\))*\)", "", raw)
            .replace("TIMESTAMP NOT NULL DEFAULT", "TIMESTAMP DEFAULT")
            .replace("sent_at TIMESTAMP NOT NULL", "sent_at INTEGER NOT NULL")
        )
    for st in [
        s for s in raw.split(";") if any(line.strip() and not line.strip().startswith("--") for line in s.splitlines())
    ]:
        d.execute(st)
    for st in LEGACY_CURSORS if 2 <= upto < 5 else ():
        d.execute(st)


def _tables(d):
    return {r[0] for r in d.execute("select name from sqlite_master where type='table'")}


def _cols(d, t):
    return [r[1] for r in d.execute(f"pragma table_info({t})")]


def applied(d):
    return (
        {r[0] for r in d.execute("select version from schema_migrations")}
        if "schema_migrations" in _tables(d)
        else set()
    )


def is_legacy(d):
    return bool(_tables(d) & {"topics", "run_lock", "replies"}) and "schema_migrations" not in _tables(d)


def _triggers(d, tables=None):
    for t in tables or TABLES:
        d.execute(
            f"CREATE TRIGGER IF NOT EXISTS trg_{t}_updated_at AFTER UPDATE ON {t} WHEN NEW.updated_at IS OLD.updated_at BEGIN UPDATE {t} SET updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=NEW.id; END"
        )


def _record(d, v, name):
    d.execute("insert or ignore into schema_migrations(version,name,applied_at) values(?,?,?)", (v, name, _now()))


def init_fresh(d):
    with d:
        _create_all(d, upto=LATEST)
        _triggers(d, ["schema_migrations", *TABLES, *WATCH_TABLES, *ORG_TABLES])
        d.executemany(
            "insert or ignore into schema_migrations(version,name,applied_at) values(?,?,?)",
            [(v, NAMES[v], _now()) for v in NAMES],
        )


def v1_baseline(d):
    for t, c in (("messages", "sender_tenant_key"), ("topics", "confirmed_version")):
        if t in _tables(d) and c not in _cols(d, t):
            d.execute(f"alter table {t} add column {c} TEXT")


def v2(d):
    old = _tables(d)
    v2_tabs = [*TABLES, "cursors", "pending_cursors"]
    hit = [t for t in old if t in v2_tabs or t in RENAMED]
    for t in hit:
        d.execute(f"alter table {t} rename to _old_{t}")
    _create_all(d, upto=2)
    for o in hit:
        new = RENAMED.get(o, o)
        cl = ",".join(c for c in _cols(d, f"_old_{o}") if c in _cols(d, new))
        d.execute(f"insert into {new}({cl}) select {cl} from _old_{o}")
        d.execute(f"drop table _old_{o}")
    d.executemany("update topics set status=? where status=?", [(en, zh) for zh, en in STATUS_V2.items()])
    _triggers(d, v2_tabs)


def v3(d):
    _create_all(d, upto=3)
    _triggers(d, WATCH_TABLES)


def v4(d):
    _create_all(d, upto=4)
    _triggers(d, ORG_TABLES)


def _resolve_target_key(d, target_key=None, cfg=None) -> str:
    if target_key:
        return str(target_key)
    return targets.self_key(
        cfg
        if cfg is not None
        else (
            config.load()
            if any(settings.env(k) for k in settings.CONFIG_ENVS) and settings.config_path().exists()
            else None
        ),
        d,
    )


def v5(d, target_key=None, cfg=None):
    _create_all(d, upto=4)
    tk = _resolve_target_key(d, target_key, cfg)
    for src_t, dst_t, ins_c, sel_c in (
        ("cursors", "watch_cursors", "target_key,chat_id", "?,chat_id"),
        ("pending_cursors", "watch_pending_cursors", "batch,target_key,chat_id", "batch,?,chat_id"),
    ):
        if src_t in _tables(d):
            d.execute(
                f"insert into {dst_t}({ins_c},last_ts,created_at,updated_at,is_deleted,deleted_at) select {sel_c},last_ts,created_at,updated_at,is_deleted,deleted_at from {src_t} where is_deleted=0 and chat_id is not null and last_ts is not null on conflict({ins_c}) do update set last_ts=max(coalesce({dst_t}.last_ts,0),excluded.last_ts),is_deleted=0",
                (tk,),
            )
            for q in (f"drop trigger if exists trg_{src_t}_updated_at", f"drop table {src_t}"):
                d.execute(q)
    all_tabs = ["schema_migrations", *TABLES, *WATCH_TABLES, *ORG_TABLES]
    existing = [t for t in all_tabs if t in _tables(d)]
    for t in existing:
        for q in (f"drop trigger if exists trg_{t}_updated_at", f"alter table {t} rename to _v4_{t}"):
            d.execute(q)
    _create_all(d, upto=LATEST)
    for t in existing:
        info = d.execute(f"pragma table_info({t})").fetchall()
        cols = [r[1] for r in info if r[1] in _cols(d, f"_v4_{t}")]
        types = {r[1]: (r[2].upper(), bool(r[3])) for r in info}
        for row in d.execute(f"select {','.join(cols)} from _v4_{t}").fetchall():
            d.execute(
                f"insert into {t}({','.join(cols)}) values({','.join('?' for _ in cols)})",
                [
                    _norm_ts(v, req=types[c][1])
                    if types[c][0] == "TIMESTAMP"
                    else ((1 if int(v or 0) else 0) if types[c][0] == "BOOLEAN" else v)
                    for c, v in zip(cols, row)
                ],
            )
        d.execute(f"drop table _v4_{t}")
    _triggers(d, all_tabs)


def _check_lock(d):
    if any(t in _tables(d) and d.execute(f"select count(*) from {t}").fetchone()[0] for t in ("run_lock", "run_locks")):
        raise LockHeld("运行锁非空（有批次未收尾），拒绝迁移；先收尾或 release 再迁")


def migrate(path, target_key=None, cfg=None, backup_dir=None, backup_path=None, require_backup=True):
    if not require_backup:
        raise BackupFailed("迁移前必须先备份，拒绝无备份迁移")
    path = Path(path)
    with contextlib.closing(sqlite3.connect(str(path), isolation_level=None)) as d:
        if not is_legacy(d) and not _tables(d) - {"sqlite_sequence"}:
            init_fresh(d)
            return [1, 2, 3, 4, 5]
        if not is_legacy(d) and set(NAMES) <= set(applied(d)):
            return []
        _check_lock(d)
    _verify_backup(path, backup_path) if backup_path is not None else backup(path, backup_dir)
    with contextlib.closing(sqlite3.connect(str(path), isolation_level=None)) as d:
        d.execute("begin immediate")
        try:
            done = applied(d)
            out = _check_lock(d) or [
                v
                for v, fn in (
                    (1, lambda: v1_baseline(d)),
                    (2, lambda: v2(d)),
                    (3, lambda: v3(d)),
                    (4, lambda: v4(d)),
                    (5, lambda: v5(d, target_key=target_key, cfg=cfg)),
                )
                if v not in done and (fn() or True)
            ]
            for v in out:
                _record(d, v, NAMES[v])
            d.execute("commit")
            return out
        except Exception:
            d.execute("rollback")
            raise
