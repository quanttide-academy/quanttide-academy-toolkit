"""用户回复语法解析：parse_reply 与 _nums。只有逐条点名的「写入」算确认；含糊的话一律不确认。"""

import re

NUM = r"#?\s*\d+"
LIST = rf"{NUM}(?:\s*[、,，和及/ ]\s*{NUM})*"


def _nums(s):
    return [int(x) for x in re.findall(r"\d+", s)]


def parse_reply(text):
    """返回 (actions, question)。只有逐条点名的「写入」算确认；含糊的话一律不确认。"""
    t = str(text or "").strip().replace("＃", "#")
    acts = []
    used = []
    mr = re.search(r"[，,、；;\s]*我(?:来|负责|做|当)?(评审|咨询|问询|执行)(?:员|对象)?\s*[。！!]?$", t)
    self_role = None
    if mr and re.match(r"升格\s*#?\s*\d+\s*\S", t[: mr.start()] or ""):
        self_role = {"咨询": "问询"}.get(mr.group(1), mr.group(1))
        t = t[: mr.start()]
    m = re.fullmatch(
        r"(指派|改派)\s*#?\s*(\d+)\s*[，,、：:]?\s*(?:给|由|执行员\s*[是为：:]?)?\s*(.*?)\s*(?:来办|办理|负责|来做|办)?\s*[。！!]?",
        t,
    )
    if m:
        who = m.group(3).strip()
        if not who:
            return [], f"{m.group(1)} #{m.group(2)} 需要写执行员，例如「{m.group(1)} #{m.group(2)} 张三」。"
        return [
            {"action": "assign" if m.group(1) == "指派" else "reassign", "no": int(m.group(2)), "assignee": who}
        ], None
    m = re.fullmatch(
        r"升格\s*#?\s*(\d+)\s*[，,、：:]?\s*(?:办理人\s*[是为：:]?\s*|由\s*)?(.*?)\s*(?:来办|办理|负责|来做|办)?\s*[。！!]?",
        t,
    )
    if m:
        who = m.group(2).strip()
        if not who:
            return (
                [],
                f"升格 #{m.group(1)} 需要同时指定办理人，例如「升格 #{m.group(1)} 办理人：张三」或「升格 #{m.group(1)} 我来办」。",
            )
        a = {"action": "promote", "no": int(m.group(1)), "assignee": who}
        if self_role:
            a["self_role"] = self_role
        return [a], None
    if re.search(r"(别|不要|不用|暂不|先不|不必|不)\s*(?:#?\s*\d+\s*)?写入", t):
        return [], "这句话里有否定（如「别写入」），我不会写入。请明确回复「#序号 写入」或「#序号 否决」。"

    def kind(v):
        return "explain" if v == "说明" else "modify"

    for m in re.finditer(
        r"(?:#\s*(\d+)|(?<![\d-])(\d+)(?=\s*(?:修改|改|说明)))\s*(修改|改|说明)(?:一下)?\s*[：:]?\s*(.+?)(?=(?:[；;\n]|$))",
        t,
    ):
        acts.append(
            {"action": kind(m.group(3)), "no": int(m.group(1) or m.group(2)), "instruction": m.group(4).strip()}
        )
        used.append(m.span())
    for m in re.finditer(r"(修改|改|说明)(?:一下)?\s*#\s*(\d+)\s*[：:的]?\s*(.+?)(?=(?:[；;\n]|$))", t):
        if any(a <= m.start() < b for a, b in used):
            continue
        acts.append({"action": kind(m.group(1)), "no": int(m.group(2)), "instruction": m.group(3).strip()})
        used.append(m.span())
    rest = "".join(" " if any(a <= i < b for a, b in used) else ch for i, ch in enumerate(t))
    for m in re.finditer(rf"({LIST})\s*(?:确认)?(写入|否决)|(写入|否决)\s*({LIST})", rest):
        verb = m.group(2) or m.group(3)
        ns = _nums(m.group(1) or m.group(4))
        for n in ns:
            acts.append({"action": "confirm" if verb == "写入" else "reject", "no": n})
    for a in acts:
        if a["action"] in ("modify", "explain") and not a["instruction"]:
            return [], f"#{a['no']} 要怎么改？请说明，例如「#{a['no']} 修改：截止改到 10-23」。"
    seen = {}
    for a in acts:
        if a["no"] in seen and seen[a["no"]] != a["action"]:
            return [], f"#{a['no']} 同时出现了不同的处理，请只选一种：写入、修改或否决。"
        seen[a["no"]] = a["action"]
    if not acts:
        if re.search(r"\d", t) is None:
            if re.fullmatch(r"\s*(全部|都|所有|全都)(的)?(都)?(确认)?写入(吧|。|！|!)?\s*", t):
                return [{"action": "confirm_all_preview", "no": None}], None
            if re.fullmatch(r"\s*确认(全部写入)?(。|！|!)?\s*", t):
                return [{"action": "confirm_all_commit", "no": None}], None
            m = re.search(r"(修改|改|说明)(?:一下)?\s*[：:]?\s*(.+)", t)
            if m and m.group(2).strip():
                return [{"action": kind(m.group(1)), "no": None, "instruction": m.group(2).strip()}], None
            if re.fullmatch(r"\s*(确认)?(写入|否决)(吧|。|！|!)?\s*", t):
                return [{"action": "confirm" if "写入" in t else "reject", "no": None}], None
        return (
            [],
            "我没法从这句话确定要怎么处理。可以直接回复：写入、修改、说明或否决（可带序号，如「#8 写入」）；只有明确的「写入」才会写进待办。",
        )
    return acts, None
