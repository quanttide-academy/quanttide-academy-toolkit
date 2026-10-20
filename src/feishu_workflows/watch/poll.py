"""watch 轮询：每个白名单群只拉一次（只读 GET），按发言人分给目标；游标写暂存表，commit 才推进。
产出的消息记录与 intent fetch 同格式（多 target、sender_open_id），之后复用 intent 的 validate/render。"""

import datetime
import json
from zoneinfo import ZoneInfo

from feishu_workflows.core import lark as larkcli
from feishu_workflows.core.config import TZ_NAME
from feishu_workflows.intent.item_text import SELF_MARK, msg_link, text_of
from feishu_workflows.intent.state import (
    THREAD_MAX,
    THREAD_TOTAL_MAX,
    trim_threads,
)
from feishu_workflows.watch import cursors, dm
from feishu_workflows.watch.dm import DmUnavailable  # noqa: F401  对外暴露
from feishu_workflows.watch.targets import owner

__all__ = ["DmUnavailable", "THREAD_MAX", "THREAD_TOTAL_MAX", "fetch", "poll", "record", "route", "trim_threads"]
TZ = ZoneInfo(TZ_NAME)


def route(items, targets, sp):
    """items：群消息原始记录；sp：该群起点 {start, targets:{key:起点}}。返回 [(目标键, 原始消息)]。"""
    own = owner(targets)
    out = []
    for m in items:
        s = m.get("sender") or {}
        if m.get("deleted") or s.get("sender_type") == "app" or m.get("sender_type") == "app":
            continue
        k = own.get(s.get("id"))
        if not k:
            continue
        if int(m["create_time"]) // 1000 >= sp["targets"].get(k, sp["start"]):
            out.append((k, m))
    return out


def fetch(cfg, cid, start, end):
    params = json.dumps(
        {
            "container_id_type": "chat",
            "container_id": cid,
            "start_time": str(start),
            "end_time": str(end),
            "page_size": 50,
            "sort_type": "ByCreateTimeAsc",
        }
    )
    return [
        m
        for page in larkcli.call(
            cfg, "api", "GET", "/open-apis/im/v1/messages", "--as", "user", "--page-all", "--params", params
        )
        for m in (page.get("data") or {}).get("items") or []
    ]


def record(cfg, chat, k, m, targets):
    t = text_of(m)
    me = cfg.get("self_open_id")
    ments = [x for x in m.get("mentions") or [] if isinstance(x, dict)]
    for x in ments:
        if me and x.get("id") == me and x.get("key"):
            t = t.replace(x["key"], SELF_MARK)
    mids = [x.get("id") for x in ments if x.get("id")]
    ts = int(m["create_time"]) // 1000
    sid = (m.get("sender") or {}).get("id")
    url, direct = msg_link(chat["chat_id"], m.get("message_position"))
    tg = next((t for t in targets if t.key == k), None)
    if tg is None or not sid or m.get("msg_type") == "system" or (m.get("sender") or {}).get("sender_type") == "system":
        return {
            "message_id": m["message_id"],
            "chat": chat.get("name"),
            "chat_id": chat["chat_id"],
            "target": k,
            "sender_open_id": None,
            "account": "系统消息",
            "time": datetime.datetime.fromtimestamp(ts, TZ).strftime("%m-%d %H:%M"),
            "parent_id": m.get("parent_id"),
            "link": url,
            "direct": direct,
            "text": t,
            "mentions": mids,
            "mentions_self": bool(me and me in mids),
            "speaker": "（系统消息）",
            "system": True,
            "external_chat": bool(chat.get("external")),
            "sender_tenant_key": None,
        }
    name = tg.name
    own = sid in tg.accounts
    rec = {
        "message_id": m["message_id"],
        "chat": chat.get("name"),
        "chat_id": chat["chat_id"],
        "target": k,
        "sender_open_id": sid,
        "account": f"{name}·{tg.accounts[sid]}" if own else "本人",
        "time": datetime.datetime.fromtimestamp(ts, TZ).strftime("%m-%d %H:%M"),
        "parent_id": m.get("parent_id"),
        "link": url,
        "direct": direct,
        "text": t,
        "mentions": mids,
        "mentions_self": bool(me and me in mids),
        "speaker": name if own else None,
        "external_chat": bool(chat.get("external")),
        "sender_tenant_key": (m.get("sender") or {}).get("tenant_key"),
    }
    if "thread_replies" in m:
        rec["thread_replies"] = list(m.get("thread_replies") or [])
    return rec


def _seen(d, batch, cid, mid):
    r = d.execute("select chat_id,batch,pushed from messages where message_id=?", (mid,)).fetchone()
    return bool(r and r[0] == cid and (r[2] == 1 or r[1] != batch))


def _remember(d, batch, cid, m, rec):
    with d:
        d.execute(
            """insert into messages(message_id,chat_id,sender,ts,text,batch,pushed,sender_tenant_key) values(?,?,?,?,?,?,0,?)
          on conflict(message_id) do update set chat_id=excluded.chat_id,sender=excluded.sender,ts=excluded.ts,text=excluded.text,
          sender_tenant_key=excluded.sender_tenant_key,batch=case when messages.pushed=1 then messages.batch else excluded.batch end""",
            (
                rec["message_id"],
                cid,
                rec["sender_open_id"],
                int(m["create_time"]) // 1000,
                rec["text"],
                batch,
                rec["sender_tenant_key"],
            ),
        )


def poll(cfg, d, batch, targets, init, end, dry_run=False):
    """返回 {messages, counts:{目标键:条数}, chats}；dry_run 时不写暂存游标。没有 scope 时什么都不拉。"""
    scope = (cfg or {}).get("scope")
    if scope is None:
        return {"messages": [], "counts": {}, "chats": 0}
    chats = scope.get("include_chats") or []
    msgs = []
    counts = {t.key: 0 for t in targets}
    marks = {}
    for c in chats:
        el = [t for t in targets if t.chats is None or c["chat_id"] in t.chats]  # 目标限定群：只在自己的群里取
        if not el:
            continue
        cid = c["chat_id"]
        seen = set()
        sp = cursors.start_points(d, el, [cid], init)[cid]
        items = fetch(cfg, cid, sp["start"], end)
        for k, m in route(items, el, sp):
            mid = m["message_id"]
            if mid in seen or _seen(d, batch, cid, mid):
                continue
            seen.add(mid)
            rec = record(cfg, c, k, m, targets)
            if not dry_run:
                _remember(d, batch, cid, m, rec)
            msgs.append(rec)
            counts[k] += 1
        if items:
            mx = max(int(m["create_time"]) // 1000 for m in items)
            for t in el:
                marks[(t.key, cid)] = mx
    for t in [t for t in targets if t.dm]:  # 私聊来源：只经 dm 模块，先核验再拉；失败抛 DmUnavailable，本轮整体停止
        seen = set()
        sp = cursors.start_points(d, [t], [t.dm_chat], init)[t.dm_chat]
        items, mx = dm.fetch(cfg, t, sp["start"], end)
        for m in items:
            mid = m["message_id"]
            if mid in seen or _seen(d, batch, t.dm_chat, mid):
                continue
            seen.add(mid)
            rec = {**record(cfg, {"chat_id": t.dm_chat, "name": f"私聊·{t.name}"}, t.key, m, targets), "dm": True}
            if not dry_run:
                _remember(d, batch, t.dm_chat, m, rec)
            msgs.append(rec)
            counts[t.key] += 1
        if mx is not None:
            marks[(t.key, t.dm_chat)] = mx
    trim_threads(msgs)
    if not dry_run:
        cursors.stage(d, batch, marks)
    return {"messages": msgs, "counts": counts, "chats": len(chats)}
