"""监听目标：沿用 config.yaml 的 watch 列表；目标键取第一个账号的 open_id。
私聊来源（本人与该目标的私聊）默认关：watch_options.dm 全局开关，目标上的 dm 优先；开启时须给 dm_chat_id（只放本地配置）。"""

from dataclasses import dataclass, field


class BadTargets(ValueError):
    pass


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    accounts: dict = field(default_factory=dict)
    dm: bool = False
    dm_chat: str | None = None
    chats: tuple | None = None  # None=全部白名单群；否则须是 include_chats 的子集


def load(cfg) -> list:
    out = []
    seen = {}
    g = ((cfg or {}).get("watch_options") or {}).get("dm", False)
    if not isinstance(g, bool):
        raise BadTargets("watch_options.dm 只能是 true/false")
    for i, w in enumerate((cfg or {}).get("watch") or []):
        name = (w or {}).get("name")
        acc = (w or {}).get("accounts") or {}
        if not isinstance(name, str) or not name.strip():
            raise BadTargets(f"watch[{i}] 缺 name")
        if not acc:
            raise BadTargets(f"watch[{i}]（{name}）没有账号")
        for oid in acc:
            if not str(oid).startswith("ou_"):
                raise BadTargets(f"watch[{i}]（{name}）的账号必须是 ou_ 开头的 open_id")
            if oid in seen:
                raise BadTargets(f"账号重复：同一 open_id 同时出现在「{seen[oid]}」和「{name}」")
            seen[oid] = name
        dm = w.get("dm", g)
        if not isinstance(dm, bool):
            raise BadTargets(f"watch[{i}]（{name}）的 dm 只能是 true/false")
        dc = w.get("dm_chat_id")
        if dm and not (isinstance(dc, str) and dc.startswith("oc_")):
            raise BadTargets(f"watch[{i}]（{name}）开了私聊来源，须在本地配置填 oc_ 开头的 dm_chat_id")
        ch = w.get("chats")
        if ch is not None:
            inc = {str(c.get("chat_id")) for c in (((cfg or {}).get("scope") or {}).get("include_chats") or [])}
            bad = [c for c in ch if str(c) not in inc]
            if bad or not ch:
                raise BadTargets(
                    f"watch[{i}]（{name}）的 chats 必须是 scope.include_chats 的非空子集（有 {len(bad)} 个不在其中）"
                )
            ch = tuple(str(c) for c in ch)
        out.append(
            Target(key=next(iter(acc)), name=name, accounts=dict(acc), dm=dm, dm_chat=dc if dm else None, chats=ch)
        )
    return out


def owner(targets) -> dict:
    """open_id → 目标键。"""
    return {oid: t.key for t in targets for oid in t.accounts}


def backfill_days(cfg) -> int:
    """新目标首次回溯天数：默认 7，可配 1～30。"""
    v = ((cfg or {}).get("watch_options") or {}).get("backfill_days", 7)
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 30:
        raise BadTargets("watch_options.backfill_days 须是 1～30 的整数")
    return v


def self_key(cfg=None, d=None) -> str:
    """本人目标的 target_key：优先含 self_open_id 的目标，其次首个目标，再其次 self_open_id 或库内已有目标。"""
    me = (cfg or {}).get("self_open_id") if isinstance(cfg, dict) else None
    if isinstance(cfg, dict) and cfg.get("watch"):
        try:
            ts = load(cfg)
        except BadTargets:
            ts = []
        if ts:
            return next((t.key for t in ts if me and me in t.accounts), ts[0].key)
        for w in cfg.get("watch") or []:
            acc = (w or {}).get("accounts") if isinstance(w, dict) else None
            if isinstance(acc, dict) and acc:
                return str(me if me in acc else next(iter(acc)))
    if me:
        return str(me)
    if d is not None:
        tabs = {r[0] for r in d.execute("select name from sqlite_master where type='table'")}
        if "watch_targets" in tabs:
            r = d.execute(
                "select key from watch_targets where is_deleted=0 order by active desc,id asc limit 1"
            ).fetchone()
            if r and r[0]:
                return str(r[0])
        if "watch_cursors" in tabs:
            r = d.execute("select target_key from watch_cursors where is_deleted=0 order by id asc limit 1").fetchone()
            if r and r[0]:
                return str(r[0])
    return "ou_demo_self"
