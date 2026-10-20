#!/usr/bin/env python3
"""feishu-workflows 命令行入口（Windows / macOS / Linux 通用，任何宿主 Agent 都可调用）。完整说明见 AGENTS.md。
所有子命令都输出一行 JSON（--json 可写可不写）。退出码：0 成功；10 等宿主完成大模型步骤；20 本轮已 abort；30 被锁/别的批次未收尾；1 命令失败（未 abort）；2 用法错误。
  feishu-workflows next [batch]                         根据状态告诉宿主下一步（可在中断后续跑）
  feishu-workflows doctor                               自检：配置、lark-cli、令牌环境变量（只报是否设置）
  feishu-workflows fetch <batch> [--from messages.json]  加锁 → 清理孤儿 → 同步跟进清单 → 只读采集 → data/work/<batch>/messages.json，退出码 10
  feishu-workflows org depts|plan [--dry-run]|show <id>|approve <审批消息 message_id>|apply <id> [--only 1,3]|status  部门↔群对齐（plan 只读，apply 须先批准）
  feishu-workflows watch targets|plan|poll <batch> [--dry-run]|commit <batch>|abort <batch>  多目标监听（只读拉取，poll 退出码 10）
  feishu-workflows validate <batch>                     （别名 ingest）校验宿主写的 topics.json 并入库；不合格 abort（20）
  feishu-workflows render <batch>                       生成 cards.txt / archive.md / versions.json
  feishu-workflows pushed <batch>                       宿主把 cards.txt 推给用户之后调用
  feishu-workflows reply <batch> "<用户原话>" [--quote <fingerprint>@<version>]   唯一的用户话语解释器
  feishu-workflows write <batch>                        有令牌直接写；否则出 data/work/<batch>/writes.json 交宿主连接器执行
  feishu-workflows mark-written <batch> <key> <ext_id|fail>
  feishu-workflows commit <batch> | abort <batch> <原因> | release <batch>
  feishu-workflows selftest                             用 tests/fixtures/ 合成数据离线跑 fetch→validate→render→reply→write"""

import contextlib
import json
import sys
from pathlib import Path

from quanttide_academy.cli.common import BATCH_RE, TOKEN_RE, abort, out, redact
from quanttide_academy.cli.doctor import doctor, selftest
from quanttide_academy.cli.next_step import next_step
from quanttide_academy.core import config, db
from quanttide_academy.intent import (
    collect,
    followups,
    outputs,
)
from quanttide_academy.intent import fetch as flow_fetch
from quanttide_academy.intent import reply as flow_reply
from quanttide_academy.intent import state as flow_common
from quanttide_academy.intent import write as flow_write
from quanttide_academy.org import cli as org_cli
from quanttide_academy.watch import cli as watch_cli
from quanttide_academy.watch import cursors as _wc

__all__ = ["BATCH_RE", "TOKEN_RE", "abort", "doctor", "entry", "main", "next_step", "out", "redact", "selftest"]


def main(argv):
    argv = [a for a in argv if a != "--json"]
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "selftest":
        return selftest(main)
    if not config.config_path().exists():
        out(
            {
                "status": "fail",
                "reason": "没有 config.yaml",
                "next": {
                    "step": "setup",
                    "do": "feishu-workflows-setup questions --json",
                    "ask_user": "首次使用，需要先回答几个配置问题",
                },
            }
        )
        return 1
    cfg = config.load()
    with contextlib.closing(db.connect(cfg)) as d:
        try:  # 跟进清单读不到必须明确报错，不能当作空清单继续（否则去重和关联会悄悄失效）
            cfg["_followup_titles"] = followups.titles(cfg, d)
            cfg["_followup_followers"] = followups.followers(cfg, d)
        except followups.FollowupError as e:
            out(
                {
                    "status": "fail",
                    "reason": str(e),
                    "next": {"step": "fix_config", "do": "检查 config.yaml 的 followups.path，或留空跳过跟进清单"},
                }
            )
            return 1
        if cmd == "doctor":
            out({"status": "ok", **doctor(cfg)})
            return 0
        if cmd == "check":
            ok, msg = outputs.load(cfg).check()
            out({"status": "ok" if ok else "fail", "msg": redact(msg)})
            return 0 if ok else 1
        if cmd == "org":
            return org_cli.main(cfg, d, argv, out)
        if cmd == "watch":
            return watch_cli.main(cfg, d, argv, out, lambda b: bool(BATCH_RE.match(b)))
        if cmd == "next":
            out({"status": "ok", **next_step(cfg, d, argv[2] if len(argv) > 2 else None)})
            return 0
        if len(argv) < 3:
            print(__doc__)
            return 2
        batch = argv[2]
        if cmd not in (
            "fetch",
            "validate",
            "ingest",
            "render",
            "pushed",
            "reply",
            "write",
            "mark-written",
            "commit",
            "abort",
            "release",
        ):
            out({"status": "fail", "reason": f"未知命令 {cmd}"})
            return 2
        if not BATCH_RE.match(batch):
            out({"status": "fail", "reason": "batch 只能含字母数字 . _ -"})
            return 2
        if cmd == "abort":
            abort(batch, " ".join(argv[3:]) or "未知原因")
            return 20
        if cmd == "release":
            db.release(d, batch)
            out({"status": "ok", "released": batch})
            return 0
        try:
            if cmd == "commit":
                db.require(d, batch)
            else:
                db.renew(d, batch)  # 除 release 外每个子命令都续锁（TTL 1 小时）
        except db.Locked as e:
            out({"status": "locked", "batch": batch, "reason": str(e)})
            return 30
        if cmd != "fetch" and flow_common.state(cfg, batch)["stage"] in ("aborted", "committed"):
            out(
                {
                    "status": "fail",
                    "batch": batch,
                    "reason": f"批次已{flow_common.state(cfg, batch)['stage']}，请用新批次",
                }
            )
            return 20
        try:
            if cmd == "fetch":
                if cfg.get("scope") is None:
                    abort(batch, collect.NO_SCOPE)
                    return 20
                src = argv[argv.index("--from") + 1] if "--from" in argv else None
                with d:
                    db.cleanup_orphans(d, keep=batch)
                    followups.sync(cfg, d)
                    cfg["_followup_titles"] = followups.titles(cfg, d)
                    cfg["_followup_followers"] = followups.followers(cfg, d)
                    if src:
                        msgs = json.loads(Path(src).read_text(encoding="utf-8"))
                        msgs = msgs.get("messages", msgs)
                        rep = {"offline": True}
                        sc = cfg.get("scope")
                        if sc is not None:  # 离线导入也按白名单过滤，并按配置标外部群
                            inc = {str(x["chat_id"]): x for x in sc.get("include_chats") or []}
                            skipped = sorted(
                                {m.get("chat") or m.get("chat_id") for m in msgs if m.get("chat_id") not in inc}
                            )
                            msgs = [
                                {**m, "external_chat": bool(inc[m["chat_id"]].get("external"))}
                                for m in msgs
                                if m.get("chat_id") in inc
                            ]
                            rep["skipped_chats"] = skipped
                    else:
                        rep = collect.run(cfg, d, batch)
                        msgs = rep.pop("messages")
                n = flow_common.write_messages(cfg, batch, msgs)
                if not n:
                    flow_common.set_state(cfg, batch, stage="pushed", items=[])
                    out({"status": "ok", "batch": batch, "messages": 0, "next": f"feishu-workflows commit {batch}"})
                    return 0
                w = flow_common.wd(cfg, batch)
                out(
                    {
                        "status": "waiting_llm",
                        "batch": batch,
                        "messages": n,
                        **{
                            k: v
                            for k, v in rep.items()
                            if k in ("new_chats", "left_chats", "offline", "skipped_chats", "suggested_chats")
                        },
                        "input": str(w / "messages.json"),
                        "prompt": "src/quanttide_academy/intent/prompts/classify.md",
                        "output": str(w / "topics.json"),
                        "then": f"feishu-workflows validate {batch}",
                    }
                )
                return 10
            if cmd in ("validate", "ingest"):
                items = flow_fetch.validate_batch(cfg, d, batch)
                out(
                    {
                        "status": "ok",
                        "batch": batch,
                        "items": len(items),
                        "warnings": flow_common.state(cfg, batch).get("warnings") or [],
                        "next": f"feishu-workflows render {batch}",
                    }
                )
                return 0
            if cmd == "render":
                out({"status": "ok", "batch": batch, **flow_fetch.render_batch(cfg, d, batch)})
                return 0
        except Exception as e:  # noqa: BLE001
            abort(batch, f"{type(e).__name__}: {e}")
            return 20
        try:
            if cmd == "pushed":
                with d:
                    n = d.execute("update messages set pushed=1 where batch=?", (batch,)).rowcount
                flow_common.set_state(cfg, batch, stage="pushed")
                out({"status": "ok", "pushed": n})
                return 0
            if cmd == "reply":
                if len(argv) < 4:
                    out({"status": "fail", "reason": "缺用户原话"})
                    return 2
                q = argv[argv.index("--quote") + 1] if "--quote" in argv else None
                out({"status": "ok", "batch": batch, **flow_reply.handle_reply(cfg, d, batch, argv[3], q)})
                return 0
            if cmd == "write":
                out({"status": "ok", "batch": batch, **flow_write.run_write(cfg, d, batch)})
                return 0
            if cmd == "mark-written":
                out({"status": "ok", **flow_write.mark_written(cfg, d, batch, argv[3], argv[4])})
                return 0
            if cmd == "commit":
                _wc.commit(d, batch)
                db.release(d, batch)
                flow_common.set_state(cfg, batch, stage="committed")
                out({"status": "committed", "batch": batch})
                return 0
            out({"status": "fail", "reason": f"未知命令 {cmd}"})
            return 2
        except Exception as e:  # noqa: BLE001
            out({"status": "fail", "reason": redact(f"{type(e).__name__}: {e}")})
            return 1


def entry():
    sys.exit(main(sys.argv))


if __name__ == "__main__":
    entry()
