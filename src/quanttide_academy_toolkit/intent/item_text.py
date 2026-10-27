"""条目文本与标签格式化：esc、各类 *_text、labels、sanitize_quote、ref_title、text_of、msg_link。"""

import json
import re
from urllib.parse import quote

from quanttide_academy_toolkit.intent import roles

FIELDS = [
    "任务类型",
    "执行员",
    "评审员",
    "咨询对象",
    "评审标准",
    "DDL",
    "日期",
    "截止",
    "提醒",
    "优先级",
    "标签",
    "行动",
    "链接",
    "子任务",
    "备注",
]
MD_SPECIAL = re.compile(r"([\\`*_\[\]#|<>])")
FID = re.compile(r"(?<![A-Za-z0-9])F\d+(?![0-9])")
TEXT_FIELDS = ("title", "summary", "note", "date_basis", "ddl_basis", "remind_basis", "refs_reason", "review_criteria")
SELF_MARK = "〔我〕"
ACTIONS = roles.ACTIONS


def text_of(m):
    try:
        c = json.loads((m.get("body") or {}).get("content") or "{}")
    except (ValueError, TypeError):
        return ""  # 图片、卡片等非文本消息的 content 不是 JSON 文本，按无文字处理
    if "text" in c:
        return c["text"]
    if "content" in c:
        return "".join(e.get("text", "") for line in c["content"] for e in line if isinstance(e, dict))
    return "[" + m.get("msg_type", "") + "]"


def msg_link(cid, pos):
    """返回 (url, direct)。position 不是纯数字时退回群链接。"""
    base = "https://applink.feishu.cn/client/chat/open?openChatId=" + quote(str(cid), safe="")
    p = str(pos) if pos is not None else ""
    return (base + "&position=" + p, True) if p.isdigit() else (base, False)


def esc(s):
    return MD_SPECIAL.sub(r"\\\1", str(s or ""))


def none(v):
    return v if v else "无"


def _pending(v, basis):
    return v if v else f"待定（{basis or '原因未写'}）"


def date_text(it):
    return _pending(it.get("date"), it.get("date_basis"))


def remind_text(it):
    return (it["remind"] + "（北京时间）") if it.get("remind") else _pending(None, it.get("remind_basis"))


def ddl_text(it):
    return (
        f"{it['ddl']}（依据：{it.get('ddl_basis') or '无'}）" if it.get("ddl") else _pending(None, it.get("ddl_basis"))
    )


def labels(it, cfg):
    """标签由程序推导：只用 config.labels.priority_names 里的优先级显示名（与 Todoist 现有标签同名，不加 P 前缀）。"""
    pn = ((cfg or {}).get("labels") or {}).get("priority_names", {}).get(it.get("priority"))
    return [pn] if pn else []


def actions_text(it, cfg=None):
    return roles.actions_text(it, cfg)


def _verified(cfg):
    return bool(((cfg or {}).get("links") or {}).get("position_verified"))


def link_text(lnk, cfg):
    if lnk.get("dm"):
        return (
            f"[私聊原消息]({lnk['url']})"
            if lnk.get("direct")
            else f"[私聊]({lnk['url']}) 消息ID {lnk['message_id']}（未能直跳）"
        )
    if lnk.get("direct"):
        return f"[原消息]({lnk['url']})" + ("" if _verified(cfg) else "（待验证）")
    return f"[群链接]({lnk['url']}) 消息ID {lnk['message_id']}（未能直跳）"


def _card_link(lnk, cfg):
    if not lnk.get("direct"):
        return f"[打开{'私聊' if lnk.get('dm') else '群聊'}]({lnk['url']})（未能直跳）"
    return f"[跳到原消息]({lnk['url']})" + ("" if _verified(cfg) else "（待验证）")


def _titles(cfg):
    return (cfg or {}).get("_followup_titles") or {}


def ref_title(r, cfg):
    """跟进清单内部编号（F3）→ 标题；未知编号显示「（未知关联）」；#6 这类批内序号原样保留。"""
    if FID.fullmatch(r.strip()):
        return _titles(cfg).get(r.strip(), "（未知关联）")
    return r


def _name(cfg):
    return ((cfg or {}).get("user") or {}).get("display_name") or "我"


def sanitize_quote(t, n=60):
    """外部原话：去 @ 提及、打码手机号/token、转义 Markdown 与链接语法、截断。"""
    t = re.sub(r"@\S+", "（成员）", str(t or ""))
    t = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", lambda m: m.group()[:3] + "****" + m.group()[-4:], t)
    t = re.sub(r"(?i)((?:token|sign|key|secret|xsec_token)=)[^&\s]+", r"\1***", t)
    t = re.sub(r"https?://\S+", "[链接]", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > n:
        cut = t[:n]
        k = max(cut.rfind(c) for c in "。！？；，,.!?;")
        t = (cut[: k + 1] if k >= n // 2 else cut) + "…"
    return esc(t)
