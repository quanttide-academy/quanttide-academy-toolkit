import re
import sqlite3

import pytest

from feishu_workflows.core import db, migrations
from tests.helpers import ROOT

OLD = (ROOT / "tests" / "fixtures" / "state_v0_schema.sql").read_text(encoding="utf-8")


def old_db(p, lock=False, tenant_col=False):
    d = sqlite3.connect(str(p))
    d.executescript(OLD)
    if tenant_col:
        d.execute("alter table messages add column sender_tenant_key TEXT")
    d.execute("alter table topics add column confirmed_version TEXT")
    for i, s in enumerate(["待确认", "已写入", "已否决", "已在跟进", "已结束"]):
        d.execute(
            "insert into topics(fingerprint,title,status,confirmed) values(?,?,?,?)", (f"om:om_{i}", f"t{i}", s, i % 2)
        )
    for i in range(4):
        d.execute(
            "insert into messages(message_id,chat_id,ts,text,batch,pushed) values(?,?,?,?,?,?)",
            (f"om_m{i}", "oc", i, "x", "b", i % 2),
        )
    d.execute(
        "insert into write_actions(key,batch,fingerprint,version,kind,idx,status) values('k1','b','om:om_1','v1','parent',0,'done')"
    )
    d.execute(
        "insert into replies(batch,raw,parsed,versions,at) values('b','#1 写入','{}','{}','2026-10-19T10:00:00Z')"
    )
    d.execute("insert into rejections values('om:om_2','t2','否','2026-10-19T18:00:00+08:00')")
    d.execute("insert into cursors values('oc',5)")
    d.execute("insert into watched_chats values('oc','n','2026-10-18T00:00:00Z','2026-10-18T08:00:00+08:00',1)")
    if lock:
        d.execute("insert into run_lock values('run','b',99999999999)")
    d.commit()
    return d


def test_migrate_preserves_rows_and_maps_status(tmp_path):
    p = tmp_path / "s.db"
    old_db(p).close()
    assert migrations.migrate(p) == [1, 2, 3, 4, 5]
    assert list((tmp_path / "backups").glob("backup-state-*.db"))  # 迁移前由代码强制自动备份
    d = sqlite3.connect(str(p))
    assert dict(d.execute("select fingerprint,status from topics")) == {
        "om:om_0": "pending",
        "om:om_1": "written",
        "om:om_2": "rejected",
        "om:om_3": "following",
        "om:om_4": "closed",
    }
    assert (
        d.execute("select count(*) from messages").fetchone()[0] == 4
        and d.execute("select count(*) from reply_logs").fetchone()[0] == 1
    )
    assert d.execute("select key,fingerprint,status from write_actions").fetchall() == [("k1", "om:om_1", "done")]
    assert d.execute("select fingerprint,at from rejections").fetchall() == [("om:om_2", "2026-10-19T10:00:00.000Z")]
    assert d.execute("select target_key,chat_id,last_ts from watch_cursors").fetchall() == [("ou_demo_self", "oc", 5)]
    cols = {r[1]: r[2] for r in d.execute("pragma table_info(messages)")}
    assert (
        {"id", "created_at", "updated_at", "is_deleted", "deleted_at", "sender_tenant_key"} <= set(cols)
        and cols["pushed"] == "BOOLEAN"
        and cols["created_at"] == "TIMESTAMP"
    )
    names = {r[0] for r in d.execute("select name from sqlite_master where type='table'")}
    assert "run_locks" in names and "reply_logs" in names and "run_lock" not in names and "replies" not in names
    assert "cursors" not in names and "pending_cursors" not in names
    d.close()
    assert migrations.migrate(p) == []  # 可重复执行


def test_migrate_adds_tenant_col_idempotent(tmp_path):
    p = tmp_path / "s.db"
    old_db(p, tenant_col=True).close()
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    assert [r[1] for r in d.execute("pragma table_info(messages)")].count("sender_tenant_key") == 1
    d.close()


def test_migrate_refuses_when_locked_or_without_backup(tmp_path):
    p = tmp_path / "s.db"
    old_db(p, lock=True).close()
    with pytest.raises(migrations.LockHeld):
        migrations.migrate(p)
    with pytest.raises(migrations.BackupFailed):
        migrations.migrate(p, require_backup=False)
    d = sqlite3.connect(str(p))
    assert d.execute("select count(*) from topics").fetchone()[0] == 5  # 原样回滚
    assert "run_lock" in {r[0] for r in d.execute("select name from sqlite_master")}
    d.close()
    q = tmp_path / "q.db"
    old_db(q).close()
    with pytest.raises(migrations.BackupFailed):
        migrations.migrate(q, backup_path=tmp_path / "missing.db")


def test_connect_legacy_needs_migration(tmp_path):
    p = tmp_path / "s.db"
    old_db(p).close()
    with pytest.raises(db.NeedsMigration):
        db.connect({"paths": {"state_db": str(p)}})


def test_logs_append_only():
    bad = re.compile(r"(?i)(update|delete\s+from)\s+(reply_logs|write_action_logs)\b")
    hits = [str(f) for f in (ROOT / "src").rglob("*.py") if bad.search(f.read_text(encoding="utf-8"))]
    assert hits == []


def test_updated_at_trigger_and_v5_checks(tmp_path):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    d.execute("insert into topics(fingerprint,updated_at) values('f','2000-01-01T00:00:00.000Z')")
    d.execute("update topics set title='x' where fingerprint='f'")
    up = d.execute("select updated_at from topics").fetchone()[0]
    assert up != "2000-01-01T00:00:00.000Z" and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", up)
    with pytest.raises(sqlite3.IntegrityError):
        d.execute("insert into topics(fingerprint,created_at) values('bad_ts','2026-10-20T00:00:00Z')")
    with pytest.raises(sqlite3.IntegrityError):
        d.execute("insert into topics(fingerprint,confirmed) values('bad_bool',2)")
    with pytest.raises(sqlite3.IntegrityError):
        d.execute("insert into topics(fingerprint,is_deleted) values('bad_del',-1)")
    d.close()


def test_plural_tables_and_integer_primary_key_guard(tmp_path):
    p = tmp_path / "fresh.db"
    assert migrations.migrate(p) == [1, 2, 3, 4, 5]
    d = sqlite3.connect(str(p))
    try:
        tabs = {r[0] for r in d.execute("select name from sqlite_master where type='table'")} - {"sqlite_sequence"}
        assert len(tabs) == 16 and all(t.endswith("s") for t in tabs)
        for t in tabs:
            info = d.execute(f"pragma table_info({t})").fetchall()
            pk = [(r[1], r[2].upper()) for r in info if r[5] == 1]
            col_names = {r[1] for r in info}
            assert pk == [("id", "INTEGER")] and {"created_at", "updated_at", "is_deleted", "deleted_at"} <= col_names
        d.execute("insert into watch_cursors(target_key,chat_id,last_ts) values('ou_a','oc_1',1)")
        with pytest.raises(sqlite3.IntegrityError):
            d.execute("insert into watch_cursors(target_key,chat_id,last_ts) values('ou_a','oc_1',2)")
    finally:
        d.close()


def test_v2_db_upgrades_to_v5_idempotent(tmp_path):
    p = tmp_path / "v2.db"
    d = sqlite3.connect(str(p))
    d.isolation_level = None
    migrations._create_all(d, upto=2)
    migrations._record(d, 1, "baseline")
    migrations._record(d, 2, "x")
    d.execute("insert into topics(fingerprint,title) values('f','t')")
    d.close()
    assert migrations.migrate(p) == [3, 4, 5] and migrations.migrate(p) == []
    d = sqlite3.connect(str(p))
    assert d.execute("select count(*) from topics").fetchone()[0] == 1 and "watch_cursors" in {
        r[0] for r in d.execute("select name from sqlite_master")
    }
    d.close()


def test_v2_db_with_lock_refused(tmp_path):
    p = tmp_path / "v2.db"
    d = sqlite3.connect(str(p))
    d.isolation_level = None
    migrations._create_all(d, upto=2)
    migrations._record(d, 1, "baseline")
    migrations._record(d, 2, "x")
    d.execute("insert into run_locks(name,owner,expires) values('run','b1',9999999999)")
    d.close()
    with pytest.raises(migrations.LockHeld):
        migrations.migrate(p)
    d = sqlite3.connect(str(p))
    assert [r[0] for r in d.execute("select version from schema_migrations order by version")] == [1, 2]
    assert "watch_cursors" not in {r[0] for r in d.execute("select name from sqlite_master")}
    d.close()


def test_v3_db_upgrades_to_v5_merges_cursors_and_drops_old(tmp_path):
    p = tmp_path / "v3.db"
    d = sqlite3.connect(str(p))
    d.isolation_level = None
    migrations._create_all(d, upto=3)
    for v in (1, 2, 3):
        migrations._record(d, v, "x")
    d.execute("insert into topics(fingerprint,title,created_at) values('f','t','2026-10-18T09:30:00Z')")
    d.execute("insert into watch_targets(key,name,active) values('ou_self','本人',1)")
    d.execute("insert into watch_cursors(target_key,chat_id,last_ts) values('ou_self','oc_1',300)")
    d.execute("insert into cursors(chat_id,last_ts) values('oc_1',500),('oc_2',600)")
    d.execute("insert into pending_cursors(batch,chat_id,last_ts) values('b1','oc_1',550)")
    d.close()
    assert migrations.migrate(p) == [4, 5] and migrations.migrate(p) == []
    d = sqlite3.connect(str(p))
    t = {r[0] for r in d.execute("select name from sqlite_master where type='table'")}
    assert {"org_plans", "org_ops", "org_approvals"} <= t and "cursors" not in t and "pending_cursors" not in t
    assert d.execute("select target_key,chat_id,last_ts from watch_cursors order by chat_id").fetchall() == [
        ("ou_self", "oc_1", 500),
        ("ou_self", "oc_2", 600),
    ]
    assert d.execute("select batch,target_key,chat_id,last_ts from watch_pending_cursors").fetchall() == [
        ("b1", "ou_self", "oc_1", 550)
    ]
    assert d.execute("select created_at from topics where fingerprint='f'").fetchone()[0] == "2026-10-18T09:30:00.000Z"
    d.execute("insert into org_ops(plan_id,idx,op_key,phase,request_digest) values('p',1,'k','before','x')")
    with pytest.raises(sqlite3.IntegrityError):
        d.execute("insert into org_ops(plan_id,idx,op_key,phase,request_digest) values('p',1,'k','before','y')")
    d.close()


def test_v3_db_with_lock_refused(tmp_path):
    p = tmp_path / "v3.db"
    d = sqlite3.connect(str(p))
    d.isolation_level = None
    migrations._create_all(d, upto=3)
    for v in (1, 2, 3):
        migrations._record(d, v, "x")
    d.execute("insert into run_locks(name,owner,expires) values('run','b1',9999999999)")
    d.close()
    with pytest.raises(migrations.LockHeld):
        migrations.migrate(p)
    d = sqlite3.connect(str(p))
    assert "org_plans" not in {r[0] for r in d.execute("select name from sqlite_master")}
    d.close()
