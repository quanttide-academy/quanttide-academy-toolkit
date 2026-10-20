"""org 审批来源核验：批准必须是本人在审批单聊里亲手发的「批准 <计划ID前8位>」，以 message_id 为凭证。
现场用应用身份只读取回该消息，核验：发送人是本人（sender_type=user）、会话是 org.approval_chat_id、发送时间在计划生成之后 24 小时内、
文本恰为「批准 <id8>」（建群/解散/转让须逐条「批准 <id8> <序号>」）。每个 message_id 只能用一次；apply 前再全部核验一遍。
残余风险：本机上任何持有本人用户令牌的进程都能以本人名义发出这条消息，元数据无法区分客户端手打与接口发送（见 ROADMAP.md）。"""

import datetime
import json
import re
from zoneinfo import ZoneInfo

from feishu_workflows.org import conf as C
from feishu_workflows.org import read as R
from feishu_workflows.org.plan import EXTRA_KINDS

WINDOW = 24 * 3600
TEXT = re.compile(r"批准 ([0-9a-f]{8})(?: (\d+))?")


class ApprovalError(ValueError):
    pass


def parse_ts(v) -> datetime.datetime:
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        n = int(v)
        sec, ms = divmod(n, 1000) if n >= 10**11 else (n, 0)
        return datetime.datetime.fromtimestamp(sec, datetime.timezone.utc).replace(microsecond=ms * 1000)
    s = str(v).strip()
    dt = datetime.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    return (dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)).astimezone(datetime.timezone.utc)


def _utc(s):
    return int(parse_ts(s).timestamp())


def ms_to_utc(ms: int) -> str:
    sec, rem = divmod(int(ms), 1000)
    return f"{datetime.datetime.fromtimestamp(sec, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')}.{rem:03d}Z"


def bj(ts):
    return parse_ts(ts).astimezone(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S") + "（北京时间）"


def find(d, prefix, statuses):
    rows = d.execute(
        "select plan_id,items_json,status,approved_items,created_at from org_plans where plan_id like ? and is_deleted=0",
        (prefix + "%",),
    ).fetchall()
    if len(rows) != 1:
        raise ApprovalError(f"找不到唯一的计划 {prefix}（匹配 {len(rows)} 个）")
    pid, items, st, ap, _ = rows[0]
    if st not in statuses:
        raise ApprovalError(f"计划 {prefix} 状态为 {st}，不能执行此操作")
    return pid, json.loads(items), st, json.loads(ap) if ap else None


def verify(cfg, d, message_id, statuses, reader=R):
    """返回 (plan_id, items, 序号或 None, 消息)；任何一项不符抛 ApprovalError。"""
    if not message_id:
        raise ApprovalError("缺审批消息的 message_id（批准必须来自本人在审批单聊里发的消息）")
    oc = C.load(cfg)
    me = (cfg or {}).get("self_open_id")
    if not oc.approval_chat_id:
        raise ApprovalError("未配置 org.approval_chat_id，无法核验批准来源")
    if not me:
        raise ApprovalError("未配置 self_open_id")
    try:
        m = reader.approval_message(cfg, message_id)
    except R.ChatReadError as e:
        raise ApprovalError(f"取不到审批消息：{e}") from e
    if m["message_id"] != message_id or m["deleted"]:
        raise ApprovalError("审批消息不存在或已删除")
    if m["chat_id"] != oc.approval_chat_id:
        raise ApprovalError("审批消息不在审批单聊里")
    if m["sender"] != me or m["sender_type"] != "user":
        raise ApprovalError("审批消息不是本人发的")
    t = TEXT.fullmatch(m["text"] or "") if m["msg_type"] == "text" else None
    if not t:
        raise ApprovalError("审批文本必须恰为「批准 <计划ID前8位>」")
    rows = d.execute(
        "select plan_id,created_at from org_plans where plan_id like ? and is_deleted=0", (t.group(1) + "%",)
    ).fetchall()
    if len(rows) != 1:
        raise ApprovalError("审批文本里的计划 ID 与计划不符")
    pid, items, _, _ = find(d, t.group(1), statuses)
    sent = m["create_ms"] // 1000
    made = _utc(rows[0][1])
    if sent < made:
        raise ApprovalError("审批消息早于计划生成，无效")
    if sent > made + WINDOW:
        raise ApprovalError("审批消息晚于计划生成 24 小时，已过期，请重新 plan")
    n = int(t.group(2)) if t.group(2) else None
    if n is not None and not any(it["idx"] == n and it["kind"] in EXTRA_KINDS for it in items):
        raise ApprovalError("带序号的批准只用于建群/解散/转让条目")
    return pid, items, n, m


def approve(cfg, d, message_id, reader=R):
    pid, items, n, m = verify(cfg, d, message_id, ("pending", "approved"), reader)
    if d.execute("select 1 from org_approvals where message_id=?", (message_id,)).fetchone():
        raise ApprovalError("这条审批消息已经用过，不能重复使用")
    st = d.execute("select status,approved_items from org_plans where plan_id=?", (pid,)).fetchone()
    prev = json.loads(st[1]) if st[1] else []
    chosen = (
        sorted(set(prev) | {n})
        if n is not None
        else sorted(set(prev) | {it["idx"] for it in items if it["kind"] not in EXTRA_KINDS})
    )
    with d:
        d.execute(
            "insert into org_approvals(message_id,plan_id,sender,chat_id,sent_at,text) values(?,?,?,?,?,?)",
            (message_id, pid, m["sender"], m["chat_id"], ms_to_utc(m["create_ms"]), m["text"]),
        )
        d.execute(
            "update org_plans set status='approved',approved_items=?,approval_text=?,approved_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') where plan_id=?",
            (json.dumps(chosen), m["text"], pid),
        )
    return {
        "plan_id": pid,
        "approved": chosen,
        "approval_sent_at": bj(m["create_ms"] // 1000),
        "skipped_extra": [it["idx"] for it in items if it["kind"] in EXTRA_KINDS and it["idx"] not in chosen],
    }


def reverify(cfg, d, pid, reader=R):
    """apply 前：该计划登记过的每条审批消息都重新现场核验；返回最早一条的发送时间（北京时间）。"""
    rows = d.execute(
        "select message_id from org_approvals where plan_id=? and is_deleted=0 order by sent_at", (pid,)
    ).fetchall()
    if not rows:
        raise ApprovalError("计划没有登记的审批消息，拒绝执行")
    sent = []
    for (mid,) in rows:
        p, _, _, m = verify(cfg, d, mid, ("approved", "applying"), reader)
        if p != pid:
            raise ApprovalError("审批消息对应的计划不符")
        sent.append(m["create_ms"] // 1000)
    return [bj(s) for s in sent]
