"""watch 端到端只读检查：用本地 A 组范围和真实 watch 目标，临时库里跑 watch plan 与 poll --dry-run（只读 GET，不写库、不推进游标）。
缺本地数据或 lark-cli 时跳过；只断言计数，不输出群 ID 或姓名。"""

import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest
import yaml

from feishu_workflows.core import migrations
from feishu_workflows.watch import cursors, poll, targets
from feishu_workflows.watch.cli import _init

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "local" / "e2e-scope-A.json"
pytestmark = pytest.mark.skipif(
    not (
        SCOPE.exists()
        and (ROOT / "config.yaml").exists()
        and shutil.which("lark-cli", path=str(Path.home() / ".local" / "bin"))
    ),
    reason="缺本地数据或 lark-cli",
)


def test_watch_dry_run_read_only():
    real = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    cfg = {**real, "scope": json.loads(SCOPE.read_text(encoding="utf-8"))}
    ts = targets.load(cfg)
    assert ts
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "s.db"
        migrations.migrate(p)
        d = sqlite3.connect(str(p))
        now = int(time.time())
        init = _init(cfg, now)  # 新目标回溯 backfill_days（默认 7 天）
        sp = cursors.start_points(d, ts, [c["chat_id"] for c in cfg["scope"]["include_chats"]], init)
        assert len(sp) == 2 and all(v["start"] == init for v in sp.values())
        rep = poll.poll(cfg, d, "e2e-watch", ts, init, now, dry_run=True)
        assert rep["chats"] == 2 and sum(rep["counts"].values()) >= 15  # A 组至少包含 #6～#10 用到的 15 条
        assert d.execute("select count(*) from watch_pending_cursors").fetchone()[0] == 0
