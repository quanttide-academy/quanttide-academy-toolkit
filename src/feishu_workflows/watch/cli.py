"""feishu-workflows watch 子命令：targets / plan / poll <batch> [--dry-run] / commit <batch> / abort <batch>。输出 JSON。
poll 与 intent 共用整轮运行锁（同一时间只跑一轮）；只读拉取，不调用任何写接口。"""

import time

from feishu_workflows.core import db, paths
from feishu_workflows.intent import flow_common, names
from feishu_workflows.watch import cursors, poll, targets

USAGE = "用法：feishu-workflows watch targets|plan|poll <batch> [--dry-run]|commit <batch>|abort <batch>"


def _init(cfg, now=None):
    """新目标（无游标）的起点：现在往回 backfill_days 天（默认 7，最多 30）。"""
    return int(now or time.time()) - targets.backfill_days(cfg) * 86400


def main(cfg, d, argv, out, batch_ok):
    sub = argv[2] if len(argv) > 2 else None
    try:
        ts = targets.load(cfg)
        targets.backfill_days(cfg)
    except targets.BadTargets as e:
        out({"status": "fail", "reason": str(e)})
        return 1
    if sub == "targets":
        out({"status": "ok", "targets": [{"key": t.key, "name": t.name, "accounts": len(t.accounts)} for t in ts]})
        return 0
    chats = [c["chat_id"] for c in ((cfg.get("scope") or {}).get("include_chats") or [])]
    if sub == "plan":
        sp = cursors.start_points(d, ts, chats, _init(cfg))
        out({"status": "ok", "scope": cfg.get("scope") is not None, "chats": [{"chat_id": c, **sp[c]} for c in chats]})
        return 0
    if sub not in ("poll", "commit", "abort") or len(argv) < 4:
        out({"status": "fail", "reason": USAGE})
        return 2
    batch = argv[3]
    if not batch_ok(batch):
        out({"status": "fail", "reason": "batch 只能含字母数字 . _ -"})
        return 2
    if sub == "abort":
        cursors.abort(d, batch)
        db.release(d, batch)
        out({"status": "aborted", "batch": batch})
        return 0
    if sub == "commit":
        try:
            db.require(d, batch)
        except db.Locked as e:
            out({"status": "locked", "batch": batch, "reason": str(e)})
            return 30
        cursors.commit(d, batch)
        db.release(d, batch)
        out({"status": "committed", "batch": batch})
        return 0
    dry = "--dry-run" in argv
    if not dry:
        try:
            db.acquire(d, batch)
        except db.Locked as e:
            out({"status": "locked", "batch": batch, "reason": str(e)})
            return 30
        cursors.sync_targets(d, ts)
    try:
        rep = poll.poll(cfg, d, batch, ts, _init(cfg), int(time.time()), dry_run=dry)
    except poll.DmUnavailable as e:  # 私聊来源开着却读不了：整轮报错停止，不静默跳过
        if not dry:
            cursors.abort(d, batch)
            db.release(d, batch)
        out({"status": "fail", "batch": batch, "reason": str(e)})
        return 1
    if dry:
        out({"status": "ok", "dry_run": True, "counts": rep["counts"], "chats": rep["chats"]})
        return 0
    names.fill(cfg, rep["messages"], paths.name_cache(cfg))
    flow_common.write_messages(cfg, batch, rep["messages"])
    out(
        {
            "status": "ok",
            "batch": batch,
            "counts": rep["counts"],
            "chats": rep["chats"],
            "next": {
                "step": "host_llm",
                "do": f"按 intent 的 classify.md 处理 data/work/{batch}/messages.json，之后 validate/render 照常",
            },
        }
    )
    return 10
