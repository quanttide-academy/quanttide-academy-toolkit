"""流程：采集结果落盘、校验入库、渲染卡片。"""

import json

from quanttide_academy.intent import names as _names
from quanttide_academy.intent import roles
from quanttide_academy.intent.item import (
    card_version,
    esc,
    render_archive,
    render_card,
    resolve,
)
from quanttide_academy.intent.section import section
from quanttide_academy.intent.state import (
    Invalid,
    _external,  # noqa: F401
    batch_items,
    clean,
    messages,
    rj,
    set_state,
    state,
    wd,
    wj,
)
from quanttide_academy.intent.status import label
from quanttide_academy.intent.validate import validate
from quanttide_academy.intent.validate import warnings as _warn


def fingerprint(it):
    return "om:" + it["links"][0]["message_id"]


def validate_batch(cfg, d, batch):
    p = wd(cfg, batch) / "topics.json"
    data = rj(p)
    if data is None:
        raise Invalid(f"没有 {p.name}：宿主需按 src/quanttide_academy/intent/prompts/classify.md 生成")
    st = state(cfg, batch)
    promoted = {int(k) for k in (st.get("promoted") or {})}
    replied = promoted | {int(k) for k in (st.get("assigned") or {})}  # basis=reply 只允许出现在用户回复改过的条目上
    cfg["_name_cache"] = _names.known(cfg)
    cfg["_dept_names"] = _names.dept_names(cfg)  # 本地缓存，不联网
    msgs = messages(cfg, batch)
    errs = validate(data, msgs, cfg, replied)
    if errs:
        raise Invalid("topics.json 校验失败：\n- " + "\n- ".join(errs[:30]))
    warns = _warn(data, (cfg.get("_followup_titles") or {}), cfg)
    if not cfg.get("self_tenant_key"):
        warns.append("未配置 self_tenant_key：所有发言人按外部成员处理，只有 @ 了用户的消息才能按原话把用户放进角色")
    items = []
    for it in data["items"]:
        it = dict(it)
        ls = []
        if it["no"] in promoted:
            it["promoted"] = True
        it["actions"] = roles.derive_actions(it, cfg)
        for lnk in it["links"]:
            m = msgs[lnk["message_id"]]
            sys_m = roles.is_system_msg(m)
            ls.append(
                {
                    **lnk,
                    "url": m.get("url"),
                    "direct": bool(m.get("direct")),
                    "time": m.get("time") or "",
                    "chat": m.get("chat"),
                    "speaker": roles.SYSTEM_SPEAKER if sys_m else m.get("speaker"),
                    "external_chat": bool(m.get("external_chat")),
                    "sender_external": bool(m.get("sender_external")),
                    "sender_open_id": m.get("sender_open_id"),
                    "people": m.get("people") or {},
                    **({"system": True} if sys_m else {}),
                    **({"dm": True} if m.get("dm") else {}),
                    **({"target": m["target"]} if m.get("target") else {}),
                }
            )
        it["links"] = sorted(ls, key=lambda x: x["time"])
        it["message_id"] = it["links"][0]["message_id"]
        it["fingerprint"] = fingerprint(it)
        items.append(it)
    with d:
        for it in items:
            js = json.dumps(it, ensure_ascii=False, sort_keys=True)
            r = d.execute("select item_json,status from topics where fingerprint=?", (it["fingerprint"],)).fetchone()
            if r is None:
                d.execute(
                    "insert into topics(fingerprint,title,status,relation,batch,item_json,origin) values(?,?,'pending',?,?,?,'识别')",
                    (it["fingerprint"], it["title"], "、".join(it["actions"]) or "仅知悉", batch, js),
                )
            elif r[0] != js:  # 内容变了：旧确认作废
                d.execute(
                    "update topics set title=?,relation=?,batch=?,item_json=?,confirmed=0,confirmed_version=null,status=case when status in ('written','rejected') then status else 'pending' end where fingerprint=?",
                    (it["title"], "、".join(it["actions"]) or "仅知悉", batch, js, it["fingerprint"]),
                )
    set_state(cfg, batch, stage="validated", items=[it["fingerprint"] for it in items], needs_edit=[], warnings=warns)
    return items


def sections(pairs, cfg):
    """合并批次按监听对象分节（本人在前，其余按首次出现）；只有一个分节时不加标题。序号沿用条目自身的 #N。"""
    groups = {}
    for it, c in pairs:
        groups.setdefault(section(it, cfg), []).append(c)
    if len(groups) <= 1:
        return [c for _, c in pairs]
    order = sorted(groups, key=lambda k: k != "本人")
    return [x for k in order for x in [f"—— {k} ——", *groups[k]]]


FOOTER = "可以直接回复：写入、修改、说明或否决（可带序号）。"


def render_batch(cfg, d, batch):
    items = batch_items(cfg, d, batch)
    w = wd(cfg, batch)
    rejected = {r[0] for r in d.execute("select fingerprint from rejections")}
    cards, fyi, skipped, vers, pend = [], [], [], {}, {}
    info = 0
    assign = 0
    for it in items:
        c = clean(it)
        cat = roles.category(c, cfg)
        t = esc(resolve(it, cfg)["title"])
        if it["fingerprint"] in rejected or it["_status"] == "rejected":
            skipped.append(f"#{it['no']} {t}（{label('rejected')}，不再推）")
        elif it["_status"] == "written":
            skipped.append(f"#{it['no']} {t}（{label('written')}）")
        elif cat == "info":  # 纯资讯：只给标题和来源群，可「升格 #N」转成任务
            g = (
                "、".join(
                    dict.fromkeys(
                        "私聊" if lnk.get("dm") else esc(lnk.get("chat"))
                        for lnk in it["links"]
                        if lnk.get("dm") or lnk.get("chat")
                    )
                )
                or "未知群"
            )
            fyi.append(f"· #{it['no']} {t}（来源：{g}）")
            info += 1
            pend[str(it["no"])] = it["fingerprint"]
        else:
            cards.append((c, render_card(c, cfg)))
            vers[str(it["no"])] = {"fingerprint": it["fingerprint"], "version": card_version(c, cfg)}
            assign += roles.approver(c, cfg) is not None
    report = f"纯资讯 {info} 条，待你指派 {assign} 条。"
    body = ["\n\n".join(sections(cards, cfg)) if cards else "本轮没有需要确认的条目。"]
    if fyi:
        body.append(
            "仅知悉（不需确认，只告知）：\n"
            + "\n".join(fyi)
            + ("\n纯资讯要转成任务，回复「升格 #序号 办理人：姓名」。" if pend else "")
        )
    if skipped:
        body.append("不再推送：\n" + "\n".join("· " + s for s in skipped))
    body.append(report + ("\n指派卡可回复「指派 #序号 姓名」确认执行员，或「改派 #序号 姓名」换人。" if assign else ""))
    if cards:
        body.append(FOOTER)
    (w / "cards.txt").write_text("\n\n".join(body) + "\n", encoding="utf-8", newline="\n")
    (w / "archive.md").write_text(
        "\n\n".join(render_archive(clean(it), cfg) for it in items) + "\n", encoding="utf-8", newline="\n"
    )
    wj(w / "versions.json", vers)
    set_state(cfg, batch, stage="rendered", info_items=pend)
    return {
        "cards": str(w / "cards.txt"),
        "archive": str(w / "archive.md"),
        "versions": str(w / "versions.json"),
        "card_count": len(cards),
        "fyi": len(fyi),
        "info": info,
        "to_assign": assign,
        "report": report,
    }
