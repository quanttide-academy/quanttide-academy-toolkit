"""org 配置：只读解析与校验，不联网。config 的 org 段：
enabled, root_department（部门 ID，必填）, allowed_departments（部门 ID，只能收窄）, approval_chat_id（机器人与本人的单聊，只放本地）,
mappings[{chat_id, department（部门 ID）, name（可选，期望群名）, hold（可选）, hold_reason（hold 时必填）}], protected[open_id], app_open_id, max_items（≤20）,
allow{create, disband, transfer}（默认全关；打开后每条仍须单独批准）。"""

from dataclasses import dataclass, field

MAX_ITEMS = 20
REMOVE_RATIO = 0.30


class BadOrgConfig(ValueError):
    pass


@dataclass(frozen=True)
class OrgConf:
    root: str | None = None
    allowed: tuple = ()
    approval_chat_id: str | None = None
    mappings: tuple = ()
    protected: frozenset = field(default_factory=frozenset)
    app_open_id: str | None = None
    max_items: int = MAX_ITEMS
    allow: dict = field(default_factory=dict)
    enabled: bool = False


def load(cfg) -> OrgConf:
    o = (cfg or {}).get("org") or {}
    mi = o.get("max_items", MAX_ITEMS)
    if isinstance(mi, bool) or not isinstance(mi, int) or not 1 <= mi <= MAX_ITEMS:
        raise BadOrgConfig(f"org.max_items 须是 1～{MAX_ITEMS} 的整数")
    allow = {k: bool((o.get("allow") or {}).get(k, False)) for k in ("create", "disband", "transfer")}
    if "on_hold" in o or "root_name" in o:
        raise BadOrgConfig(
            "org.on_hold / root_name 已废弃：部门一律用 department_id；暂缓改在映射上写 hold: true 与 hold_reason"
        )
    maps = []
    seen = set()
    for i, m in enumerate(o.get("mappings") or []):
        cid = (m or {}).get("chat_id")
        dep = (m or {}).get("department")
        if not (isinstance(cid, str) and cid.startswith("oc_")):
            raise BadOrgConfig(f"org.mappings[{i}] 的 chat_id 须是 oc_ 开头")
        if not dep:
            raise BadOrgConfig(f"org.mappings[{i}] 缺 department")
        if cid in seen:
            raise BadOrgConfig(f"org.mappings[{i}]：一个群只能对应一个部门")
        hold = m.get("hold", False)
        why = m.get("hold_reason")
        if not isinstance(hold, bool):
            raise BadOrgConfig(f"org.mappings[{i}] 的 hold 只能是 true/false")
        if hold and not (isinstance(why, str) and why.strip()):
            raise BadOrgConfig(f"org.mappings[{i}] 标了 hold，必须写 hold_reason")
        seen.add(cid)
        maps.append(
            {
                "chat_id": cid,
                "department": str(dep),
                "name": m.get("name"),
                "hold": hold,
                "hold_reason": why if hold else None,
            }
        )
    prot = o.get("protected") or []
    if any(not str(x).startswith("ou_") for x in prot):
        raise BadOrgConfig("org.protected 只能列 ou_ 开头的 open_id")
    return OrgConf(
        root=str(o["root_department"]) if o.get("root_department") else None,
        allowed=tuple(str(x) for x in o.get("allowed_departments") or []),
        approval_chat_id=o.get("approval_chat_id") or None,
        mappings=tuple(maps),
        protected=frozenset(prot),
        app_open_id=o.get("app_open_id"),
        max_items=mi,
        allow=allow,
        enabled=bool(o.get("enabled", False)),
    )
