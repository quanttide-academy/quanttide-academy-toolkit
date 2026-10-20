"""org depts：只读列出部门 ID 与名字，并给出「建议勾选」（根部门、暂缓部门、群→部门映射）。结果写本地文件，不入库。
建议只是建议：部门最终一律按 department_id 写进本地配置，由本人确认。"""

import difflib

from quanttide_academy.core import paths
from quanttide_academy.org import read as R

ROOT_HINT = "实训基地"
HOLD_HINTS = ("创始人部", "秘书处", "运营部", "游戏部")


def _sim(a, b):
    return difflib.SequenceMatcher(None, a or "", b or "").ratio()


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


def closest(tree, hint):
    """名字最接近的部门：包含关系优先，其次相似度 ≥0.5；都没有返回 None（「无匹配」）。"""
    sc = sorted(((hint in (d["name"] or ""), _sim(hint, d["name"]), d["id"]) for d in tree), reverse=True)
    best = sc[0] if sc else None
    if not best or not (best[0] or best[1] >= 0.5):
        return None
    return next(d for d in tree if d["id"] == best[2])


def suggest(cfg, reader=R) -> dict:
    tree = reader.dept_tree(cfg)
    roots = [d for d in tree if d["parent"] == "0" and ROOT_HINT in (d["name"] or "")]
    root = roots[0] if len(roots) == 1 else None
    scope = [d for d in tree if root and d["id"] in _desc(tree, root["id"])] or tree
    holds = {h: closest(scope, h) for h in HOLD_HINTS}
    mem = {d["id"]: reader.dept_members(cfg, d["id"]) for d in scope}
    full = {d["id"]: set().union(*(mem.get(x, set()) for x in _desc(tree, d["id"]) if x in mem)) for d in scope}
    maps = []
    for c in reader.my_chats(cfg):
        cm = set(reader.chat_members(cfg, c["chat_id"]))
        best = max(
            scope,
            key=lambda d, cm=cm, n=c["name"]: (
                len(cm & full[d["id"]]) / max(1, len(cm | full[d["id"]])),
                _sim(n, d["name"]),
            ),
            default=None,
        )  # Jaccard，避免总选根部门
        if best and cm & full[best["id"]]:
            maps.append({"chat": c, "dept": best, "overlap": len(cm & full[best["id"]]), "chat_members": len(cm)})
    return {"tree": tree, "root": root, "root_candidates": len(roots), "holds": holds, "mappings": maps}


def write(cfg, s) -> str:
    L = ["# org depts（只读结果，仅本地，不入库）", "", "## 部门 ID 与名字"] + [
        f"- {d['id']}　{d['name']}（上级 {d['parent']}）" for d in s["tree"]
    ]
    L += [
        "",
        "## 建议勾选",
        "",
        f"根部门（名字含「{ROOT_HINT}」的顶级部门）："
        + (f"{s['root']['name']}　{s['root']['id']}" if s["root"] else f"无匹配（候选 {s['root_candidates']} 个）"),
    ]
    L += ["", "暂缓部门（名字最接近）："] + [
        f"- {h} → " + (f"{d['name']}　{d['id']}" if d else "无匹配") for h, d in s["holds"].items()
    ]
    L += ["", "群 → 部门（按成员重合与群名）："] + [
        f"- {m['chat']['name']}　{m['chat']['chat_id']} → {m['dept']['name']}　{m['dept']['id']}（重合 {m['overlap']}/{m['chat_members']} 人）"
        for m in s["mappings"]
    ]
    L += ["", "以上只是建议；请把选定的 department_id 写进本地 config 的 org 段，并由本人确认。"]
    p = paths.data_dir(cfg) / "org_depts_suggest.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")
    return str(p)
