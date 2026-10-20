"""BP1 集成测试：在匿名 v3 测试库上跑 v3→v5 迁移、游标合并、24h 审批窗口一致性、同秒两条消息分轮拉取，以及反例用例，
并与入库的固定期望文件 integrated_tests/expected/v5_migration.json 自动逐项比对。"""

import json
import sqlite3
from pathlib import Path

from feishu_workflows.core import migrations
from feishu_workflows.org import approve as A
from feishu_workflows.org import plan as P
from feishu_workflows.watch import cursors as C
from feishu_workflows.watch import poll as W
from feishu_workflows.watch.targets import Target
from tests.org.helpers import message
from tests.org.test_plan import cfg as org_cfg
from tests.org.test_plan import fake_big
from tests.watch.test_poll import raw

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = ROOT / "integrated_tests" / "expected" / "v5_migration.json"
COUNT_TABLES = (
    "watched_chats",
    "messages",
    "topics",
    "rejections",
    "writes",
    "write_actions",
    "write_action_logs",
    "reply_logs",
    "watch_targets",
    "watch_cursors",
    "watch_pending_cursors",
)


def _build_anonymous_v3_db(p: Path):
    d = sqlite3.connect(str(p))
    d.isolation_level = None
    try:
        migrations._create_all(d, upto=3)
        for v in (1, 2, 3):
            migrations._record(d, v, migrations.NAMES[v])
        d.execute(
            "insert into watched_chats(chat_id,name,first_seen,last_checked,active) values('oc_1','群一','2026-10-18T09:00:00+08:00','2026-10-18T10:00:00Z',1),('oc_2','群二','2026-10-18T02:00:00Z','2026-10-18T03:00:00Z',1)"
        )
        for i in range(1, 4):
            d.execute(
                "insert into messages(message_id,chat_id,sender,ts,text,batch,pushed) values(?,?,?,?,?,'b0',1)",
                (f"om_m{i}", "oc_1", "ou_demo_self", 100 + i, f"msg-{i}"),
            )
        d.execute(
            "insert into topics(fingerprint,title,status,origin,created_at) values('om:om_self_1','本人事项一','pending','识别','2026-10-18T09:30:00Z'),('om:om_self_2','本人事项二','written','识别','2026-10-18T10:30:00Z')"
        )
        for fp, title, st in [
            ("om:om_colleague_1", "同事事项一", "pending"),
            ("om:om_colleague_2", "同事事项二", "written"),
            ("om:om_colleague_3", "同事事项三", "following"),
        ]:
            d.execute(
                "insert into topics(fingerprint,title,status,origin,created_at) values(?,?,?,'同事','2026-10-18T11:00:00Z')",
                (fp, title, st),
            )
        d.execute(
            "insert into rejections(fingerprint,title,reason,at) values('om:om_rej_1','否决项','不需要','2026-10-18T12:00:00Z')"
        )
        d.execute(
            "insert into writes(fingerprint,provider,parent_id,subs_done,status) values('om:om_self_2','todoist','T1','[]','done')"
        )
        d.execute(
            "insert into write_actions(key,batch,fingerprint,version,kind,idx,status) values('k1','b0','om:om_self_2','v1','parent',0,'done')"
        )
        d.execute("insert into write_action_logs(key,status,ext_id) values('k1','done','T1')")
        d.execute(
            "insert into reply_logs(batch,raw,parsed,versions,at) values('b0','#1 写入','{}','{}','2026-10-18T12:30:00Z')"
        )
        d.execute(
            "insert into watch_targets(key,name,first_seen,active) values('ou_demo_self','示例用户','2026-10-18T00:00:00Z',1)"
        )
        d.execute("insert into watch_cursors(target_key,chat_id,last_ts) values('ou_demo_self','oc_1',300)")
        d.execute("insert into cursors(chat_id,last_ts) values('oc_1',500),('oc_2',600)")
        d.execute("insert into pending_cursors(batch,chat_id,last_ts) values('b_pend','oc_1',550)")
    finally:
        d.close()


def collect_bp1_report(tmp_path: Path, monkeypatch) -> dict:
    p = tmp_path / "anon_v3.db"
    _build_anonymous_v3_db(p)
    d = sqlite3.connect(str(p))
    try:
        before = {t: d.execute(f"select count(*) from {t}").fetchone()[0] for t in COUNT_TABLES}
    finally:
        d.close()
    migrated = migrations.migrate(p)
    second = migrations.migrate(p)
    d = sqlite3.connect(str(p))
    try:
        tabs = {r[0] for r in d.execute("select name from sqlite_master where type='table'")}
        dropped = [t for t in ("cursors", "pending_cursors") if t not in tabs]
        after = {t: d.execute(f"select count(*) from {t}").fetchone()[0] for t in COUNT_TABLES}
        merged = [
            {"target_key": r[0], "chat_id": r[1], "last_ts": r[2]}
            for r in d.execute("select target_key,chat_id,last_ts from watch_cursors order by chat_id").fetchall()
        ]
        colleague = [
            {"fingerprint": r[0], "title": r[1], "status": r[2], "origin": r[3]}
            for r in d.execute(
                "select fingerprint,title,status,origin from topics where origin='同事' order by fingerprint"
            ).fetchall()
        ]
        ts_topics = d.execute("select created_at from topics where fingerprint='om:om_self_1'").fetchone()[0]
        ts_chat = d.execute("select first_seen from watched_chats where chat_id='oc_1'").fetchone()[0]
        final_vers = sorted(migrations.applied(d))
    finally:
        d.close()
    # 24h 审批窗口（v4→v5 迁移前后 + sent_at 秒转 .000Z）
    p4 = tmp_path / "v4.db"
    d4 = sqlite3.connect(str(p4))
    d4.isolation_level = None
    try:
        migrations._create_all(d4, upto=4)
        for v in (1, 2, 3, 4):
            migrations._record(d4, v, migrations.NAMES[v])
        f = fake_big()
        c = org_cfg()
        pl = P.compute(c, f)
        pid = pl["plan_id"]
        base = 1792411200
        d4.execute(
            "insert into org_plans(plan_id,items_json,held_json,status,created_at,updated_at) values(?,?,?,'pending','2026-10-19T12:00:00Z','2026-10-19T12:00:00Z')",
            (pid, json.dumps(pl["items"], sort_keys=True), "[]"),
        )
        ok_m = message(f, f"批准 {pid[:8]}", create_ms=(base + 3600) * 1000)
        exp_m = message(f, f"批准 {pid[:8]}", create_ms=(base + 25 * 3600) * 1000)
        w_before = A.verify(c, d4, ok_m, ("pending", "approved"), f)[0] == pid
        try:
            A.verify(c, d4, exp_m, ("pending", "approved"), f)
            e_before = "accepted"
        except A.ApprovalError:
            e_before = "rejected"
        d4.execute(
            "insert into org_approvals(message_id,plan_id,sender,chat_id,sent_at,text,created_at,updated_at) values(?,?,?,?,?,?,?,?)",
            (ok_m, pid, "ou_me", "oc_ap", base, "批准 " + pid[:8], "2026-10-19T12:00:00Z", "2026-10-19T12:00:00Z"),
        )
    finally:
        d4.close()
    migrations.migrate(p4)
    d4 = sqlite3.connect(str(p4))
    try:
        sent_at_val = d4.execute("select sent_at from org_approvals where message_id=?", (ok_m,)).fetchone()[0]
        w_after = A.verify(c, d4, ok_m, ("pending", "approved"), f)[0] == pid
        try:
            A.verify(c, d4, exp_m, ("pending", "approved"), f)
            e_after = "accepted"
        except A.ApprovalError:
            e_after = "rejected"
    finally:
        d4.close()
    # 同秒两条消息分两轮拉取
    pw = tmp_path / "watch.db"
    migrations.migrate(pw)
    dw = sqlite3.connect(str(pw))
    try:
        m1 = raw("om_same_1", "ou_a", 150, "一")
        m2 = raw("om_same_2", "ou_a", 150, "二")
        rounds = [[m1], [m1, m2]]
        monkeypatch.setattr(W.larkcli, "call", lambda cfg, *a, **k: [{"code": 0, "data": {"items": rounds.pop(0)}}])
        tg = [Target("ou_a", "甲", {"ou_a": "内部"})]
        wcfg = {"self_open_id": "ou_me", "scope": {"include_chats": [{"chat_id": "oc_1", "name": "群一"}]}}
        r1 = W.poll(wcfg, dw, "b1", tg, init=100, end=200)
        C.commit(dw, "b1")
        c1 = C.start_points(dw, tg, ["oc_1"], init=100)["oc_1"]["start"]
        r2 = W.poll(wcfg, dw, "b2", tg, init=100, end=200)
        C.commit(dw, "b2")
        c2 = C.start_points(dw, tg, ["oc_1"], init=100)["oc_1"]["start"]
    finally:
        dw.close()
    # 反例（失败用例）
    plk = tmp_path / "lock.db"
    _build_anonymous_v3_db(plk)
    dlk = sqlite3.connect(str(plk))
    try:
        dlk.execute("insert into run_locks(name,owner,expires) values('run','b_hold',9999999999)")
        dlk.commit()
    finally:
        dlk.close()
    try:
        migrations.migrate(plk)
        neg_lock = "ok"
    except migrations.LockHeld:
        neg_lock = "LockHeld"
    try:
        migrations.migrate(p, require_backup=False)
        neg_bak = "ok"
    except migrations.BackupFailed:
        neg_bak = "BackupFailed"
    d = sqlite3.connect(str(p))
    try:
        try:
            d.execute("insert into topics(fingerprint,created_at) values('bad_ts','2026-10-20T00:00:00Z')")
            neg_ts = "ok"
        except sqlite3.IntegrityError:
            neg_ts = "IntegrityError"
        try:
            d.execute("insert into topics(fingerprint,confirmed) values('bad_bool',2)")
            neg_bool = "ok"
        except sqlite3.IntegrityError:
            neg_bool = "IntegrityError"
    finally:
        d.close()
    return {
        "migrated_versions_from_v3": migrated,
        "idempotent_second_run": second,
        "final_applied_versions": final_vers,
        "dropped_legacy_cursor_tables": dropped,
        "table_counts_before_and_after": {t: {"before": before[t], "after": after[t]} for t in COUNT_TABLES},
        "merged_watch_cursors": merged,
        "colleague_topics_preserved": colleague,
        "timestamp_samples_normalized": {
            "topics_created_at": ts_topics,
            "watched_chats_first_seen": ts_chat,
            "org_approvals_sent_at": sent_at_val,
        },
        "approval_window_24h_consistency": {
            "within_24h_before": w_before,
            "within_24h_after": w_after,
            "expired_25h_before": e_before,
            "expired_25h_after": e_after,
        },
        "same_second_two_rounds_poll": {
            "round1_ids": [x["message_id"] for x in r1["messages"]],
            "round2_ids": [x["message_id"] for x in r2["messages"]],
            "cursor_after_round1": c1,
            "cursor_after_round2": c2,
        },
        "negative_cases": {
            "lock_held_refused": neg_lock,
            "corrupt_or_missing_backup_refused": neg_bak,
            "invalid_timestamp_check_rejected": neg_ts,
            "invalid_boolean_check_rejected": neg_bool,
        },
    }


def test_bp1_v3_to_v5_matches_expected(tmp_path, monkeypatch):
    actual = collect_bp1_report(tmp_path, monkeypatch)
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert actual == expected
