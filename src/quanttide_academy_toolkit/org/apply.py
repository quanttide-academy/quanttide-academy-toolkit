"""org apply：先重新 plan，与已批准计划逐字比较，不一致即拒绝（要求重新审批）；一致才把批准的条目逐条交给 writer。
执行后再 plan 一次，报告剩余差异。暂缓部门的群、保护名单在这里现场再算一遍交给 writer 兜底。"""

from quanttide_academy_toolkit.org import approve as A
from quanttide_academy_toolkit.org import conf as C
from quanttide_academy_toolkit.org import plan as P
from quanttide_academy_toolkit.org import read as R
from quanttide_academy_toolkit.org import writer as W


class ApplyRefused(RuntimeError):
    pass


def run(cfg, d, prefix, only=None, reader=R, runner=None, notify=None):
    pid, items, _, approved = A.find(d, prefix, ("approved", "applying"))
    sent = A.reverify(cfg, d, pid, reader)  # 批准来源现场再核验
    fresh = P.compute(cfg, reader)
    if fresh["items"] != items:
        with d:
            d.execute("update org_plans set status='stale' where plan_id=?", (pid,))
        raise ApplyRefused("重新计算的计划与已批准的不一致（情况已变化），拒绝执行；请重新 plan 并审批")
    sel = sorted(set(approved) & set(only)) if only else sorted(approved)
    if only and set(only) - set(approved):
        raise ApplyRefused("--only 里有未获批准的序号")
    oc = C.load(cfg)
    me = cfg.get("self_open_id")
    held = {g["chat_id"] for g in fresh["groups"] if g["held"]}
    owners = {reader.chat_info(cfg, c).get("owner") for c in {it["chat_id"] for it in items}}
    guard = {"held_chats": held, "protected": {me, oc.app_open_id, *oc.protected, *owners} - {None}}
    if notify:
        notify(
            {"status": "info", "plan_id": pid[:8], "approval_sent_at": sent, "note": "写入前确认：批准消息的发送时间"}
        )
    with d:
        d.execute("update org_plans set status='applying' where plan_id=?", (pid,))
    done, replayed, refused = [], [], []
    for i in sel:
        it = next(x for x in items if x["idx"] == i)
        if it["chat_id"] in held:
            raise ApplyRefused(f"第 {i} 条所在的群标了暂缓，拒绝执行（已完成 {done}）")
        if it["kind"] in P.PROTECTED_KINDS and it.get("person") in guard["protected"]:
            raise ApplyRefused(f"第 {i} 条要移出保护名单里的人或撤销其管理员，拒绝执行（已完成 {done}）")
        try:
            r = W.execute(cfg, d, pid, i, guard, runner=runner)
        except W.WriteRefused as e:
            raise ApplyRefused(f"第 {i} 条被拒或失败，已停止（已完成 {done}）：{e}") from e
        (replayed if r["replayed"] else done).append(i)
    left = P.compute(cfg, reader)
    if not refused and set(sel) == set(approved):
        with d:
            d.execute(
                "update org_plans set status='applied',applied_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') where plan_id=?",
                (pid,),
            )
    return {
        "plan_id": pid,
        "done": done,
        "replayed": replayed,
        "refused": refused,
        "remaining": len(left["items"]) + left["deferred"],
        "approval_sent_at": sent,
    }
