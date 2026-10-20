"""发言人姓名解析（只读）：先查群成员列表，查不到再查通讯录单个用户；结果只缓存 open_id→姓名，7 天过期。
不存手机号、邮箱或其他字段；不打印令牌。所有调用经 core/lark（只允许 GET）。"""

import json
import time
from pathlib import Path

from feishu_workflows.core import lark as larkcli
from feishu_workflows.core import paths

TTL = 7 * 24 * 3600


def load(path: Path, now=None) -> dict:
    """读缓存，丢掉过期项；文件不存在返回空表。"""
    now = now or time.time()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        k: {"name": v["name"], "at": v["at"]}
        for k, v in raw.items()
        if isinstance(v, dict) and v.get("name") and now - v.get("at", 0) < TTL
    }


def save(path: Path, cache: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: {"name": str(v["name"]), "at": int(v["at"])} for k, v in cache.items()}  # 只留姓名和时间
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def chat_members(cfg, chat_id) -> dict:
    out = {}
    for page in larkcli.call(
        cfg,
        "api",
        "GET",
        f"/open-apis/im/v1/chats/{chat_id}/members",
        "--as",
        "user",
        "--page-all",
        "--params",
        '{"member_id_type":"open_id","page_size":100}',
    ):
        for m in (page.get("data") or {}).get("items") or []:
            if m.get("member_id") and m.get("name"):
                out[m["member_id"]] = m["name"]
    return out


def contact_name(cfg, open_id):
    r = larkcli.call(
        cfg,
        "api",
        "GET",
        f"/open-apis/contact/v3/users/{open_id}",
        "--as",
        "user",
        "--params",
        '{"user_id_type":"open_id"}',
    )
    for o in r:
        n = ((o.get("data") or {}).get("user") or {}).get("name")
        if n:
            return n
    return None


def resolve(cfg, pairs, cache_path: Path, now=None) -> dict:
    """pairs：[(chat_id, open_id)]。返回 open_id→姓名（解析不到的不出现）。先用缓存，再按群查成员，最后查通讯录。"""
    now = now or time.time()
    cache = load(cache_path, now)
    need = {}
    for cid, oid in pairs:
        if oid and oid not in cache:
            need.setdefault(cid, set()).add(oid)
    left = set()
    for cid, oids in need.items():
        try:
            mem = chat_members(cfg, cid)
        except larkcli.LarkError:
            mem = {}  # 群成员查不到（权限或已退群）：改走通讯录
        for oid in oids:
            if oid in mem:
                cache[oid] = {"name": mem[oid], "at": int(now)}
            else:
                left.add(oid)
    for oid in sorted(left):
        try:
            n = contact_name(cfg, oid)
        except larkcli.LarkError:
            n = None  # 通讯录也查不到：保持未知，卡片显示「（未知发言人）」
        if n:
            cache[oid] = {"name": n, "at": int(now)}
    save(cache_path, cache)
    return {k: v["name"] for k, v in cache.items()}


def fill(cfg, msgs, cache_path: Path, now=None) -> int:
    """按 sender_open_id 补 speaker，并给每条消息写 people（只含发言人和被 @ 的人：open_id→姓名，供摘要占位符使用）。
    返回补上发言人姓名的条数。"""
    pairs = [(m.get("chat_id"), o) for m in msgs for o in [m.get("sender_open_id"), *(m.get("mentions") or [])]]
    names = resolve(cfg, pairs, cache_path, now)
    n = 0
    for m in msgs:
        nm = names.get(m.get("sender_open_id"))
        if nm:
            m["speaker"] = nm
            n += 1
        m["people"] = {o: names[o] for o in [m.get("sender_open_id"), *(m.get("mentions") or [])] if o in names}
    return n


def departments(cfg, cache_path: Path, now=None) -> list:
    """只读拉取部门名（GET 部门子树，应用身份 --as bot：用户身份返回 0 个部门），缓存 7 天；只存名字。查不到返回空表。"""
    now = now or time.time()
    if cache_path.exists():
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if now - raw.get("at", 0) < TTL:
            return list(raw.get("names") or [])
    out = set()
    try:
        for page in larkcli.call(
            cfg,
            "api",
            "GET",
            "/open-apis/contact/v3/departments/0/children",
            "--as",
            "bot",
            "--page-all",
            "--params",
            '{"fetch_child":true,"page_size":50}',
        ):
            out |= {d["name"] for d in (page.get("data") or {}).get("items") or [] if d.get("name")}
    except larkcli.LarkError:
        out = set()  # 没有通讯录部门权限：豁免表为空，不影响人名校验
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"names": sorted(out), "at": int(now)}, ensure_ascii=False), encoding="utf-8")
    return sorted(out)


def known(cfg) -> dict:
    """本地已知的 open_id→姓名（只读缓存，不联网）。"""
    return {k: v["name"] for k, v in load(paths.name_cache(cfg)).items()}


def dept_names(cfg) -> list:
    p = paths.dept_cache(cfg)
    return list(json.loads(p.read_text(encoding="utf-8")).get("names") or []) if p.exists() else []
