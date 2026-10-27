"""watch 游标：按「目标 × 群」记录；先暂存（按批次），commit 才推进，abort 丢弃；只前进不后退。"""

import datetime


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def sync_targets(d, targets):
    """配置里的目标写入 watch_targets；配置里没有的标为不启用（不删除）。"""
    keys = {t.key for t in targets}
    with d:
        for t in targets:
            d.execute(
                "insert into watch_targets(key,name,first_seen,active) values(?,?,?,1) on conflict(key) do update set name=excluded.name,active=1",
                (t.key, t.name, _now()),
            )
        for (k,) in d.execute("select key from watch_targets where active=1").fetchall():
            if k not in keys:
                d.execute("update watch_targets set active=0 where key=?", (k,))


def start_points(d, targets, chats, init):
    """每个群：各目标的起点（游标 last_ts，或 init），群的拉取起点取最小值（同秒靠 message_id 去重）。"""
    out = {}
    for cid in chats:
        per = {}
        for t in targets:
            r = d.execute(
                "select last_ts from watch_cursors where target_key=? and chat_id=? and is_deleted=0", (t.key, cid)
            ).fetchone()
            per[t.key] = r[0] if r and r[0] is not None else init
        out[cid] = {"start": min(per.values()) if per else init, "targets": per}
    return out


def stage(d, batch, marks):
    """marks：{(target_key, chat_id): last_ts}，写暂存表。"""
    with d:
        for (k, cid), ts in marks.items():
            d.execute(
                """insert into watch_pending_cursors(batch,target_key,chat_id,last_ts) values(?,?,?,?)
              on conflict(batch,target_key,chat_id) do update set last_ts=max(last_ts,excluded.last_ts)""",
                (batch, k, cid, ts),
            )


def commit(d, batch):
    with d:
        for k, cid, ts in d.execute(
            "select target_key,chat_id,last_ts from watch_pending_cursors where batch=?", (batch,)
        ).fetchall():
            d.execute(
                """insert into watch_cursors(target_key,chat_id,last_ts) values(?,?,?)
              on conflict(target_key,chat_id) do update set last_ts=max(coalesce(last_ts,0),excluded.last_ts)""",
                (k, cid, ts),
            )
        d.execute("delete from watch_pending_cursors where batch=?", (batch,))


def abort(d, batch):
    with d:
        d.execute("delete from watch_pending_cursors where batch=?", (batch,))
        d.execute("delete from messages where batch=? and pushed=0", (batch,))
