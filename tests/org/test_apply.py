"""apply 与 writer：全部用假 reader 与假 runner，不发任何真实写请求。"""

import sqlite3

import pytest

from feishu_workflows.core import migrations
from feishu_workflows.org import apply as AP
from feishu_workflows.org import approve as A
from feishu_workflows.org import plan as P
from feishu_workflows.org import writer as W
from tests.org.helpers import approve
from tests.org.test_plan import cfg, fake_big


def setup(tmp_path, c=None, f=None):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    f = f or fake_big()
    c = c or cfg()
    pl = P.compute(c, f)
    P.store(d, pl)
    return d, f, c, pl


def runner(log):
    def run(req):
        log.append(req)
        return {"ok": True}

    return run


def test_apply_writes_approved_only_logs_and_replays(tmp_path):
    d, f, c, pl = setup(tmp_path)
    approve(c, d, f, pl)
    log = []
    g = {"held_chats": set(), "protected": set()}
    with pytest.raises(W.WriteRefused, match="未获批准"):
        W.execute(c, d, pl["plan_id"], 99, g, runner=runner(log))
    assert W.execute(c, d, pl["plan_id"], 1, g, runner=runner(log))["replayed"] is False  # 模拟中断前已写完第 1 条
    info = []
    r = AP.run(c, d, pl["plan_id"][:8], reader=f, runner=runner(log), notify=info.append)
    assert (
        r["done"] == [2]
        and r["replayed"] == [1]
        and [q[0] for q in log] == ["DELETE", "DELETE"]
        and "ou_ext" in str(log[0][3])
    )  # 续跑：幂等键防重复
    assert "北京时间" in info[0]["approval_sent_at"][0]  # 写入前打印批准消息发送时间
    ph = d.execute("select phase,result from org_ops order by id").fetchall()
    assert ph == [("before", None), ("after", "ok")] * 2
    assert d.execute("select status from org_plans").fetchone()[0] == "applied"
    d.close()


def test_apply_refuses_when_diff_changed(tmp_path):
    d, f, c, pl = setup(tmp_path)
    approve(c, d, f, pl)
    log = []
    f.data["chats"]["oc_a"]["members"]["ou_new"] = "t"  # 审批后有人进群
    with pytest.raises(AP.ApplyRefused, match="不一致"):
        AP.run(c, d, pl["plan_id"][:8], reader=f, runner=runner(log))
    assert log == [] and d.execute("select status from org_plans").fetchone()[0] == "stale"
    d.close()


def test_unapproved_plan_never_writes(tmp_path):
    d, f, c, pl = setup(tmp_path)
    log = []
    with pytest.raises(A.ApprovalError):
        AP.run(c, d, pl["plan_id"][:8], reader=f, runner=runner(log))
    with pytest.raises(W.WriteRefused, match="未批准"):
        W.execute(c, d, pl["plan_id"], 1, {"held_chats": set(), "protected": set()}, runner=runner(log))
    assert log == []
    d.close()


def test_hold_refused_at_apply_and_writer(tmp_path):
    m = [{"chat_id": "oc_a", "department": "od_a"}]
    d, f, c, pl = setup(tmp_path, cfg(mappings=m))
    approve(c, d, f, pl)
    log = []
    with pytest.raises(AP.ApplyRefused):
        AP.run(
            cfg(mappings=[{**m[0], "hold": True, "hold_reason": "r"}]),
            d,
            pl["plan_id"][:8],
            reader=f,
            runner=runner(log),
        )  # 批准后群被标暂缓
    assert log == []
    d.close()
    d2, _f2, c2, pl2 = setup(tmp_path / "b" if (tmp_path / "b").mkdir() is None else tmp_path)
    approve(c2, d2, _f2, pl2)
    with pytest.raises(W.WriteRefused, match="暂缓"):
        W.execute(c2, d2, pl2["plan_id"], 1, {"held_chats": {"oc_a"}, "protected": set()}, runner=runner(log))
    assert log == []
    d2.close()
