"""topics.json 校验器（只用标准库，规则与 src/quanttide_academy/intent/schemas/topics.schema.json 一致）。宿主大模型的输出视为外部输入，不合格一律拒绝。"""

import datetime
import json
import re
from zoneinfo import ZoneInfo

from quanttide_academy.intent import validate_roles
from quanttide_academy.intent.item import FID, PERSON
from quanttide_academy.intent.state import sanitize_text
from quanttide_academy.settings import PKG

SCHEMA = PKG / "intent" / "schemas" / "topics.schema.json"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _real_date(s, fmt):
    try:
        datetime.datetime.strptime(s, fmt)
        return True
    except ValueError:
        return False


def validate(data, messages=None, cfg=None, promoted=()):
    """返回错误列表（空表示通过）。messages: {message_id: text}，给了就校验来源存在。"""
    sc = schema()["properties"]["items"]["items"]
    req = sc["required"]
    props = sc["properties"]
    meta = {}
    if messages is not None:
        meta = {k: (v if isinstance(v, dict) else {"text": v}) for k, v in messages.items()}
        messages = {k: str(v.get("text") or "") for k, v in meta.items()}
    E = []
    if not isinstance(data, dict) or set(data) != {"items"} or not isinstance(data.get("items"), list):
        return ['顶层必须是 {"items": [...]}']
    lc = (cfg or {}).get("labels") or {}
    derived = set((lc.get("priority_names") or {}).values()) | {"跟进"}
    seen = set()
    for i, it in enumerate(data["items"]):
        w = f"items[{i}]"
        if not isinstance(it, dict):
            E.append(f"{w} 不是对象")
            continue
        for k in req:
            if k not in it:
                E.append(f"{w} 缺字段 {k}")
        for k in it:
            if k not in props and k != "approvers":  # approvers 由 validate_roles 给出具体原因
                E.append(f"{w} 多出字段 {k}（url/direct/time 等由程序填，宿主不要写）")
        if E and any(e.startswith(w) for e in E):
            continue
        n = it["no"]
        w = f"#{n}" if isinstance(n, int) else w
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            E.append(f"{w} no 必须是正整数")
        elif n in seen:
            E.append(f"{w} 序号重复")
        seen.add(n)
        for k, mx in (("title", 60), ("summary", 200)):
            if not isinstance(it[k], str) or not it[k].strip():
                E.append(f"{w} {k} 不能为空")
            elif len(it[k]) > mx:
                E.append(f"{w} {k} 超过 {mx} 字")
        for k, b, rx, fmt, name in (
            ("date", "date_basis", DATE, "%Y-%m-%d", "YYYY-MM-DD"),
            ("ddl", "ddl_basis", DATE, "%Y-%m-%d", "YYYY-MM-DD"),
            ("remind", "remind_basis", DT, "%Y-%m-%d %H:%M", "YYYY-MM-DD HH:MM"),
        ):
            v = it[k]
            if v is not None and (not isinstance(v, str) or not rx.match(v) or not _real_date(v, fmt)):
                E.append(f"{w} {k} 必须是 {name} 或 null")
            if it[b] is not None and not isinstance(it[b], str):
                E.append(f"{w} {b} 必须是字符串或 null")
            if (v is None or k == "ddl") and not (isinstance(it[b], str) and it[b].strip()):
                E.append(f"{w} {k} 为待定或有截止时必须写 {b}（依据/原因）")
        if it["priority"] not in ("P1", "P2", "P3", "P4", None):
            E.append(f"{w} priority 只能是 P1–P4 或 null")
        elif (
            it["priority"] in ("P3", "P4")
            and isinstance(it["ddl"], str)
            and DATE.match(it["ddl"])
            and _real_date(it["ddl"], "%Y-%m-%d")
        ):
            if (
                datetime.date.fromisoformat(it["ddl"]) - datetime.datetime.now(ZoneInfo("Asia/Shanghai")).date()
            ).days <= 2:
                E.append(f"{w} 截止在 2 天内，优先级至少 P2（现在是 {it['priority']}）")
        E += validate_roles.check(it, w, messages, meta, cfg, promoted)
        if not isinstance(it["labels"], list) or not all(isinstance(x, str) for x in it["labels"]):
            E.append(f"{w} labels 必须是字符串数组")
        elif derived & set(it["labels"]):
            E.append(f"{w} labels 只放业务标签，优先级标签和跟进由程序推导：{sorted(derived & set(it['labels']))}")
        links = it["links"]
        if not isinstance(links, list) or not links:
            E.append(f"{w} links 至少一条")
        else:
            for j, lnk in enumerate(links):
                if not isinstance(lnk, dict) or set(lnk) != {"message_id", "quote"}:
                    E.append(f"{w} links[{j}] 只能含 message_id 和 quote")
                    continue
                if (
                    not isinstance(lnk["message_id"], str)
                    or not isinstance(lnk["quote"], str)
                    or not lnk["quote"].strip()
                    or len(lnk["quote"]) > 60
                ):
                    E.append(f"{w} links[{j}] message_id/quote 不合格（quote 1–60 字）")
                    continue
                if messages is not None:
                    if lnk["message_id"] not in messages:
                        E.append(f"{w} links[{j}] 消息 {lnk['message_id']} 不在 messages.json 里")
                    else:
                        head = re.sub(r"\s+", "", sanitize_text(lnk["quote"]).rstrip("…").strip())[:8]
                        if head and head not in re.sub(r"\s+", "", messages[lnk["message_id"]]):
                            E.append(f"{w} links[{j}] quote 不是该消息的原话")
        refs = it["refs"]
        rr = it["refs_reason"]
        if not isinstance(refs, list) or not all(isinstance(x, str) and x.strip() for x in refs):
            E.append(f"{w} refs 必须是字符串数组")
        elif refs and not (isinstance(rr, str) and re.search(r"「[^」]+」", rr)):
            E.append(f"{w} refs 非空时 refs_reason 必须给出用「」括起的原话证据")
        if not isinstance(it["subtasks"], list) or not all(isinstance(x, str) and x.strip() for x in it["subtasks"]):
            E.append(f"{w} subtasks 必须是非空字符串数组")
        elif any("本人" in x for x in it["subtasks"]):
            E.append(f"{w} subtasks 不能写「本人」，称呼用户请写 {{display_name}}")
        ftitles = [t for t in ((cfg or {}).get("_followup_titles") or {}).values() if t]
        body = [(k, it.get(k)) for k in ("title", "summary", "note", "date_basis", "ddl_basis", "remind_basis")] + [
            ("subtasks", x) for x in it["subtasks"] if isinstance(it["subtasks"], list)
        ]
        for k, v in body:
            if isinstance(v, str) and FID.search(v):
                E.append(
                    f"{w} {k} 里不能写跟进编号（{FID.search(v).group()}），请写具体短语，如「等运营部、游戏部审批结果」；编号只放 refs"
                )
            elif isinstance(v, str) and any(t in v for t in ftitles):
                E.append(f"{w} {k} 里不能照抄跟进事项标题，请写具体短语；标题只在卡片关联行显示")
        E += _person_checks(it, w, meta, cfg)
        if it["note"] is not None and not isinstance(it["note"], str):
            E.append(f"{w} note 必须是字符串或 null")
        if it["written"] is not False:
            E.append(f"{w} written 必须为 false（写入只由用户确认决定）")
    return E


def warnings(data, known_followups, cfg=None):
    """不阻断的提醒：引用了跟进清单里没有的编号；像用户但没有 open_id 的成员。"""
    W = []
    for it in (data or {}).get("items") or []:
        W += validate_roles.warnings(it, cfg)
        for r in it.get("refs") or []:
            if FID.fullmatch(str(r).strip()) and str(r).strip() not in known_followups:
                W.append(f"#{it.get('no')} 关联的 {r} 不在跟进清单里，卡片将显示「（未知关联）」")
    return W


def _person_checks(it, w, meta, cfg):
    sm = it.get("summary")
    if not isinstance(sm, str) or not meta:
        return []
    cache = dict((cfg or {}).get("_name_cache") or {})
    E = []
    allowed = set()
    known = set(cache.values())
    for lnk in it.get("links") or []:
        m = meta.get(lnk.get("message_id") if isinstance(lnk, dict) else None) or {}
        allowed |= {x for x in [m.get("sender_open_id"), *(m.get("mentions") or [])] if x}
        ppl = m.get("people") or {}
        known |= {n for n in ppl.values() if n}
        cache.update(ppl)
        txt = str(m.get("text") or "")
        by = {}
        for oid, n in cache.items():
            if n and len(n) >= 2 and n in txt:
                by.setdefault(n, set()).add(oid)
        allowed |= {next(iter(v)) for v in by.values() if len(v) == 1}  # 点名但没 @：姓名唯一对上才加
    for oid in PERSON.findall(sm):
        if oid not in allowed:
            E.append(f"{w} summary 的 {{person:{oid}}} 不是所引消息的发言人、被 @ 或点名的人")
    bare = PERSON.sub("", sm).replace("{display_name}", "").replace("{speaker}", "")
    for dn in sorted((cfg or {}).get("_dept_names") or [], key=len, reverse=True):
        bare = bare.replace(dn, "")
    for n in sorted(n for n in known if len(n) >= 2 and n in bare):
        E.append(f"{w} summary 里直接写了成员名字「{n}」，请改成 {{person:open_id}}")
    return E
