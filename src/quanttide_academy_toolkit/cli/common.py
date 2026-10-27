"""CLI 公共工具：令牌脱敏、JSON 输出、中止清理与批次号校验。"""

import contextlib
import json
import re
import sys

from quanttide_academy_toolkit.core import config, db
from quanttide_academy_toolkit.intent import state as flow_common

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass  # 仅清理：stdout 不支持 reconfigure（如被测试捕获替换）时沿用原编码，不影响结果
TOKEN_RE = re.compile(r"(?i)\b(?:[ut]-[A-Za-z0-9._-]{16,}|bearer\s+\S+|[A-Za-z0-9_-]{32,})")
BATCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def redact(s):
    return TOKEN_RE.sub("***", str(s))


def out(o):
    print(json.dumps(o, ensure_ascii=False, default=str))


def abort(batch, reason, owns_lock=True):
    reason = redact(reason)
    try:
        cfg = config.load()
        with contextlib.closing(db.connect(cfg)) as d:
            h = db.holder(d)
            if owns_lock and (h is None or h[0] == batch):
                pushed = d.execute("select count(*) from messages where batch=? and pushed=1", (batch,)).fetchone()[0]
                with d:
                    d.execute("delete from watch_pending_cursors where batch=?", (batch,))
                    d.execute("delete from messages where batch=? and pushed=0", (batch,))
                db.release(d, batch)
                try:
                    flow_common.set_state(cfg, batch, stage="aborted", reason=reason)
                except OSError:
                    pass  # 仅清理：中止路径上尽力记状态；写不进去也不能盖住原始中止原因
                if pushed:
                    out({"status": "warn", "batch": batch, "reason": reason, "push": None})
                    return
    except Exception as e:
        reason += f"（清理暂存时也出错：{type(e).__name__}）"  # noqa: BLE001
    out({"status": "incomplete", "batch": batch, "reason": reason, "push": f"本轮未完成，原因是：{reason}"})
