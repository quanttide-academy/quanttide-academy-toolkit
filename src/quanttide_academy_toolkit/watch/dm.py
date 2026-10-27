"""私聊来源（仅本人与监听目标之间的私聊）：唯一允许读私聊的模块，只读 GET，且只在该目标私聊开关打开时调用。
每次拉取前现场核验：会话必须是 p2p，成员必须恰好是本人与该目标；不信任配置里的 dm_chat_id。任何失败都报错停止，不静默跳过。"""

import json

from quanttide_academy_toolkit.core import lark as larkcli

PERM = "im:message.p2p_msg:get_as_user"


class DmUnavailable(RuntimeError):
    pass


def _get(cfg, t, *a):
    try:
        return larkcli.call(cfg, "api", "GET", *a)
    except larkcli.LarkError as e:
        raise DmUnavailable(f"目标「{t.name}」私聊读取失败：需要用户身份权限 {PERM}（可能尚未开通）；{e}") from e


def verify(cfg, t):
    """现场核验 dm_chat_id：chat_mode/chat_type 为 p2p，成员恰为 {本人, 该目标的一个账号}。"""
    if not t.dm or not t.dm_chat:
        raise DmUnavailable(f"目标「{t.name}」未开启私聊来源，拒绝读取私聊")
    me = (cfg or {}).get("self_open_id")
    if not me:
        raise DmUnavailable("未配置 self_open_id，无法核验私聊成员")
    info = (
        _get(cfg, t, f"/open-apis/im/v1/chats/{t.dm_chat}", "--as", "user", "--params", '{"user_id_type":"open_id"}')[
            0
        ].get("data")
        or {}
    )
    if "p2p" not in (info.get("chat_mode"), info.get("chat_type")):
        raise DmUnavailable(f"目标「{t.name}」的 dm_chat_id 不是私聊会话，停止")
    pages = _get(
        cfg,
        t,
        f"/open-apis/im/v1/chats/{t.dm_chat}/members",
        "--as",
        "user",
        "--page-all",
        "--params",
        '{"member_id_type":"open_id","page_size":100}',
    )
    mem = {x.get("member_id") for p in pages for x in (p.get("data") or {}).get("items") or []}
    if len(mem) != 2 or me not in mem or not (mem - {me}) <= set(t.accounts):
        raise DmUnavailable(f"目标「{t.name}」的私聊成员不是恰好本人与该目标，停止")


def fetch(cfg, t, start, end):
    """核验后只读拉取；返回 (本人或该目标发的、未删除、不早于 start 的消息, 本次见到的最大秒级时间戳或 None)。"""
    verify(cfg, t)
    me = cfg["self_open_id"]
    params = json.dumps(
        {
            "container_id_type": "chat",
            "container_id": t.dm_chat,
            "start_time": str(start),
            "end_time": str(end),
            "page_size": 50,
            "sort_type": "ByCreateTimeAsc",
        }
    )
    items = [
        m
        for p in _get(cfg, t, "/open-apis/im/v1/messages", "--as", "user", "--page-all", "--params", params)
        for m in (p.get("data") or {}).get("items") or []
    ]
    keep = [
        m
        for m in items
        if (m.get("sender") or {}).get("id") in {me, *t.accounts}
        and (m.get("sender") or {}).get("sender_type") != "app"
        and not m.get("deleted")
        and int(m["create_time"]) // 1000 >= start
    ]
    return keep, (max(int(m["create_time"]) // 1000 for m in items) if items else None)
