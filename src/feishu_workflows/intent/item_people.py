"""条目人员占位符与角色块：resolve、person_text、speaker_text、role_block。"""

import re

from feishu_workflows.intent import roles
from feishu_workflows.intent.item_text import TEXT_FIELDS, esc, ref_title

PERSON = re.compile(r"\{person:(ou_[0-9A-Za-z_]+)\}")


def speaker_text(lnk, cfg=None):
    """依据行的发言人：系统消息或空 sender 显示「（系统消息）」；其余显示 display_name，外部成员加后缀「（外部成员）」，缺发言人写「（未知发言人）」。"""
    if roles.is_system_msg(lnk):
        return roles.SYSTEM_SPEAKER
    n = (lnk.get("speaker") or "").strip()
    if not n:
        return "（未知发言人）"
    return n + "（外部成员）" if lnk.get("sender_external") or not (cfg or {}).get("self_tenant_key") else n


def person_text(oid, links, cfg=None):
    """摘要占位符 {person:ou_xxx}：本人→display_name；发言人→与依据行相同的 speaker_text；被 @ 的人→姓名；查不到→（未知成员）。"""
    if oid == roles.self_id(cfg):
        return ((cfg or {}).get("user") or {}).get("display_name") or "我"
    for lnk in links:
        if lnk.get("sender_open_id") == oid:
            return speaker_text(lnk, cfg)
    for lnk in links:
        n = (lnk.get("people") or {}).get(oid)
        if n:
            return n
    return "（未知成员）"


def resolve(it, cfg=None):
    """渲染前处理：{display_name} 换成配置里的称呼；自由文本里的 F 编号换成跟进事项标题（编号只留在存档 fi 行）。"""
    name = ((cfg or {}).get("user") or {}).get("display_name") or "我"
    cjk = r"[\u4e00-\u9fff]"

    def put_name(v):
        if not isinstance(v, str):
            return v
        v = v.replace("{display_name}", "\x00")
        if re.fullmatch(r"[A-Za-z0-9 ._-]+", name):  # 拉丁称呼与汉字之间加空格
            v = re.sub(rf"(?<={cjk})\x00", "\x01", v)
            v = re.sub(rf"\x00(?={cjk})", "\x02", v)
            v = re.sub(rf"\x01(?={cjk})", "\x03", v)
            v = v.replace("\x03", " " + name + " ").replace("\x01", " " + name).replace("\x02", name + " ")
        return v.replace("\x00", name)

    o = dict(it)
    for k in TEXT_FIELDS:
        o[k] = put_name(o.get(k))
    if isinstance(o.get("summary"), str) and PERSON.search(o["summary"]):
        o["summary"] = PERSON.sub(lambda m: person_text(m.group(1), it.get("links") or [], cfg), o["summary"])
    if isinstance(o.get("summary"), str) and "{speaker}" in o["summary"]:  # 摘要与依据行共用 speaker_text
        links = it.get("links") or []
        main = next((lnk for lnk in links if lnk.get("message_id") == it.get("message_id")), links[0] if links else {})
        o["summary"] = o["summary"].replace("{speaker}", speaker_text(main, cfg))
    o["subtasks"] = [put_name(x) for x in it.get("subtasks") or []]
    o["_refs_raw"] = list(it.get("refs") or [])
    o["refs"] = [ref_title(r, cfg) for r in it.get("refs") or []]
    return o


def role_block(it, cfg, archive=False):
    """任务类型 / 执行员 / 评审员 / 咨询对象 / 评审标准（有才显示）/ DDL（按人一行）。"""
    f = (lambda k, v: f"- **{k}**：{v}") if archive else (lambda k, v: f"{k}：{v}")
    L = [
        f("任务类型", roles.TASK_TYPE.get(it.get("task_type"), "（待定）")),
        f("执行员", esc(roles.assignees_text(it, cfg))),
        f("评审员", esc(roles.reviewers_text(it, cfg)).replace(" -\\> ", " -> ")),
        f("咨询对象", esc(roles.consultees_text(it, cfg))),
    ]
    if roles.approver(it, cfg):
        L.append(f("审批人", esc(roles.approver_text(it, cfg))))
    if it.get("review_criteria"):
        L.append(f("评审标准", esc(it["review_criteria"])))
    L += [f("DDL", esc(x)) for x in roles.ddl_lines(it, cfg)] or [f("DDL", "无")]
    return L
