"""用户回复升格、指派与改派：promote、assign 与 _lookup。"""

import json

from feishu_workflows.intent import flow_fetch, names, roles
from feishu_workflows.intent.flow_common import (
    Invalid,
    now,
    rj,
    set_state,
    state,
    wd,
    wj,
)


def promote(cfg, d, batch, text, a, vers):
    """「升格 #N 办理人：X」：只对纯资讯生效（v3）；程序把它转成任务（kind=task），指定的人写成执行员，重新校验、渲染，转为卡片。"""
    st = state(cfg, batch)
    no = a["no"]
    q = None
    if str(no) not in (st.get("info_items") or {}):
        q = f"#{no} 不是纯资讯，不能升格；任务卡请回复「指派 #{no} 姓名」或「改派 #{no} 姓名」。"
    else:
        p = wd(cfg, batch) / "topics.json"
        data = rj(p)
        user = cfg.get("user") or {}
        me = a["assignee"] in ("我", "我自己", "我来", "自己", user.get("display_name"))
        ev = f"用户回复「{text.strip()}」"[:60]
        mine = {
            "name": user.get("display_name") or "我",
            "open_id": roles.self_id(cfg),
            "basis": "reply",
            "evidence": ev,
        }
        person = dict(mine) if me else {"name": a["assignee"], "open_id": None, "basis": "reply", "evidence": ev}
        for it in data["items"]:
            if it.get("no") == no:
                it["assignees"] = [person]
                if not me:  # 指定别人办：用户默认是评审员；回复里自己说了角色就按他说的
                    role = a.get("self_role") or "评审"
                    if role == "执行":
                        it["assignees"] = [person, mine]
                    else:
                        key = {"评审": "reviewers", "问询": "consultees"}[role]
                        it[key] = [mine] + [x for x in it.get(key) or [] if not roles.is_self(x, cfg)]
                it["task_type"] = "team" if len(it["assignees"]) > 1 else "personal"
                it["kind"] = "task"
                it.pop("actions", None)
        wj(p, data)
        set_state(cfg, batch, promoted={**(st.get("promoted") or {}), str(no): person["name"]})
        try:
            flow_fetch.validate_batch(cfg, d, batch)
            flow_fetch.render_batch(cfg, d, batch)
        except Invalid as e:
            q = f"#{no} 升格后校验没通过：{e}"
    a = (
        dict(a, next=f"把新的 {wd(cfg, batch) / 'cards.txt'} 推给用户，然后 feishu-workflows pushed {batch}")
        if not q
        else a
    )
    rec = {"actions": [] if q else [a], "ask_user": q}
    with d:
        d.execute(
            "insert into reply_logs(batch,raw,parsed,versions,at) values(?,?,?,?,?)",
            (batch, text, json.dumps(rec, ensure_ascii=False), json.dumps(vers, ensure_ascii=False), now()),
        )
    return rec


def assign(cfg, d, batch, text, a, vers):
    """「指派 #N 张三」「改派 #N 张三」：只对任务卡生效；执行员换成指定的人（basis=reply），重新校验、渲染，卡片版本随之递增。"""
    st = state(cfg, batch)
    no = a["no"]
    q = None
    old = (vers.get(str(no)) or {}).get("version")
    if old is None:
        q = f"#{no} 不是本批的任务卡，不能{'指派' if a['action'] == 'assign' else '改派'}。" + (
            "纯资讯请用「升格 #N 办理人：姓名」。" if str(no) in (st.get("info_items") or {}) else ""
        )
    else:
        p = wd(cfg, batch) / "topics.json"
        data = rj(p)
        user = cfg.get("user") or {}
        me = a["assignee"] in ("我", "我自己", "自己", user.get("display_name"), *(user.get("names") or []))
        ev = f"用户回复「{text.strip()}」"[:60]
        oid = None
        if not me:
            oids = _lookup(cfg, batch, a["assignee"])
            if len(oids) != 1:
                q = (
                    f"找不到「{a['assignee']}」对应的飞书成员，请用对方在群里的显示名再说一次。"
                    if not oids
                    else f"「{a['assignee']}」对上了 {len(oids)} 位成员，请换个更具体的称呼（如飞书显示名全称）。"
                )
            else:
                oid = next(iter(oids))
        person = (
            {"name": user.get("display_name") or "我", "open_id": roles.self_id(cfg), "basis": "reply", "evidence": ev}
            if me
            else {"name": a["assignee"], "open_id": oid, "basis": "reply", "evidence": ev}
        )
        if not q:  # 解析不了或重名：什么都不存，只追问
            for it in data["items"]:
                if it.get("no") == no:
                    it["assignees"] = [person]
                    it["task_type"] = "personal"
                    it["kind"] = "task"
                    it.pop("actions", None)
                    keep = {x.get("name") for k in ("assignees", "reviewers", "consultees") for x in it.get(k) or []}
                    it["ddl_by_person"] = [e for e in it.get("ddl_by_person") or [] if e.get("person") in keep]
            wj(p, data)
            set_state(cfg, batch, assigned={**(st.get("assigned") or {}), str(no): person["name"]})
            try:
                flow_fetch.validate_batch(cfg, d, batch)
                flow_fetch.render_batch(cfg, d, batch)
            except Invalid as e:
                q = f"#{no} 改执行员后校验没通过：{e}"
    if not q:
        new = (rj(wd(cfg, batch) / "versions.json").get(str(no)) or {}).get("version")
        a = dict(
            a,
            old_version=old,
            version=new,
            next=f"卡片版本已变（{old} → {new}），把新的 {wd(cfg, batch) / 'cards.txt'} 推给用户，然后 feishu-workflows pushed {batch}",
        )
    rec = {"actions": [] if q else [a], "ask_user": q}
    with d:
        d.execute(
            "insert into reply_logs(batch,raw,parsed,versions,at) values(?,?,?,?,?)",
            (batch, text, json.dumps(rec, ensure_ascii=False), json.dumps(vers, ensure_ascii=False), now()),
        )
    return rec


def _lookup(cfg, batch, name):
    """按姓名找 open_id：姓名缓存 + 本批消息的 people；返回所有对上的 open_id。"""
    found = {o for o, n in names.known(cfg).items() if n == name}
    m = rj(wd(cfg, batch) / "messages.json") or {}
    for x in m.get("messages") or []:
        found |= {o for o, n in (x.get("people") or {}).items() if n == name}
    return found
