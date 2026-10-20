"""办理人角色字段的校验（validate.py 调用）。不合格一律拒绝，错误信息直接告诉宿主怎么改。"""

import datetime
import re

from quanttide_academy.intent import roles as R
from quanttide_academy.intent.state import sanitize_text

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PKEYS = {"name", "open_id", "basis", "evidence", "message_id"}


def _date_ok(s):
    if not (isinstance(s, str) and DATE.match(s)):
        return False
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _quote_ok(q, text):
    head = re.sub(r"\s+", "", sanitize_text(q).rstrip("…").strip())[:8]
    return bool(head) and head in re.sub(r"\s+", "", text)


def check(it, w, messages, meta, cfg, promoted=()):
    E = []
    user = (cfg or {}).get("user") or {}
    my_roles = [str(r) for r in user.get("roles") or []]
    my_names = [n for n in [user.get("display_name")] + list(user.get("names") or []) if n]
    links = it.get("links") if isinstance(it.get("links"), list) else []
    link_ids = {lnk.get("message_id") for lnk in links if isinstance(lnk, dict)}
    members = []
    for key, label in (("assignees", "执行员"), ("reviewers", "评审员"), ("consultees", "咨询对象")):
        ps = it.get(key)
        if not isinstance(ps, list):
            E.append(f"{w} {key} 必须是数组")
            continue
        for j, p in enumerate(ps):
            at = f"{w} {key}[{j}]（{label}）"
            if not isinstance(p, dict) or not {"name", "open_id", "basis", "evidence"} <= set(p) <= PKEYS:
                E.append(f"{at} 须含 name、open_id、basis、evidence，按原话时另加 message_id")
                continue
            if not isinstance(p["name"], str) or not p["name"].strip():
                E.append(f"{at} name 不能为空")
                continue
            if p["open_id"] is not None and not (isinstance(p["open_id"], str) and p["open_id"].startswith("ou_")):
                E.append(f"{at} open_id 只能是 ou_ 开头的字符串或 null")
            if not isinstance(p["evidence"], str) or not p["evidence"].strip():
                E.append(f"{at} 缺依据（evidence）")
                continue
            if p["name"].strip() in (R.SYSTEM_SPEAKER, "系统消息"):
                E.append(f"{at} 系统消息不参与角色推断")
                continue
            members.append(p)
            me = R.is_self(p, cfg)
            if p["basis"] == "quote":
                mid = p.get("message_id")
                if not isinstance(mid, str) or mid not in link_ids:
                    E.append(f"{at} 按原话须给 message_id，且该消息也列在 links 里")
                    continue
                if meta and mid in meta and R.is_system_msg(meta[mid]):
                    E.append(f"{at} 系统消息（{mid}）不参与角色推断")
                    continue
                if messages is not None and mid in messages:
                    if not _quote_ok(p["evidence"], messages[mid]):
                        E.append(f"{at} evidence 不是该消息的原话")
                    else:
                        m = meta[mid]
                        internal = not m.get("sender_external")
                        named = any(n in messages[mid] for n in my_names)
                        if me and not (m.get("mentions_self") or (internal and named)):
                            E.append(
                                f"{at} "
                                + (
                                    "外部成员的消息只认 @ 用户（mentions_self），只写名字不算"
                                    if named
                                    else "该消息没有 @ 或点名用户"
                                )
                                + f"，不能按原话把用户判为{label}，只能按角色推断（basis=role）"
                            )
                        elif not me and p["name"] in my_names and internal and (m.get("mentions_self") or named):
                            E.append(f"{at} 内部成员 @ 或点名的是用户本人，open_id 必须写用户的 open_id")
            elif p["basis"] == "role":
                if meta and link_ids and all(R.is_system_msg(meta.get(lid) or {}) for lid in link_ids):
                    E.append(f"{at} 系统消息不参与角色推断")
                if me and p["evidence"] not in my_roles:
                    E.append(f"{at} 按角色推断用户时，evidence 须是 config user.roles 里的角色：{my_roles}")
            elif p["basis"] == "reply":
                if it.get("no") not in promoted:
                    E.append(f"{at} basis=reply 只由程序在用户「升格」「指派」「改派」时写入，宿主不要写")
            elif p["basis"] == "rule":
                E.append(f"{at} basis=rule（审批人）只由程序推导，宿主不能写")
            else:
                E.append(
                    f"{at} basis 只能取 quote、role、reply、rule 之一（{p['basis']!r} 不认识）：quote=原话点名，role=按角色推断（仅限用户本人是唯一执行员）；reply=用户回复「升格/指派/改派」时由程序写入，rule=审批人由程序推导，这两种宿主都不要写"
                )
    A = it.get("assignees") if isinstance(it.get("assignees"), list) else []
    for key, label in (("reviewers", "评审员"), ("consultees", "咨询对象")):  # 按角色推断只用于执行员
        for j, p in enumerate(it.get(key) or []):
            if isinstance(p, dict) and p.get("basis") == "role":
                E.append(
                    f"{w} {key}[{j}]（{label}）不能按角色推断，只能按原话（basis=quote）；原话没点到用户就不要放进{label}"
                )
    for j, p in enumerate(A):
        if isinstance(p, dict) and p.get("basis") == "role" and not (R.is_self(p, cfg) and len(A) == 1):
            E.append(
                f"{w} assignees[{j}] 按角色推断只允许「用户本人是唯一执行员、原话没点名任何执行员」的情形；原话点名了执行员时，用户只能按原话进评审员或咨询对象"
            )
    tt = it.get("task_type")
    if tt not in ("personal", "team", "undetermined", None):
        E.append(f"{w} task_type 只能是 personal、team 或 undetermined")
    elif tt is None and A:
        E.append(f"{w} 已有执行员时 task_type 不能为空")
    elif tt == "personal" and len(A) != 1:
        E.append(
            f"{w} 个人任务（personal）的执行员必须恰好 1 人，现在 {len(A)} 人；判断不了类型或推断不出办理人请用 undetermined 并留空 assignees"
        )
    rc = it.get("review_criteria")
    if rc is not None and not (isinstance(rc, str) and rc.strip()):
        E.append(f"{w} review_criteria 必须是非空字符串或 null")
    D = it.get("ddl_by_person")
    if not isinstance(D, list):
        E.append(f"{w} ddl_by_person 必须是数组")
    else:
        names = {p["name"] for p in members}
        for j, e in enumerate(D):
            at = f"{w} ddl_by_person[{j}]"
            if not isinstance(e, dict) or set(e) != {"person", "date", "basis"}:
                E.append(f"{at} 只能含 person、date、basis")
                continue
            if not _date_ok(e["date"]):
                E.append(f"{at} date 必须是 YYYY-MM-DD")
            if not (isinstance(e["basis"], str) and e["basis"].strip()):
                E.append(f"{at} 缺 basis（依据）")
            if e["person"] not in names:
                E.append(f"{at} 的「{e['person']}」不在执行员、评审员或咨询对象里")
    if it.get("approvers"):
        E.append(
            f"{w} 不要写 approvers：审批人只由程序推导（basis=rule）"
            + ("；用户已有原话角色时更不能再叠加审批人" if R.own_roles(it, cfg) else "")
        )
    if it.get("kind") == "info":
        if A:
            E.append(f"{w} 纯资讯（kind=info）不能有执行员；有人要办就是 task")
        if it.get("subtasks") or it.get("ddl") or it.get("ddl_by_person"):
            E.append(f"{w} 含执行任务（子任务或截止）却标成纯资讯，会进仅知悉——请改为 kind=task")
    elif it.get("kind") != "task":
        E.append(f"{w} kind 只能是 task 或 info")
    if "actions" in it:
        got = it["actions"]
        want = R.derive_actions(it, cfg)
        if not isinstance(got, list) or any(a not in R.ACTIONS for a in got):
            E.append(f"{w} actions 只能取 执行/评审/问询/指派（也可以不写，由程序推导）")
        elif got != want:
            E.append(
                f"{w} actions {got} 与角色推导结果 {want} 不一致（本人按 open_id 匹配：执行员→执行，评审员→评审，咨询对象→问询；都不是且为任务→指派）"
            )
    return E


def warnings(it, cfg):
    """不阻断：名字像用户但没有 open_id 或 open_id 不同，不会被判为用户。"""
    W = []
    user = (cfg or {}).get("user") or {}
    my = [n for n in [user.get("display_name")] + list(user.get("names") or []) if n]
    for key in ("assignees", "reviewers", "consultees"):
        for p in it.get(key) or []:
            if isinstance(p, dict) and p.get("name") in my and not R.is_self(p, cfg):
                W.append(f"#{it.get('no')} 的「{p.get('name')}」没有你的 open_id，不按你本人处理")
    return W
