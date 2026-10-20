"""每轮重读外部跟进清单（config.followups.path），以文件为准同步；删掉的条目标「已结束」。留空跳过；配了但读不到抛错（走 abort）。"""

import json
import re

from quanttide_academy.core import paths


class FollowupError(RuntimeError):
    pass


def sync(cfg, d):
    p = paths.followups_path(cfg)
    if p is None:
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        raise FollowupError(f"跟进清单读不到：{p}（{type(e).__name__}）")
    src = p.name
    seen = set()
    fol = {}
    if p.suffix.lower() == ".json":  # [{id,title,keywords?,note?,follower?:{name,open_id}}]
        data = json.loads(text)
        rows = [[str(x["id"]), str(x["title"]), str(x.get("keywords", "")), str(x.get("note", ""))] for x in data]
        fol = {str(x["id"]): x["follower"] for x in data if isinstance(x.get("follower"), dict)}
    else:
        rows = [[x.strip() for x in line.strip().strip("|").split("|")] for line in text.splitlines()]
        head = next((r for r in rows if r and r[0] == "编号"), [])
        col = next((i for i, h in enumerate(head) if h in ("跟进人", "负责", "负责人")), None)
        if col is not None:
            for r in rows:
                if len(r) > col and re.fullmatch(r"[A-Z]+\d+", r[0]):
                    m = re.search(r"\bou_[0-9A-Za-z]+", r[col])
                    fol[r[0]] = {
                        "name": re.sub(r"[（(]?\bou_[0-9A-Za-z]+[)）]?", "", r[col]).strip(),
                        "open_id": m.group() if m else None,
                    }
    for c in rows:
        if len(c) < 3 or not re.fullmatch(r"[A-Z]+\d+", c[0]):
            continue
        fp = f"{src}:{c[0]}"
        seen.add(fp)
        fj = json.dumps({"follower": fol.get(c[0])}, ensure_ascii=False)
        d.execute(
            """insert into topics(fingerprint,title,status,relation,sources,origin,ext_id,keywords,note,item_json) values(?,?,'following','需跟进',?,'外部跟进',?,?,?,?)
          on conflict(fingerprint) do update set title=excluded.title,keywords=excluded.keywords,note=excluded.note,item_json=excluded.item_json,status='following'""",
            (fp, c[1], src, c[0], c[2], "｜".join(c[3:]), fj),
        )
    for (fp,) in d.execute("select fingerprint from topics where origin='外部跟进' and sources=?", (src,)).fetchall():
        if fp not in seen:
            d.execute("update topics set status='closed' where fingerprint=?", (fp,))
    return d.execute("select ext_id,title,status from topics where origin='外部跟进'").fetchall()


def _check(p):
    if not p.is_file():
        raise FollowupError(f"跟进清单读不到：{p}（文件不存在）")


def titles(cfg, d):
    """当前跟进清单的 编号→标题，供卡片把 F 编号换成标题。配了路径但文件不在就抛 FollowupError。"""
    p = paths.followups_path(cfg)
    if p is None:
        return {}
    _check(p)
    return {
        r[0]: r[1]
        for r in d.execute(
            "select ext_id,title from topics where origin='外部跟进' and sources=? and status!='closed'", (p.name,)
        )
    }


def followers(cfg, d):
    """当前跟进清单的 编号→跟进人 {name, open_id}；没有 open_id 的跟进人不会被判为本人。"""
    p = paths.followups_path(cfg)
    if p is None:
        return {}
    out = {}
    for ext, js in d.execute(
        "select ext_id,item_json from topics where origin='外部跟进' and sources=? and status!='closed'", (p.name,)
    ):
        f = (json.loads(js) if js else {}).get("follower")
        if f:
            out[ext] = f
    return out
