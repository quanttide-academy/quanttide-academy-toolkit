"""采集层：发现与监听对象同在的群，增量拉取其发言（只读，本人身份）。拉取与按发言人分配统一走 watch.poll（intent = 本人目标视角）；游标只写暂存表，推送成功后才推进。"""

import datetime
import json
from zoneinfo import ZoneInfo

from feishu_workflows.core import lark as larkcli
from feishu_workflows.core import paths
from feishu_workflows.core.config import TZ_NAME
from feishu_workflows.intent import names
from feishu_workflows.intent.item_text import SELF_MARK, msg_link, text_of
from feishu_workflows.watch import cursors as _cursors
from feishu_workflows.watch import poll as _poll
from feishu_workflows.watch import targets as _targets

__all__ = ["NO_SCOPE", "NoScope", "SELF_MARK", "list_chats", "msg_link", "run", "text_of"]
TZ = ZoneInfo(TZ_NAME)


class NoScope(RuntimeError):
    pass


NO_SCOPE = "未配置监听范围，请运行 setup chats"


def run(cfg, d, batch):
    if cfg.get("scope") is None:
        raise NoScope(NO_SCOPE)  # 没有白名单就什么都不拉，不调用任何消息接口
    ts = _targets.load(cfg)
    watch = _targets.owner(ts)
    tk = _targets.self_key(cfg, d)
    init = int(
        datetime.datetime.fromisoformat(str(cfg.get("initial_since", "2026-10-16"))).replace(tzinfo=TZ).timestamp()
    )
    now = _cursors._now()
    rep = {"batch": batch, "new_chats": [], "left_chats": [], "messages": []}
    seen = set()
    chats = larkcli.call(cfg, "im", "+chat-list", "--as", "user")[0]["data"]["chats"]
    scope = cfg.get("scope")
    inc = {str(x["chat_id"]): x for x in (scope.get("include_chats") or [])}
    rep["suggested_chats"] = []
    for c in chats:
        cid = c["chat_id"]
        if cid in inc:  # 白名单是主机制：直接监听，不靠成员检测
            seen.add(cid)
            if not d.execute("select 1 from watched_chats where chat_id=?", (cid,)).fetchone():
                d.execute(
                    "insert into watched_chats(chat_id,name,first_seen,last_checked,active) values(?,?,?,?,1)",
                    (cid, c.get("name"), now, now),
                )
                rep["new_chats"].append(c.get("name"))
            d.execute(
                "update watched_chats set last_checked=?,name=?,active=1 where chat_id=?", (now, c.get("name"), cid)
            )
            continue
        mem = json.dumps(
            larkcli.call(
                cfg,
                "api",
                "GET",
                f"/open-apis/im/v1/chats/{cid}/members",
                "--as",
                "user",
                "--page-all",
                "--params",
                '{"page_size":100}',
            )
        )
        if any(a in mem for a in watch):  # 部门群检测只做建议，不自动监听
            rep["suggested_chats"].append({"chat_id": cid, "name": c.get("name")})
    for cid, name in d.execute("select chat_id,name from watched_chats where active=1").fetchall():
        if cid not in seen:
            d.execute("update watched_chats set active=0 where chat_id=?", (cid,))
            rep["left_chats"].append(name)
    for cid, name in d.execute("select chat_id,name from watched_chats where active=1").fetchall():
        r = d.execute(
            "select last_ts from watch_cursors where target_key=? and chat_id=? and is_deleted=0", (tk, cid)
        ).fetchone()
        start = r[0] if r and r[0] is not None else init  # 同一秒的消息靠消息ID查重兜底
        end = int(datetime.datetime.now(TZ).timestamp())
        items = _poll.fetch(cfg, cid, start, end)
        mx = max([start - 1, *(int(m["create_time"]) // 1000 for m in items)])
        chat = {"chat_id": cid, "name": name, "external": bool(inc and inc.get(cid, {}).get("external"))}
        for k, m in _poll.route(
            items, ts, {"start": 0, "targets": {}}
        ):  # 拉取与按发言人分配统一走 watch；intent = 本人目标视角
            r = _poll.record(cfg, chat, k, m, ts)
            r.pop("target", None)  # intent 原格式不变（无 target 字段）
            ex = d.execute("select batch,pushed from messages where message_id=?", (r["message_id"],)).fetchone()
            d.execute(
                """insert into messages(message_id,chat_id,sender,ts,text,batch,pushed,sender_tenant_key) values(?,?,?,?,?,?,0,?)
              on conflict(message_id) do update set chat_id=excluded.chat_id,sender=excluded.sender,ts=excluded.ts,text=excluded.text,
              sender_tenant_key=excluded.sender_tenant_key,batch=case when messages.pushed=1 then messages.batch else excluded.batch end""",
                (
                    r["message_id"],
                    cid,
                    r["sender_open_id"],
                    int(m["create_time"]) // 1000,
                    r["text"],
                    batch,
                    r["sender_tenant_key"],
                ),
            )
            if ex and (ex[1] == 1 or ex[0] != batch):
                continue  # 已推送或前序批次已收过：只更新元数据，不再出卡片
            rep["messages"].append(r)
        _cursors.stage(d, batch, {(tk, cid): mx})
    rep["names_resolved"] = names.fill(cfg, rep["messages"], paths.name_cache(cfg))
    names.departments(cfg, paths.dept_cache(cfg))  # 部门名豁免表（只读，7 天缓存）
    return rep


def list_chats(cfg):
    """setup 用：列出本人已加入的群（只读），供勾选白名单。"""
    return [
        {"chat_id": c["chat_id"], "name": c.get("name"), "external": bool(c.get("external"))}
        for c in larkcli.call(cfg, "im", "+chat-list", "--as", "user")[0]["data"]["chats"]
    ]
