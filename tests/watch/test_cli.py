import json
import os
from pathlib import Path

import yaml

from feishu_workflows.watch import poll as P
from tests.helpers import run
from tests.watch.test_poll import raw


def setcfg(extra):
    p = Path(os.environ["FEISHU_INTENT_CONFIG"])
    c = yaml.safe_load(p.read_text(encoding="utf-8"))
    c.update(extra)
    p.write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")


W = {
    "watch": [{"name": "甲", "accounts": {"ou_a": "内部"}}, {"name": "乙", "accounts": {"ou_b": "内部"}}],
    "initial_since": "2026-10-16",
}


def test_targets_and_plan(env):
    setcfg(W)
    rc, r = run("watch", "targets")
    assert rc == 0 and [t["name"] for t in r["targets"]] == ["甲", "乙"] and r["targets"][0]["accounts"] == 1
    rc, r = run("watch", "plan")
    assert rc == 0 and r["chats"][0]["chat_id"] == "oc_demo" and set(r["chats"][0]["targets"]) == {"ou_a", "ou_b"}
    setcfg({"watch": [{"name": "甲", "accounts": {"bad": "x"}}]})
    rc, r = run("watch", "targets")
    assert rc == 1 and "ou_" in r["reason"]


def test_poll_commit_abort(env, monkeypatch):
    _cfg, tmp = env
    setcfg(W)

    def call(c, *a, **k):  # 同一个只读客户端：按路径分发
        assert a[:2] == ("api", "GET")
        if a[2] == "/open-apis/im/v1/messages":
            return [
                {
                    "code": 0,
                    "data": {
                        "items": [
                            raw("m1", "ou_a", 1792400000, "请看 @_user_1", mentions=[{"id": "ou_b", "key": "@_user_1"}])
                        ]
                    },
                }
            ]
        return [{"code": 0, "data": {"items": []}}]

    monkeypatch.setattr(P.larkcli, "call", call)
    rc, r = run("watch", "poll", "w1", "--dry-run")
    assert rc == 0 and r["counts"] == {"ou_a": 1, "ou_b": 0} and not (tmp / "w" / "w1" / "messages.json").exists()
    rc, r = run("watch", "poll", "w1")
    assert rc == 10 and r["counts"]["ou_a"] == 1
    m = json.loads((tmp / "w" / "w1" / "messages.json").read_text(encoding="utf-8"))["messages"][0]
    assert m["sender_open_id"] == "ou_a" and "@_user_1" not in m["text"]
    rc, r = run("watch", "poll", "w2")
    assert rc == 30  # 上一批未收尾
    rc, r = run("watch", "commit", "w1")
    assert rc == 0
    rc, r = run("watch", "plan")
    assert all(v == 1792400000 for v in r["chats"][0]["targets"].values())
    rc, r3 = run("watch", "poll", "w3")
    assert rc == 10 and r3["counts"]["ou_a"] == 0
    rc, r = run("watch", "abort", "w3")
    assert rc == 0 and r["status"] == "aborted"


def test_dm_on_without_permission_fails_loudly(env, monkeypatch):
    setcfg(
        {
            **W,
            "watch": [{"name": "甲", "accounts": {"ou_a": "内部"}, "dm": True, "dm_chat_id": "oc_dm_a"}],
            "self_open_id": "ou_me",
        }
    )

    def call(c, *a, **k):
        if a[2].startswith("/open-apis/im/v1/chats/"):
            raise P.larkcli.LarkError("飞书接口错误 99991679：no permission")
        return [{"code": 0, "data": {"items": []}}]

    monkeypatch.setattr(P.larkcli, "call", call)
    rc, r = run("watch", "poll", "w9")
    assert rc == 1 and r["status"] == "fail" and "p2p_msg:get_as_user" in r["reason"]
    rc, r = run("watch", "poll", "w10", "--dry-run")
    assert rc == 1  # 演练同样报错
    monkeypatch.setattr(P.larkcli, "call", lambda c, *a, **k: [{"code": 0, "data": {"items": []}}])
    setcfg(W)
    rc, _ = run("watch", "poll", "w11", "--dry-run")
    assert rc == 0  # 锁已释放
