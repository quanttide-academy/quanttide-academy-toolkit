"""办理人角色（执行员 / 评审员 / 咨询对象）与用户本人的行动推导。
本人身份只按 open_id 匹配（config.self_open_id）；open_id 缺失的人永远不是本人。行动由程序推导：
本人 ∈ 执行员 → 执行；∈ 评审员 → 评审；∈ 咨询对象 → 问询。跟进清单里本人是跟进人的事项，关联它的条目按评审员处理。"""

from feishu_workflows.intent.watch_view import watched

ACTIONS = ["执行", "评审", "问询", "指派"]
ROLE_KEYS = (("assignees", "执行"), ("reviewers", "评审"), ("consultees", "问询"))
TASK_TYPE = {"personal": "个人任务", "team": "团队任务", "undetermined": "（待定）", None: "（待定）"}
PENDING = "（办理人待定）"
SYSTEM_SPEAKER = "（系统消息）"


def is_system_msg(m) -> bool:
    """sender 为空或标记为 system 的消息属于系统消息，显示「（系统消息）」，不参与角色推断。"""
    if not isinstance(m, dict):
        return False
    if m.get("system") is True or m.get("msg_type") == "system" or m.get("sender_type") == "system":
        return True
    if (m.get("speaker") or "").strip() == SYSTEM_SPEAKER:
        return True
    if "sender" in m:
        s = m.get("sender")
        if s is None or (isinstance(s, str) and not s.strip()):
            return True
        if isinstance(s, dict) and (s.get("sender_type") == "system" or not (s.get("id") or "").strip()):
            return True
    if "sender_open_id" in m and not (m.get("sender_open_id") or "").strip() and not (m.get("speaker") or "").strip():
        if m.get("sender_external") is None and m.get("url") is None:
            return True
    return False


def self_id(cfg):
    return (cfg or {}).get("self_open_id") or ((cfg or {}).get("user") or {}).get("open_id")


def is_self(p, cfg):
    me = self_id(cfg)
    oid = (p or {}).get("open_id")
    return bool(me and oid and oid == me)


def display(p, cfg):
    """姓名一律取 display_name：本人用 config user.display_name，其他人用记录里的 name。"""
    if is_self(p, cfg):
        return ((cfg or {}).get("user") or {}).get("display_name") or p.get("name") or "我"
    return (p or {}).get("name") or "（未知）"


def followup_reviewer(it, cfg):
    """关联的跟进事项里，本人是跟进人 → 本人按评审员处理；返回该事项标题或 None。"""
    me = self_id(cfg)
    if not me:
        return None
    for r in it.get("refs") or []:
        f = ((cfg or {}).get("_followup_followers") or {}).get(str(r).strip())
        if f and f.get("open_id") == me:
            return ((cfg or {}).get("_followup_titles") or {}).get(str(r).strip(), str(r))
    return None


def effective(it, cfg):
    """渲染与推导用的角色表：模型写的角色 + 跟进清单带来的评审员（不改原记录）；系统消息不参与角色推断。"""
    sys_ids = {lnk.get("message_id") for lnk in it.get("links") or [] if isinstance(lnk, dict) and is_system_msg(lnk)}
    R = {
        k: [
            dict(p)
            for p in it.get(k) or []
            if isinstance(p, dict)
            and (p.get("name") or "").strip() not in (SYSTEM_SPEAKER, "系统消息")
            and p.get("message_id") not in sys_ids
        ]
        for k, _ in ROLE_KEYS
    }
    t = followup_reviewer(it, cfg)
    if t and R["assignees"] and not any(is_self(p, cfg) for p in R["reviewers"]):
        R["reviewers"].append(
            {
                "name": display({"open_id": self_id(cfg)}, cfg),
                "open_id": self_id(cfg),
                "basis": "followup",
                "evidence": t,
            }
        )
    return R


def pending(it):
    return not [p for p in it.get("assignees") or [] if isinstance(p, dict)]


def is_task(it):
    """含执行任务：kind=task（或被「升格」转成任务）；kind=info 是纯资讯。"""
    return it.get("kind") != "info" or bool(it.get("promoted"))


def own_roles(it, cfg):
    """本人在原话（或角色推断、跟进清单、用户回复）里的角色行动，顺序固定为 执行、评审、问询。"""
    R = effective(it, cfg)
    return [a for k, a in ROLE_KEYS if any(is_self(p, cfg) for p in R[k])]


def approver(it, cfg):
    """v3：本人没有原话角色、而条目含执行任务（执行员是别人或待定）→ 本人是审批人，行动「指派」，basis=rule（只由程序推导）。"""
    if not is_task(it) or own_roles(it, cfg) or not self_id(cfg):
        return None
    why = "办理人待定" if pending(it) else "执行员是别人"
    return {"name": display({"open_id": self_id(cfg)}, cfg), "open_id": self_id(cfg), "basis": "rule", "evidence": why}


def derive_actions(it, cfg):
    """纯资讯不推导行动；任务：本人有角色就用角色，否则「指派」。"""
    if not is_task(it):
        return []
    return own_roles(it, cfg) or (["指派"] if approver(it, cfg) else [])


def category(it, cfg):
    """card：含执行任务，出卡（办理人待定也出卡）；info：纯资讯，进仅知悉。"""
    return "card" if is_task(it) else "info"


def actions_text(it, cfg):
    """行动行：按角色推断的注「（按角色推断：…）」，来自跟进清单的注「（跟进清单：…）」，审批人注「（按规则：…）」。"""
    R = effective(it, cfg)
    out = []
    ap = approver(it, cfg)
    if ap:
        return f"指派（按规则：{ap['evidence']}）"
    for k, a in ROLE_KEYS:
        mine = [p for p in R[k] if is_self(p, cfg)]
        if not mine:
            continue
        b = mine[0].get("basis")
        out.append(
            a
            + (
                f"（按角色推断：{mine[0].get('evidence')}）"
                if b == "role"
                else f"（跟进清单：{mine[0].get('evidence')}）"
                if b == "followup"
                else ""
            )
        )
    return "、".join(out) or "无"


def names(ps, cfg):
    return "、".join(display(p, cfg) for p in ps)


def assignees_text(it, cfg):
    return names(effective(it, cfg)["assignees"], cfg) or PENDING


def reviewers_text(it, cfg):
    rv = effective(it, cfg)["reviewers"]
    return " -> ".join(["执行员"] + [display(p, cfg) for p in rv]) if rv else "无"


def consultees_text(it, cfg):
    return names(effective(it, cfg)["consultees"], cfg) or "无"


def approver_text(it, cfg):
    ap = approver(it, cfg)
    return f"{ap['name']}（按规则：{ap['evidence']}）" if ap else None


def ddl_lines(it, cfg):
    """按人一行：「张三 2026-10-24（依据）」；本人名字换成 display_name。"""
    R = effective(it, cfg)
    who = {}
    for k, _ in ROLE_KEYS:
        for p in R[k]:
            who.setdefault(p.get("name"), p)
    out = []
    for e in it.get("ddl_by_person") or []:
        p = who.get(e.get("person"))
        n = display(p, cfg) if p else e.get("person")
        out.append(f"{n} {e.get('date')}（{e.get('basis') or '依据未写'}）")
    return out


def self_ddl(it, cfg):
    """本人的 DDL（Todoist deadline 用）；没有按人 DDL 时退回条目的截止日期。"""
    R = effective(it, cfg)
    mine = {p.get("name") for k, _ in ROLE_KEYS for p in R[k] if is_self(p, cfg)}
    for e in it.get("ddl_by_person") or []:
        if e.get("person") in mine:
            return e.get("date")
    if watched(it, cfg):
        return None  # 监听他人的条目：对方 DDL 只进描述，不退回条目截止
    return None if approver(it, cfg) else it.get("ddl")  # 指派卡：只有本人自己有 DDL 才填


def summary_line(it, cfg):
    """Todoist 描述首行。"""
    L = [
        f"行动：{actions_text(it, cfg)}",
        f"任务类型：{TASK_TYPE.get(it.get('task_type'), '（待定）')}",
        f"执行员：{assignees_text(it, cfg)}",
        f"评审：{reviewers_text(it, cfg)}",
        f"咨询：{consultees_text(it, cfg)}",
    ]
    if approver(it, cfg):
        L.append(f"审批人：{approver_text(it, cfg)}")
    return " ｜ ".join(L)
