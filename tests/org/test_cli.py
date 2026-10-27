"""org CLI：全部经假 reader / 假 runner；退出码 40/41/42。"""

import json
import sqlite3

from quanttide_academy_toolkit.core import migrations
from quanttide_academy_toolkit.org import cli as O
from tests.org.helpers import message
from tests.org.test_plan import cfg, fake_big


def go(c, d, *a, reader=None, runner=None):
    got = []
    rc = O.main(c, d, ["fw", "org", *a], got.append, reader=reader or fake_big(), runner=runner)
    return rc, got[-1]


def test_plan_approve_apply_flow(tmp_path):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    c = {**cfg(), "paths": {"data_dir": str(tmp_path)}}
    f = fake_big()
    log = []
    rc, r = go(c, d, "depts", reader=f)
    assert (
        rc == 0
        and r["departments"] == 5
        and r["root_found"]
        and r["hold_matched"] == 1
        and r["mapping_suggestions"] == 2
    )
    assert (tmp_path / "org_depts_suggest.md").exists() and "oc_" not in json.dumps(r).replace(
        r["file"], ""
    )  # 输出只给计数
    assert json.loads((tmp_path / "org_depts.json").read_text(encoding="utf-8"))["od_a"] == "技术部"
    rc, r = go(c, d, "plan", "--dry-run", reader=f)
    assert rc == 0 and d.execute("select count(*) from org_plans").fetchone()[0] == 0
    rc, r = go(c, d, "plan", reader=f)
    pid = r["plan_id"][:8]
    assert r["items"] == 2
    rc, r = go(c, d, "apply", pid, reader=f)
    assert rc == 42  # 未批准
    rc, r = go(c, d, "approve", "om_none", reader=f)
    assert rc == 42  # 没有这条审批消息
    rc, r = go(c, d, "approve", message(f, f"批准 {pid}"), reader=f)
    assert rc == 0 and r["approved"] == [1, 2]
    got = []
    rc = O.main(c, d, ["fw", "org", "apply", pid, "--only", "2"], got.append, reader=f, runner=lambda q: log.append(q))
    assert (
        rc == 0
        and got[0]["status"] == "info"
        and "北京时间" in got[0]["approval_sent_at"][0]
        and got[-1]["done"] == [2]
        and len(log) == 1
    )  # 写入前先打印批准时间
    rc, r = go(c, d, "status")
    assert r["plans"][0]["state"] == "applying"
    d.close()  # 只执行了 --only 2


def test_exit_codes(tmp_path):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    assert go(cfg(), d, "plan", reader=fake_big(fail_dept=True))[0] == 40
    assert go(cfg(protected=["x"]), d, "plan")[0] == 41
    assert go(cfg(), d, "nope")[0] == 2
    d.close()
