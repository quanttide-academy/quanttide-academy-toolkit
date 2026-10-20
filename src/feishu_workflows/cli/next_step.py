"""CLI 状态机下一步提示：next_step。"""

import datetime

from feishu_workflows.cli.common import BATCH_RE
from feishu_workflows.core import db, paths
from feishu_workflows.intent import reply as flow_reply
from feishu_workflows.intent import state as flow_common
from feishu_workflows.intent import write as flow_write


def next_step(cfg, d, batch=None):
    h = db.holder(d)
    if not batch:
        batch = h[0] if h else None
        if not batch:
            dirs = sorted(
                (
                    p
                    for p in paths.work_dir(cfg).iterdir()
                    if p.is_dir() and BATCH_RE.match(p.name) and (p / "state.json").exists()
                ),
                key=lambda p: p.stat().st_mtime,
            )
            if dirs and flow_common.state(cfg, dirs[-1].name)["stage"] not in ("committed", "aborted"):
                batch = dirs[-1].name
    if not batch:
        nb = datetime.datetime.now(flow_common.TZ).strftime("%Y%m%d-%H%M")
        return {"step": "fetch", "why": "没有进行中的批次", "do": f"feishu-workflows fetch {nb} --json"}
    if h and h[0] != batch:
        return {
            "step": "wait",
            "batch": batch,
            "why": f"批次 {h[0]} 正持有运行锁",
            "do": f"feishu-workflows next {h[0]} --json",
        }
    st = flow_common.state(cfg, batch)
    s = st["stage"]
    w = paths.work_dir(cfg, batch)
    if s in ("new", "fetched"):
        if not (w / "messages.json").exists():
            return {"step": "fetch", "batch": batch, "why": "还没采集", "do": f"feishu-workflows fetch {batch} --json"}
        if not (w / "topics.json").exists():
            return {
                "step": "llm",
                "batch": batch,
                "why": "等宿主完成识别（单次须在 30 分钟内完成）",
                "do": f"关闭写入类工具；读 src/feishu_workflows/intent/prompts/classify.md 和 {w / 'messages.json'}，按约定写出 {w / 'topics.json'}，然后 feishu-workflows validate {batch} --json",
            }
        return {
            "step": "validate",
            "batch": batch,
            "why": "topics.json 已就绪",
            "do": f"feishu-workflows validate {batch} --json",
        }
    if s == "needs_edit":
        return {
            "step": "llm_edit",
            "batch": batch,
            "why": "用户对部分卡片提了修改或说明（序号见 needs_edit）",
            "needs_edit": [int(x) for x in st.get("needs_edit") or []],
            "do": f"按 reply 返回的 instruction，只改 {w / 'topics.json'} 里 needs_edit 所列序号的条目（说明若不涉及字段可不改），然后 feishu-workflows validate {batch} --json",
        }
    if s == "validated":
        return {"step": "render", "batch": batch, "why": "已校验", "do": f"feishu-workflows render {batch} --json"}
    if s == "rendered":
        return {
            "step": "push",
            "batch": batch,
            "why": "卡片已生成，尚未推送",
            "do": f"把 {w / 'cards.txt'} 原样发给用户，然后 feishu-workflows pushed {batch} --json",
        }
    if s == "pushed":
        if flow_write.unwritten_confirmed(cfg, d, batch) or any(
            r[0] != "done" for r in d.execute("select status from write_actions where batch=?", (batch,))
        ):
            return {
                "step": "write",
                "batch": batch,
                "why": "有已确认未写完的条目",
                "do": f"feishu-workflows write {batch} --json；若输出 mode=plan，按 {w / 'writes.json'} 逐个执行并 mark-written，再次 write 直到 actions 为空",
            }
        pend = flow_reply.pending_cards(cfg, d, batch)
        if pend:
            return {
                "step": "wait_user",
                "batch": batch,
                "why": f"待用户逐条确认：{pend}",
                "do": f'把用户的原话交给 feishu-workflows reply {batch} "<原话>" --json',
                "ask_user": "可以直接回复：写入、修改、说明或否决（可带序号）。",
            }
        return {
            "step": "commit",
            "batch": batch,
            "why": "所有卡片已处理",
            "do": f"feishu-workflows commit {batch} --json",
        }
    return {
        "step": "idle",
        "batch": batch,
        "why": f"批次已{ {'committed': '收尾', 'aborted': '中止'}.get(s, s) }",
        "do": "用户要新一轮时：feishu-workflows next --json 之后按提示 fetch",
    }
