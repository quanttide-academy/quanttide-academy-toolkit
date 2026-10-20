"""用户回复执行与状态更新：handle_reply 与 pending_cards（唯一的确认状态修改点）。"""

import json

from quanttide_academy.intent.item import card_version
from quanttide_academy.intent.reply_assign import assign, promote
from quanttide_academy.intent.reply_parse import parse_reply
from quanttide_academy.intent.state import (
    Invalid,
    batch_items,
    clean,
    now,
    rj,
    set_state,
    state,
    wd,
)


def handle_reply(cfg, d, batch, text, quote=None):
    """quote=<fingerprint>@<version>：用户引用了某张卡片回复。不带序号的回复只在能唯一确定卡片时生效，绝不猜。"""
    w = wd(cfg, batch)
    vers = rj(w / "versions.json")
    if vers is None:
        raise Invalid("本批还没有渲染卡片")
    acts, q = parse_reply(text)
    st0 = state(cfg, batch)
    if acts and acts[0]["action"] == "promote":
        return promote(cfg, d, batch, text, acts[0], vers)
    if acts and acts[0]["action"] in ("assign", "reassign"):
        return assign(cfg, d, batch, text, acts[0], vers)
    if acts and acts[0]["action"] == "confirm_all_preview":
        pend = pending_cards(cfg, d, batch)
        lst = [{"no": n, "version": vers[str(n)]["version"]} for n in pend]
        set_state(cfg, batch, confirm_all={str(x["no"]): x["version"] for x in lst})
        rec = {
            "actions": [{"action": "confirm_all_preview", "pending": lst}],
            "ask_user": (
                "将写入以下卡片："
                + "、".join(f"#{x['no']}（版本 {x['version']}）" for x in lst)
                + "。确认无误请回复「确认」。"
            )
            if lst
            else "现在没有待确认的卡片。",
        }
        with d:
            d.execute(
                "insert into reply_logs(batch,raw,parsed,versions,at) values(?,?,?,?,?)",
                (batch, text, json.dumps(rec, ensure_ascii=False), json.dumps(vers, ensure_ascii=False), now()),
            )
        return rec
    if acts and acts[0]["action"] == "confirm_all_commit":
        ca = st0.get("confirm_all") or {}
        if not ca:
            acts, q = [], "没有待确认的「全部写入」清单。请先说「全部写入」，或带序号回复，如「#8 写入」。"
        elif any(vers.get(n, {}).get("version") != v for n, v in ca.items()):
            acts, q = [], "「全部写入」列出的卡片后来改过，请重新说「全部写入」核对一遍。"
        else:
            acts = [{"action": "confirm", "no": int(n)} for n in ca]
    if st0.get("confirm_all"):
        set_state(cfg, batch, confirm_all=None)
    if acts and any(a["no"] is None for a in acts):
        target = None
        if quote:
            fp, _, ver = quote.partition("@")
            hit = [no for no, v in vers.items() if v["fingerprint"] == fp]
            if not hit:
                q = "引用的卡片不在这次推送里，请用「#序号 写入」回复。"
            elif vers[hit[0]]["version"] != ver:
                q = f"你引用的是 #{hit[0]} 的旧版卡片，内容已改过，请看新卡片后再回复。"
            else:
                target = int(hit[0])
        else:
            pend = pending_cards(cfg, d, batch)
            if len(pend) == 1:
                target = pend[0]
            else:
                q = "现在有多张待确认的卡片，请带上序号回复，例如「#8 写入」。" if pend else "现在没有待确认的卡片。"
        if target is None:
            acts = []
        else:
            for a in acts:
                a["no"] = target
    if not q:
        items = {str(it["no"]): it for it in batch_items(cfg, d, batch)}
        for a in acts:
            k = str(a["no"])
            if k not in vers:
                q = f"#{a['no']} 不在这次推送的卡片里（仅知悉、已否决或序号不存在），请核对序号。"
                acts = []
                break
            st = state(cfg, batch)
            if a["action"] == "confirm" and st["stage"] == "needs_edit" and a["no"] in (st.get("needs_edit") or []):
                q = f"#{a['no']} 刚提了修改，卡片改过后要重新推送，请看新卡片再确认。"
                acts = []
                break
            it = items.get(k)
            if not it or card_version(clean(it), cfg) != vers[k]["version"]:
                q = f"#{a['no']} 的卡片在推送后改过，旧版本不能确认，请先重新渲染并推送。"
                acts = []
                break
    rec = {"actions": acts, "ask_user": q}
    with d:
        d.execute(
            "insert into reply_logs(batch,raw,parsed,versions,at) values(?,?,?,?,?)",
            (batch, text, json.dumps(rec, ensure_ascii=False), json.dumps(vers, ensure_ascii=False), now()),
        )
        for a in acts:
            v = vers[str(a["no"])]
            fp = v["fingerprint"]
            a["fingerprint"] = fp
            a["version"] = v["version"]
            if a["action"] == "confirm":
                d.execute(
                    "update topics set confirmed=1,confirmed_version=?,confirmed_at=? where fingerprint=?",
                    (v["version"], now(), fp),
                )
                a["next"] = f"feishu-workflows write {batch}"
            elif a["action"] == "reject":
                d.execute(
                    "insert into rejections(fingerprint,title,reason,at) values(?,?,?,?) on conflict(fingerprint) do update set title=excluded.title,reason=excluded.reason,at=excluded.at",
                    (fp, items[str(a["no"])]["title"], text, now()),
                )
                d.execute(
                    "update topics set status='rejected',confirmed=0,confirmed_version=null where fingerprint=?", (fp,)
                )
            elif a["action"] == "explain":  # 说明不改变确认状态；若据此改了字段，版本自然变化，旧确认失效
                a["next"] = (
                    f"读 instruction 判断是否需要改字段：需要就只改 data/work/{batch}/topics.json 中 no={a['no']} 的条目；不需要也照常 feishu-workflows validate {batch} → render {batch}。字段变了要重新推送新卡片"
                )
            else:
                d.execute("update topics set confirmed=0,confirmed_version=null where fingerprint=?", (fp,))
                a["next"] = (
                    f"按 instruction 修改 data/work/{batch}/topics.json 中 no={a['no']} 的条目（只改该条），再 feishu-workflows validate {batch} → render {batch}，重新推送新卡片"
                )
    mods = [a["no"] for a in acts if a["action"] in ("modify", "explain")]
    if mods:
        set_state(cfg, batch, stage="needs_edit", needs_edit=mods)
    return rec


def pending_cards(cfg, d, batch):
    vers = rj(wd(cfg, batch) / "versions.json", {})
    out = []
    for no, v in vers.items():
        r = d.execute(
            "select status,confirmed,confirmed_version from topics where fingerprint=?", (v["fingerprint"],)
        ).fetchone()
        if r and r[0] not in ("written", "rejected") and not (r[1] == 1 and r[2] == v["version"]):
            out.append(int(no))
    return sorted(out)
