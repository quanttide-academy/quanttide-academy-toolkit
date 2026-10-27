"""流程：写入计划（确认闸门）、mark-written、直接写入。"""

import hashlib
import json

from quanttide_academy_toolkit import settings
from quanttide_academy_toolkit.intent import outputs, roles
from quanttide_academy_toolkit.intent.item import (
    card_version,
    description,
    labels,
    resolve,
    task_title,
)
from quanttide_academy_toolkit.intent.state import Invalid, batch_items, now, wd, wj
from quanttide_academy_toolkit.settings import TZ_NAME

PRI = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}


def akey(fp, ver, kind, idx):
    return hashlib.sha256(f"{fp}|{ver}|{kind}|{idx}".encode()).hexdigest()[:16]


def confirmed_current(d, cfg, fp):
    """闸门：已确认且确认的就是当前卡片版本。返回 (item, version) 或 None。"""
    r = d.execute(
        "select item_json,confirmed,confirmed_version,status from topics where fingerprint=?", (fp,)
    ).fetchone()
    if not r or not r[0] or r[1] != 1 or r[3] == "rejected":
        return None
    it = json.loads(r[0])
    v = card_version(it, cfg)
    return (it, v) if r[2] == v else None


def plan_actions(cfg, it, ver):
    fp = it["fingerprint"]
    t = cfg.get("todo") or {}
    r = resolve(it, cfg)
    parent = {
        "content": task_title(it, cfg),
        "description": description(it, cfg),
        "labels": labels(it, cfg),
        "priority": it.get("priority"),
        "todoist_priority": PRI.get(it.get("priority")),
        "due_date": it.get("date"),
        "deadline_date": roles.self_ddl(it, cfg),
        "project_id": t.get("project_id"),
    }
    A = [{"kind": "parent", "idx": 0, "payload": parent}]
    A += [{"kind": "subtask", "idx": i, "payload": {"content": s}} for i, s in enumerate(r["subtasks"])]
    if it.get("remind"):
        A.append({"kind": "reminder", "idx": 0, "payload": {"datetime": it["remind"], "timezone": TZ_NAME}})
    for a in A:
        a.update(key=akey(fp, ver, a["kind"], a["idx"]), fingerprint=fp, version=ver, no=it["no"])
    return A


def build_plan(cfg, d, batch):
    """只为「当前卡片版本已确认」的条目出计划；已完成的动作不再出；子任务和提醒要等父任务有 ext_id。"""
    acts, waiting = [], 0
    for it in batch_items(cfg, d, batch):
        cc = confirmed_current(d, cfg, it["fingerprint"])
        if not cc:
            continue
        item, ver = cc
        done = {
            r[0]: (r[1], r[2])
            for r in d.execute(
                "select key,status,ext_id from write_actions where fingerprint=? and version=?",
                (item["fingerprint"], ver),
            )
        }
        A = plan_actions(cfg, item, ver)
        pk = A[0]["key"]
        pid = done.get(pk, (None, None))
        with d:
            for a in A:
                cur = d.execute(
                    "insert or ignore into write_actions(key,batch,fingerprint,version,kind,idx,payload,status,updated_at) values(?,?,?,?,?,?,?,'planned',?)",
                    (
                        a["key"],
                        batch,
                        a["fingerprint"],
                        ver,
                        a["kind"],
                        a["idx"],
                        json.dumps(a["payload"], ensure_ascii=False),
                        now(),
                    ),
                )
                if cur.rowcount:
                    d.execute("insert into write_action_logs(key,status) values(?,'planned')", (a["key"],))
        for a in A:
            if done.get(a["key"], ("",))[0] == "done":
                continue
            if a["kind"] != "parent":
                if pid[0] != "done":
                    waiting += 1
                    continue
                a["parent_ext_id"] = pid[1]
            acts.append(a)
    plan = {
        "batch": batch,
        "generated_at": now(),
        "note": "每个动作执行后调用 feishu-workflows mark-written <batch> <key> <ext_id|fail>；子任务和提醒要等父任务记下 ext_id 后再次 feishu-workflows write 才会出现。",
        "actions": acts,
        "waiting_for_parent": waiting,
    }
    wj(wd(cfg, batch) / "writes.json", plan)
    return plan


def mark_written(cfg, d, batch, key, ext):
    r = d.execute(
        "select fingerprint,version,kind,idx,payload,status from write_actions where key=? and batch=?", (key, batch)
    ).fetchone()
    if not r:
        raise Invalid(f"没有这个写入动作：{key}")
    fp, ver, kind, idx, _payload, st = r
    cc = confirmed_current(d, cfg, fp)
    if not cc or cc[1] != ver:
        raise Invalid("该条目已不是当前确认版本（卡片改过或确认被撤销），拒绝记录")
    if st == "done":
        return {"key": key, "status": "done", "note": "已记录过，忽略"}
    fail = ext == "fail"
    with d:
        d.execute(
            "update write_actions set status=?,ext_id=?,updated_at=? where key=?",
            ("failed" if fail else "done", None if fail else ext, now(), key),
        )
        d.execute(
            "insert into write_action_logs(key,status,ext_id) values(?,?,?)",
            (key, "failed" if fail else "done", None if fail else ext),
        )
        if not fail:
            w = d.execute("select parent_id,subs_done from writes where fingerprint=?", (fp,)).fetchone()
            pid, subs = (w[0], json.loads(w[1] or "[]")) if w else (None, [])
            if kind == "parent":
                pid = ext
            if kind == "subtask" and idx not in subs:
                subs.append(idx)
            left = d.execute(
                "select count(*) from write_actions where fingerprint=? and version=? and status!='done'", (fp, ver)
            ).fetchone()[0]
            d.execute(
                "insert into writes(fingerprint,provider,parent_id,subs_done,status,updated_at) values(?,?,?,?,?,?) on conflict(fingerprint) do update set provider=excluded.provider,parent_id=excluded.parent_id,subs_done=excluded.subs_done,status=excluded.status,updated_at=excluded.updated_at",
                (fp, "host-connector", pid, json.dumps(sorted(subs)), "done" if not left else "partial", now()),
            )
            if not left:
                d.execute("update topics set status='written',ext_id=? where fingerprint=?", (pid, fp))
    return {"key": key, "status": "failed" if fail else "done"}


def run_write(cfg, d, batch):
    """有 REST 令牌（或本地 markdown/export）由程序经闸门写入；否则出 writes.json 交宿主连接器执行。"""
    t = cfg.get("todo") or {"provider": "markdown"}
    prov = t.get("provider", "markdown")
    direct = prov in ("markdown", "export", "custom") or (
        prov == "todoist" and settings.has_secret(t.get("token_env", "TODOIST_API_TOKEN"))
    )
    if not direct:
        return {"mode": "plan", **build_plan(cfg, d, batch)}
    a = outputs.load(cfg)
    res = []
    for it in batch_items(cfg, d, batch):
        cc = confirmed_current(d, cfg, it["fingerprint"])
        if not cc or it["_status"] == "written":
            continue
        try:
            eid, _ = a.create(cc[0])
            with d:
                d.execute("update topics set status='written',ext_id=? where fingerprint=?", (eid, it["fingerprint"]))
            res.append({"no": it["no"], "status": "written", "ext_id": eid})
        except Exception as e:
            res.append({"no": it["no"], "status": "failed", "reason": type(e).__name__})  # noqa: BLE001
    return {"mode": "direct", "provider": prov, "results": res}


def unwritten_confirmed(cfg, d, batch):
    return [
        it["no"]
        for it in batch_items(cfg, d, batch)
        if it["_status"] != "written" and confirmed_current(d, cfg, it["fingerprint"])
    ]
