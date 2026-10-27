"""org plan：只读算出「部门 → 群」的差异（成员增删、改群名），不写飞书。
保护：读不到部门即报错；映射部门须在允许范围；保护名单（本人、群主、程序账号、org.protected）不作移出候选，若仍出现在移出/撤管理员里即拒绝（apply 再查）；
单群移出超过 30% 拒绝；外部成员只能移出；映射上标 hold 的群只在「暂缓，仅展示」里列差异与原因、不生成写入条目；每批最多 max_items 条，其余留到下一批。"""

import hashlib
import json

from quanttide_academy_toolkit.org import conf as C
from quanttide_academy_toolkit.org import read as R

KIND_ORDER = {
    "remove_member": 0,
    "unset_admin": 1,
    "add_member": 2,
    "set_admin": 3,
    "rename": 4,
    "transfer": 5,
    "create": 6,
    "disband": 7,
}
KIND_ZH = {
    "remove_member": "移出群",
    "add_member": "拉进群",
    "set_admin": "设为管理员",
    "unset_admin": "撤销管理员",
    "rename": "改群名",
    "transfer": "转让群主",
    "create": "建群",
    "disband": "解散群",
}
EXTRA_KINDS = {"create", "disband", "transfer"}  # 默认禁用；打开后每条仍须单独批准


class PlanRefused(RuntimeError):
    pass


def _desc(tree, root):
    kids = {}
    [kids.setdefault(d["parent"], []).append(d["id"]) for d in tree]
    out, st = set(), [root]
    while st:
        x = st.pop()
        if x not in out:
            out.add(x)
            st += kids.get(x, [])
    return out


def _resolve(tree, ref, what):
    """只按 department_id 匹配，不按名字。"""
    if ref and any(d["id"] == ref for d in tree):
        return ref
    raise C.BadOrgConfig(f"{what} {ref or '（未填）'} 不在部门树里（只认 department_id，可用 org depts 查）")


def scope(cfg, oc, tree):
    root = _resolve(tree, oc.root, "root_department")
    allowed = _desc(tree, root)
    if oc.allowed:
        rs = [_resolve(tree, a, "allowed_departments") for a in oc.allowed]
        if any(r not in allowed for r in rs):
            raise C.BadOrgConfig("allowed_departments 只能收窄到根部门之内")
        allowed = set().union(*(_desc(tree, r) for r in rs))
    return allowed


PROTECTED_KINDS = ("remove_member", "unset_admin")


def check_protected(diff, prot):
    """兜底不变式：任何条目要移出保护名单里的人或撤销其管理员，整个计划拒绝生成（apply 与写入层再查）。"""
    if prot & {x.get("person") for x in diff if x["kind"] in PROTECTED_KINDS}:
        raise PlanRefused("计划会把保护名单里的人（本人、群主、程序账号或 org.protected）移出群或撤销管理员，拒绝生成")


def _candidates(cur, want, prot):
    return sorted(set(cur) - want - prot)


def plan_id(items):
    return hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def compute(cfg, reader=R) -> dict:
    oc = C.load(cfg)
    tree = reader.dept_tree(cfg)
    allowed = scope(cfg, oc, tree)
    me = (cfg or {}).get("self_open_id")
    tk = (cfg or {}).get("self_tenant_key")
    if not me or not tk:
        raise C.BadOrgConfig("org 需要 self_open_id 与 self_tenant_key（判断本人与外部成员）")
    raw, held_lines, groups = [], [], []
    for m in oc.mappings:
        did = _resolve(tree, m["department"], "映射部门")
        if did not in allowed:
            raise C.BadOrgConfig("映射的部门不在 allowed_departments 内，拒绝运行")
        want = set().union(*(reader.dept_members(cfg, x) for x in sorted(_desc(tree, did) & allowed)))
        info = reader.chat_info(cfg, m["chat_id"])
        cur = reader.chat_members(cfg, m["chat_id"])
        prot = {me, info.get("owner"), oc.app_open_id, *oc.protected} - {None}
        kept = sorted(
            (set(cur) - want) & prot
        )  # 保护名单不进移出候选（本人、群主不一定在映射部门里）；下面的拒绝检查是兜底不变式
        rm = _candidates(cur, want, prot)
        add = sorted(want - set(cur))
        diff = [
            {
                "kind": "remove_member",
                "person": p,
                "external": cur[p] != tk,
                "reason": "不在映射部门" if cur[p] == tk else "外部成员，不在映射部门",
            }
            for p in rm
        ]
        diff += [
            {"kind": "add_member", "person": p, "external": False, "reason": "映射部门成员，不在群里"} for p in add
        ]
        if m.get("name") and info.get("name") != m["name"]:
            diff.append(
                {"kind": "rename", "person": None, "name": m["name"], "external": False, "reason": "群名与映射不一致"}
            )
        diff = [{"chat_id": m["chat_id"], "department": did, **x} for x in diff]
        groups.append(
            {
                "chat_id": m["chat_id"],
                "members": len(cur),
                "remove": len(rm),
                "add": len(add),
                "protected_kept": len(kept),
                "held": m["hold"],
            }
        )
        if m["hold"]:
            held_lines += [{**x, "hold_reason": m["hold_reason"]} for x in diff]
            continue  # 暂缓：只列差异，不生成写入条目
        check_protected(diff, prot)
        if cur and len(rm) / len(cur) > C.REMOVE_RATIO:
            raise PlanRefused(f"一个群要移出 {len(rm)}/{len(cur)} 人，超过 30%，拒绝生成")
        if any(x["kind"] == "add_member" and x["external"] for x in diff):
            raise PlanRefused("外部成员不能被拉进内部群")
        raw += diff
    raw.sort(key=lambda x: (KIND_ORDER[x["kind"]], x["chat_id"], x.get("person") or "", x.get("name") or ""))
    items = [{"idx": i, **x} for i, x in enumerate(raw[: oc.max_items], 1)]
    return {
        "plan_id": plan_id(items),
        "items": items,
        "held": held_lines,
        "deferred": max(0, len(raw) - oc.max_items),
        "groups": groups,
        "departments": len(tree),
        "in_scope": len(allowed),
        "held_groups": sum(g["held"] for g in groups),
    }


def line(it):
    obj = "{person:" + it["person"] + "}" if it.get("person") else f"「{it.get('name')}」"
    return f"{it['idx']}. 群 {it['chat_id']}：{KIND_ZH[it['kind']]} {obj}（{it['reason']}）"


def render(p) -> str:
    """计划文本：移出群的条目放最前并标红；暂缓部门的差异单列「暂缓」。"""
    rm = [line(x) for x in p["items"] if x["kind"] == "remove_member"]
    other = [line(x) for x in p["items"] if x["kind"] != "remove_member"]
    L = (
        [f"org 计划 {p['plan_id'][:8]}（{len(p['items'])} 条）"]
        + (["🔴 移出群（请逐条核对）："] + rm if rm else [])
        + (["其他变更："] + other if other else [])
    )
    if not p["items"]:
        L.append("没有需要执行的变更。")
    if p["deferred"]:
        L.append(f"另有 {p['deferred']} 条超出本批上限，执行完本批后重新 plan 再审批。")
    if p["held"]:
        L += ["暂缓，仅展示（不生成写入条目；解除暂缓须改配置并经本人确认）："] + [
            f"· 群 {x['chat_id']}：{KIND_ZH[x['kind']]} "
            + ("{person:" + x["person"] + "}" if x.get("person") else f"「{x.get('name')}」")
            + f"（暂缓原因：{x['hold_reason']}）"
            for x in p["held"]
        ]
    L.append(
        f"批准方式：本人在审批单聊里亲手发「批准 {p['plan_id'][:8]}」（24 小时内有效）；计划 ID 只出现在本报告里，不要转发到别处。"
    )
    return "\n".join(L)


def store(d, p):
    with d:
        d.execute(
            "insert or ignore into org_plans(plan_id,items_json,held_json,status) values(?,?,?,'pending')",
            (
                p["plan_id"],
                json.dumps(p["items"], ensure_ascii=False, sort_keys=True),
                json.dumps(p["held"], ensure_ascii=False, sort_keys=True),
            ),
        )
