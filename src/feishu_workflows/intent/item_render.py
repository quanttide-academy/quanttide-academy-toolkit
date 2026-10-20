"""条目卡片与存档渲染：render_card、render_archive、card_version、task_title、description。"""

import hashlib

from feishu_workflows.intent import roles
from feishu_workflows.intent.item_people import resolve, role_block, speaker_text
from feishu_workflows.intent.item_text import (
    SELF_MARK,
    _card_link,
    _name,
    actions_text,
    date_text,
    ddl_text,
    esc,
    labels,
    link_text,
    none,
    remind_text,
    sanitize_quote,
)
from feishu_workflows.intent.section import role_line


def render_archive(it, cfg=None):
    """内部存档格式（不推给用户）。"""
    it = resolve(it, cfg)
    L = [
        f"### [#{it['no']}] {esc(it['title'])}",
        f"<!-- fi:id={it['no']} msg={','.join(lnk['message_id'] for lnk in it.get('links', []) if lnk.get('message_id')) or it.get('message_id', '')}{(' refs=' + ','.join(it['_refs_raw'])) if it['_refs_raw'] else ''} -->",
        *role_block(it, cfg, archive=True),
        f"- **日期**：{date_text(it)}",
        f"- **截止**：{ddl_text(it)}",
        f"- **提醒**：{remind_text(it)}",
        f"- **优先级**：{it.get('priority') or '无'}",
        f"- **标签**：{none(', '.join(labels(it, cfg)))}",
        f"- **行动**：{actions_text(it, cfg)}",
        "- **链接**：",
    ]
    L += ["  - " + link_text(lnk, cfg) for lnk in it.get("links", [])] or ["  - 无"]
    L.append("  - 关联：" + none("、".join(it.get("refs") or [])))
    L.append("- **子任务**：")
    L += ["  - [ ] " + esc(s) for s in it.get("subtasks", [])] or ["  - 无"]
    L.append(f"- **备注**：{none(it.get('note'))}")
    return "\n".join(L)


def render_card(it, cfg=None):
    """推给用户确认的任务卡片：不出现内部字段名、注释或跟进清单编号。"""
    it = resolve(it, cfg)
    p = it.get("priority")
    rl = role_line(it, cfg)
    L = (
        ([esc(rl)] if rl else [])
        + [f"【#{it['no']}】{esc(it['title'])}", esc(it.get("summary") or "无")]
        + (["来自外部群"] if any(lnk.get("external_chat") for lnk in it.get("links", [])) else [])
        + [
            "",
            *role_block(it, cfg),
            f"日期：{date_text(it)}",
            f"截止：{ddl_text(it)}",
            f"提醒：{remind_text(it)}",
            f"优先级：{p or '无'}",
            f"标签：{none('、'.join(labels(it, cfg)))}",
            f"行动：{actions_text(it, cfg)}",
            "",
            "依据",
        ]
    )
    links = sorted(it.get("links", []), key=lambda x: x.get("time", ""))
    me = f"（{_name(cfg)}）"
    L += [
        f"· {lnk.get('time', '')} {'「私聊」 ' if lnk.get('dm') else ''}{speaker_text(lnk, cfg)}：「{sanitize_quote(lnk.get('quote')).replace(SELF_MARK, me)}」 {_card_link(lnk, cfg)}"
        for lnk in links
    ] or ["· 无"]
    if it.get("refs"):
        L += ["", f"关联：{'、'.join(it['refs'])}"]
    L += ["", "子任务"] + [f"☐ {esc(s)}" for s in it.get("subtasks", [])] or ["无"]
    L += ["", f"备注：{none(it.get('note'))}"]
    return "\n".join(L)


def card_version(it, cfg=None):
    """卡片内容指纹：确认回复须与推送时的版本一致，卡片改过则旧确认作废。"""
    return hashlib.sha256(render_card(it, cfg).encode("utf-8")).hexdigest()[:12]


def task_title(it, cfg=None):
    """待办标题：指派卡写成用户自己的任务「指派：<任务名>」。"""
    t = resolve(it, cfg)["title"]
    return f"指派：{t}" if roles.approver(it, cfg) else t


def description(it, cfg=None):
    """写进待办描述：首行「行动：… ｜ 任务类型：… ｜ 执行员：… ｜ 评审：执行员 -> … ｜ 咨询：…」，其后评审标准、各人 DDL、依据、链接、备注。"""
    it = resolve(it, cfg)
    me = "（" + _name(cfg) + "）"
    L = [roles.summary_line(it, cfg)]
    if it.get("review_criteria"):
        L.append("评审标准：" + it["review_criteria"])
    dl = roles.ddl_lines(it, cfg)
    if dl:
        L.append("各人 DDL：" + "；".join(dl))
    L += [
        f"截止依据：{ddl_text(it)}",
        f"提醒：{remind_text(it)}",
        f"优先级：{it.get('priority') or '无'}",
        f"日期：{date_text(it)}",
        "链接：",
    ]
    L += [
        f"- {lnk.get('time', '')}「{sanitize_quote(lnk.get('quote')).replace(SELF_MARK, me)}」 " + link_text(lnk, cfg)
        for lnk in it.get("links", [])
    ]
    L.append("关联：" + none("、".join(it.get("refs") or [])))
    R = roles.effective(it, cfg)
    ev = []
    for k, a in (("assignees", "执行员"), ("reviewers", "评审员"), ("consultees", "咨询对象")):
        for p in R[k]:
            b = p.get("basis")
            src = {"quote": "原话", "role": "按角色推断", "followup": "跟进清单", "reply": "用户指定"}.get(b, b)
            ev.append(
                f"- {a} {roles.display(p, cfg)}：{src}「{sanitize_quote(p.get('evidence')).replace(SELF_MARK, me)}」"
            )
    if ev:
        L += ["角色依据："] + ev
    if it.get("labels"):
        L.append("业务标签：" + "、".join(it["labels"]))
    L.append("备注：" + none(it.get("note")))
    return "\n".join(L)


to_card = render_card
to_markdown = render_archive
