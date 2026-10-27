"""feishu-workflows org 子命令：depts | plan [--dry-run] | show <id> | approve <message_id> | apply <id> [--only 1,3] | status。输出 JSON。
退出码：0 成功；40 读不到部门；41 配置不合规或计划被保护规则拒绝；42 apply 被拒（未批准、计划已变化、写入被拒）；30 运行锁被占。"""

import json

from quanttide_academy_toolkit.core import db, paths
from quanttide_academy_toolkit.org import apply as AP
from quanttide_academy_toolkit.org import approve as A
from quanttide_academy_toolkit.org import conf as C
from quanttide_academy_toolkit.org import depts
from quanttide_academy_toolkit.org import plan as P
from quanttide_academy_toolkit.org import read as R

USAGE = "用法：feishu-workflows org depts|plan [--dry-run]|show <id>|approve <审批消息 message_id>|apply <id> [--only 1,3]|status"


def _cache_depts(cfg, tree):
    p = paths.data_dir(cfg) / "org_depts.json"
    p.parent.mkdir(parents=True, exist_ok=True)  # 只存 部门 id→名字
    p.write_text(json.dumps({d["id"]: d["name"] for d in tree}, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def main(cfg, d, argv, out, reader=R, runner=None):
    sub = argv[2] if len(argv) > 2 else None
    arg = argv[3] if len(argv) > 3 and not argv[3].startswith("--") else None
    try:
        if sub == "depts":  # 只读：部门 ID/名字 + 建议勾选，写本地文件；输出只给计数
            s = depts.suggest(cfg, reader)
            _cache_depts(cfg, s["tree"])
            f = depts.write(cfg, s)
            out(
                {
                    "status": "ok",
                    "file": f,
                    "departments": len(s["tree"]),
                    "root_found": bool(s["root"]),
                    "hold_matched": sum(1 for v in s["holds"].values() if v),
                    "hold_unmatched": sum(1 for v in s["holds"].values() if not v),
                    "mapping_suggestions": len(s["mappings"]),
                }
            )
            return 0
        if sub == "plan":
            p = P.compute(cfg, reader)
            if "--dry-run" not in argv:
                P.store(d, p)
            out(
                {
                    "status": "ok",
                    "dry_run": "--dry-run" in argv,
                    "plan_id": p["plan_id"],
                    "items": len(p["items"]),
                    "held": len(p["held"]),
                    "deferred": p["deferred"],
                    "groups": len(p["groups"]),
                    "departments": p["departments"],
                    "in_scope": p["in_scope"],
                    "text": P.render(p),
                }
            )
            return 0
        if sub == "show" and arg:
            pid, items, st, ap = A.find(d, arg, ("pending", "approved", "applying", "applied", "stale"))
            out({"status": "ok", "plan_id": pid, "state": st, "approved": ap, "lines": [P.line(x) for x in items]})
            return 0
        if sub == "approve" and arg:
            out({"status": "ok", **A.approve(cfg, d, arg, reader)})
            return 0
        if sub == "status":
            out(
                {
                    "status": "ok",
                    "plans": [
                        {"plan_id": r[0][:8], "state": r[1]}
                        for r in d.execute(
                            "select plan_id,status from org_plans where is_deleted=0 order by id desc limit 10"
                        )
                    ],
                }
            )
            return 0
        if sub == "apply" and arg:
            only = (
                [int(x) for x in argv[argv.index("--only") + 1].replace("，", ",").split(",")]
                if "--only" in argv
                else None
            )
            lock = f"org-{arg[:8]}"
            try:
                db.acquire(d, lock)
            except db.Locked as e:
                out({"status": "locked", "reason": str(e)})
                return 30
            try:
                out({"status": "ok", **AP.run(cfg, d, arg, only, reader=reader, runner=runner, notify=out)})
                return 0
            finally:
                db.release(d, lock)
    except R.DeptReadError as e:
        out({"status": "fail", "reason": str(e)})
        return 40
    except (C.BadOrgConfig, P.PlanRefused, R.ChatReadError) as e:
        out({"status": "fail", "reason": str(e)})
        return 41
    except (A.ApprovalError, AP.ApplyRefused) as e:
        out({"status": "fail", "reason": str(e)})
        return 42
    out({"status": "fail", "reason": USAGE})
    return 2
