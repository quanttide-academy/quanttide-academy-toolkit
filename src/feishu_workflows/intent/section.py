"""watch 多目标在卡片上的呈现：条目的监听对象取自依据消息的 target；本人目标不加任何东西。
监听对象的角色只做展示（单独一行），不参与「行动」推导——行动一律按本人 open_id 计算；对方的 DDL 只进描述，不进 Todoist deadline。"""

ROLE_NAMES = (("assignees", "执行员"), ("reviewers", "评审员"), ("consultees", "咨询对象"))


def _self_id(cfg):
    return (cfg or {}).get("self_open_id") or ((cfg or {}).get("user") or {}).get("open_id")


def _targets(cfg):
    return {next(iter(w.get("accounts") or {}), None): w for w in (cfg or {}).get("watch") or [] if w.get("accounts")}


def target_of(it):
    return next((lnk.get("target") for lnk in it.get("links") or [] if lnk.get("target")), None)


def watched(it, cfg):
    """非本人的监听对象：返回 watch 配置项，否则 None。"""
    k = target_of(it)
    w = _targets(cfg).get(k)
    if not w or _self_id(cfg) in (w.get("accounts") or {}):
        return None
    return w


def role_line(it, cfg):
    w = watched(it, cfg)
    if not w:
        return None
    acc = set(w.get("accounts") or {})
    rs = [n for k, n in ROLE_NAMES for p in it.get(k) or [] if isinstance(p, dict) and p.get("open_id") in acc]
    return f"监听对象：{w['name']}（角色：{'、'.join(dict.fromkeys(rs)) or '未列入角色'}，仅展示）"


def section(it, cfg):
    """合并批次里的分节名：本人或无 target 归「本人」。"""
    w = watched(it, cfg)
    return w["name"] if w else "本人"
