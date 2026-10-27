"""渲染：candidates/YYYYMMDD-HHMM.md 为内部存档；同名 .card.txt 为推送正文（任务卡片）。"""

import datetime
import json
from zoneinfo import ZoneInfo

from quanttide_academy_toolkit.core import paths
from quanttide_academy_toolkit.core.config import TZ_NAME
from quanttide_academy_toolkit.intent.item import card_version, to_card, to_markdown


def render(data, cfg):
    stem = paths.candidates_dir(cfg) / datetime.datetime.now(ZoneInfo(TZ_NAME)).strftime("%Y%m%d-%H%M")
    md = [to_markdown(it, cfg) for it in data.get("items", [])]
    card = [data.get("header", "")] + [to_card(it, cfg) for it in data.get("items", [])]
    tail = []
    for k, t in [
        ("merged", "已合并"),
        ("followup_hits", "已在跟进"),
        ("rejected_hits", "已否决不再推"),
        ("retry", "待重试（上轮写入失败）"),
    ]:
        if data.get(k):
            tail += [f"{t}："] + [f"· {x}" for x in data[k]]
    card += (["\n".join(tail)] if tail else []) + ["回复「#序号 写入」「#序号 修改：说明」或「#序号 否决」即可。"]

    def w(p, s):
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(s)

    w(stem.with_suffix(".md"), "\n\n".join(md) + "\n")
    w(stem.with_suffix(".card.txt"), "\n\n".join(card) + "\n")
    # 推送时存下 序号→fingerprint/卡片版本，确认时据此校验
    vers = {
        str(it["no"]): {"fingerprint": it.get("fingerprint"), "version": card_version(it, cfg)}
        for it in data.get("items", [])
    }
    w(stem.with_suffix(".versions.json"), json.dumps(vers, ensure_ascii=False, indent=1))
    return stem.with_suffix(".card.txt")
