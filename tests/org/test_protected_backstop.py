"""保护名单兜底：plan、apply、writer 三层各自拒绝「移出保护名单里的人」与「撤销其管理员」。全部离线、假 runner。"""

import json
import sqlite3

import pytest

from feishu_workflows.core import migrations
from feishu_workflows.org import apply as AP
from feishu_workflows.org import plan as P
from feishu_workflows.org import writer as W
from tests.org.test_plan import cfg, fake_big

KINDS = ["remove_member", "unset_admin"]


def runner(log):
    return lambda q: log.append(q)


@pytest.mark.parametrize(
    "who,c", [("ou_me", cfg()), ("ou_ext", cfg(protected=["ou_ext"])), ("ou_old", cfg(app_open_id="ou_old"))]
)
def test_plan_refuses_when_protected_leaks_into_removals(monkeypatch, who, c):
    monkeypatch.setattr(
        P, "_candidates", lambda cur, want, prot: sorted(set(cur) - want)
    )  # 模拟候选计算出错，保护名单漏进移出
    with pytest.raises(P.PlanRefused, match="保护名单"):
        P.compute(c, fake_big())


def test_plan_refuses_owner_leak(monkeypatch):
    f = fake_big()
    f.data["chats"]["oc_a"]["owner"] = "ou_old"
    monkeypatch.setattr(P, "_candidates", lambda cur, want, prot: sorted(set(cur) - want))
    with pytest.raises(P.PlanRefused, match="保护名单"):
        P.compute(cfg(), f)


@pytest.mark.parametrize("kind", KINDS)
def test_plan_invariant_both_kinds(kind):
    with pytest.raises(P.PlanRefused, match="撤销管理员"):
        P.check_protected([{"kind": kind, "person": "ou_me"}], {"ou_me"})
    P.check_protected(
        [{"kind": kind, "person": "ou_x"}, {"kind": "add_member", "person": "ou_me"}], {"ou_me"}
    )  # 非保护对象、或拉人进群：放行


def approved_db(tmp_path, kind, person):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    items = [
        {
            "idx": 1,
            "kind": kind,
            "chat_id": "oc_a",
            "department": "od_a",
            "person": person,
            "external": False,
            "reason": "x",
        }
    ]
    pid = P.plan_id(items)
    d.execute(
        "insert into org_plans(plan_id,items_json,status,approved_items) values(?,?,'approved','[1]')",
        (pid, json.dumps(items, sort_keys=True)),
    )
    d.commit()
    return d, pid, items


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "who,c",
    [("ou_me", cfg()), ("ou_owner2", cfg()), ("ou_p", cfg(protected=["ou_p"])), ("ou_app", cfg(app_open_id="ou_app"))],
)
def test_apply_refuses_protected(tmp_path, monkeypatch, kind, who, c):
    d, pid, items = approved_db(tmp_path, kind, who)
    f = fake_big()
    if who == "ou_owner2":
        f.data["chats"]["oc_a"]["owner"] = "ou_owner2"
    monkeypatch.setattr(
        AP.P,
        "compute",
        lambda cfg, reader: {"items": items, "groups": [{"chat_id": "oc_a", "held": False}], "deferred": 0},
    )  # 重算与批准一致，只剩保护检查
    monkeypatch.setattr(
        AP.A, "reverify", lambda cfg, d, pid, reader: ["2026-10-20 05:00:00（北京时间）"]
    )  # 来源核验另测，这里只测保护检查
    monkeypatch.setattr(AP.W, "execute", lambda *a, **k: pytest.fail("apply 应在调用 writer 之前拒绝"))
    log = []
    with pytest.raises(AP.ApplyRefused, match="保护名单"):
        AP.run(c, d, pid[:8], reader=f, runner=runner(log))
    assert log == [] and d.execute("select count(*) from org_ops").fetchone()[0] == 0
    d.close()


@pytest.mark.parametrize("kind", KINDS)
def test_writer_refuses_protected(tmp_path, kind):
    d, pid, _ = approved_db(tmp_path, kind, "ou_p")
    log = []
    with pytest.raises(W.WriteRefused, match="保护名单"):
        W.execute(cfg(), d, pid, 1, {"held_chats": set(), "protected": {"ou_p"}}, runner=runner(log))
    assert log == [] and d.execute("select count(*) from org_ops").fetchone()[0] == 0
    assert (
        W.execute(cfg(), d, pid, 1, {"held_chats": set(), "protected": {"ou_other"}}, runner=runner(log))["result"]
        == "ok"
        and len(log) == 1
    )
    d.close()  # 对照：非保护对象放行
