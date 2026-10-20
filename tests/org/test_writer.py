"""writer：只收已批准计划的条目；保护名单、外部成员、未开启动作、写客户端未启用都拒绝。全部用假 runner。"""

import json
import types

import pytest

from feishu_workflows.org import writer as W
from tests.org.helpers import approve
from tests.org.test_apply import runner, setup
from tests.org.test_plan import cfg


def test_writer_guards_protected_external_and_disabled(tmp_path):
    d, f, c, pl = setup(tmp_path)
    approve(c, d, f, pl)
    log = []
    with pytest.raises(W.WriteRefused, match="保护名单"):
        W.execute(c, d, pl["plan_id"], 1, {"held_chats": set(), "protected": {"ou_ext"}}, runner=runner(log))
    with pytest.raises(W.WriterDisabled):
        W.execute(
            c, d, pl["plan_id"], 1, {"held_chats": set(), "protected": set()}
        )  # 没注入 runner 且 org.enabled=false：不构造写客户端
    assert log == [] and W.request({"kind": "add_member", "chat_id": "oc", "person": "ou"})[0] == "POST"
    d.close()


def test_extra_kinds_need_config(tmp_path):
    d, _f, c, _pl = setup(tmp_path)
    d.execute(
        "insert into org_plans(plan_id,items_json,status,approved_items) values('e'*64,?,'approved','[1]')".replace(
            "'e'*64", "'" + "e" * 64 + "'"
        ),
        (json.dumps([{"idx": 1, "kind": "disband", "chat_id": "oc_a", "person": None}]),),
    )
    d.commit()
    log = []
    with pytest.raises(W.WriteRefused, match="未在 config"):
        W.execute(c, d, "e" * 64, 1, {"held_chats": set(), "protected": set()}, runner=runner(log))
    assert (
        W.execute(
            cfg(allow={"disband": True}), d, "e" * 64, 1, {"held_chats": set(), "protected": set()}, runner=runner(log)
        )["result"]
        == "ok"
        and log[0][0] == "DELETE"
    )
    d.close()


def test_external_never_added(tmp_path):
    d, _f, c, _pl = setup(tmp_path)
    d.execute(
        "insert into org_plans(plan_id,items_json,status,approved_items) values(?,?,'approved','[1]')",
        (
            "f" * 64,
            json.dumps([{"idx": 1, "kind": "add_member", "chat_id": "oc_a", "person": "ou_ext", "external": True}]),
        ),
    )
    d.commit()
    log = []
    with pytest.raises(W.WriteRefused, match="外部成员"):
        W.execute(c, d, "f" * 64, 1, {"held_chats": set(), "protected": set()}, runner=runner(log))
    assert log == []
    d.close()


def test_writer_runner_failure_logs_error_and_real_runner(tmp_path, monkeypatch):
    d, f, c, pl = setup(tmp_path)
    approve(c, d, f, pl)
    calls = []
    monkeypatch.setattr(W, "find", lambda cfg: "/fake/lark-cli")

    def fake_run(args, **kw):
        calls.append(args)
        return types.SimpleNamespace(returncode=1 if len(calls) == 1 else 0, stdout="secret", stderr="secret")

    monkeypatch.setattr(W.subprocess, "run", fake_run)
    ec = cfg(enabled=True)
    g = {"held_chats": set(), "protected": set()}
    with pytest.raises(W.WriteRefused, match="写入失败：error: WriteRefused"):
        W.execute(ec, d, pl["plan_id"], 1, g)
    rows = d.execute(
        "select phase,result from org_ops where plan_id=? and idx=1 order by id", (pl["plan_id"],)
    ).fetchall()
    assert rows == [("before", None), ("after", "error: WriteRefused")]
    assert W.execute(ec, d, pl["plan_id"], 1, g) == {"replayed": False, "result": "ok"}
    assert W.execute(ec, d, pl["plan_id"], 1, g) == {"replayed": True, "result": "ok"}
    d.execute("update org_plans set approved_items='[1, 2, 99]' where plan_id=?", (pl["plan_id"],))
    d.commit()
    with pytest.raises(W.WriteRefused, match="计划里没有这一条"):
        W.execute(ec, d, pl["plan_id"], 99, g)
    d.close()
