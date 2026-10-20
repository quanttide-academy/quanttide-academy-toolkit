import json
import sqlite3

import pytest

from feishu_workflows.core import migrations
from feishu_workflows.watch import cursors as C
from feishu_workflows.watch import poll as P
from feishu_workflows.watch.targets import Target
from tests.helpers import ROOT

TS = [Target("ou_a", "甲", {"ou_a": "内部", "ou_a2": "外部"}), Target("ou_b", "乙", {"ou_b": "内部"})]


def raw(mid, sender, ts, text="hi", **kw):
    return {
        "message_id": mid,
        "create_time": str(ts * 1000),
        "sender": {"id": sender, "tenant_key": "t"},
        "body": {"content": json.dumps({"text": text})},
        "message_position": "7",
        **kw,
    }


def test_route_by_sender_and_target_start():
    sp = {"start": 100, "targets": {"ou_a": 100, "ou_b": 300}}
    got = P.route(
        [
            raw("m1", "ou_a2", 150),
            raw("m2", "ou_b", 200),
            raw("m3", "ou_b", 350),
            raw("m4", "ou_x", 400),
            raw("m5", "ou_a", 160, deleted=True),
        ],
        TS,
        sp,
    )
    assert [(m["message_id"], t) for t, m in got] == [("m1", "ou_a"), ("m3", "ou_b")]


def test_poll_reads_get_only_and_stages(tmp_path, monkeypatch):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    calls = []

    def call(cfg, *a, **k):
        calls.append(a)
        assert a[:2] == ("api", "GET")
        return [
            {
                "code": 0,
                "data": {
                    "items": [
                        raw("m1", "ou_a", 150),
                        raw("m2", "ou_b", 160, mentions=[{"id": "ou_me", "key": "@_user_1"}]),
                    ]
                },
            }
        ]

    monkeypatch.setattr(P.larkcli, "call", call)
    cfg = {"self_open_id": "ou_me", "scope": {"include_chats": [{"chat_id": "oc_1", "name": "群一", "external": True}]}}
    rep = P.poll(cfg, d, "b1", TS, init=100, end=1000, dry_run=True)
    assert (
        rep["counts"] == {"ou_a": 1, "ou_b": 1}
        and d.execute("select count(*) from watch_pending_cursors").fetchone()[0] == 0
    )  # 演练不写库
    assert len(calls) == 1 and '"container_id": "oc_1"' in calls[0][-1]
    rep = P.poll(cfg, d, "b1", TS, init=100, end=1000)
    m = {x["message_id"]: x for x in rep["messages"]}
    assert (
        m["m1"]["target"] == "ou_a"
        and m["m1"]["speaker"] == "甲"
        and m["m1"]["sender_open_id"] == "ou_a"
        and m["m1"]["external_chat"] is True
    )
    assert m["m2"]["mentions_self"] is True and m["m2"]["mentions"] == ["ou_me"]
    C.commit(d, "b1")
    assert C.start_points(d, TS, ["oc_1"], init=100)["oc_1"]["targets"] == {"ou_a": 160, "ou_b": 160}
    d.close()


def test_no_scope_fetches_nothing(monkeypatch, tmp_path):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    monkeypatch.setattr(P.larkcli, "call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应联网")))
    assert P.poll({}, d, "b1", TS, init=0, end=1)["messages"] == []
    d.close()


DMT = [
    Target("ou_a", "甲", {"ou_a": "内部"}, dm=True, dm_chat="oc_dm_a"),
    Target("ou_b", "乙", {"ou_b": "内部"}),
    Target("ou_c", "丙", {"ou_c": "外部"}, dm=True, dm_chat="oc_dm_c"),
]


def _dm_fixture(monkeypatch, calls, fail=False):
    fx = json.loads((ROOT / "tests" / "fixtures" / "watch" / "dm_multi.json").read_text(encoding="utf-8"))

    def call(cfg, *a, **k):
        calls.append(a)
        assert a[:2] == ("api", "GET")
        if a[2].startswith("/open-apis/im/v1/chats/"):
            if fail:
                raise P.larkcli.LarkError("飞书接口错误 99991679：no permission")
            c = a[2].split("/")[5]
            mem = {"oc_dm_a": ["ou_me", "ou_a"], "oc_dm_c": ["ou_me", "ou_c"]}[c]
            return (
                [{"code": 0, "data": {"items": [{"member_id": o} for o in mem]}}]
                if a[2].endswith("/members")
                else [{"code": 0, "data": {"chat_mode": "p2p"}}]
            )
        cid = json.loads(a[-1])["container_id"]
        return [{"code": 0, "data": {"items": fx.get(cid, [])}}]

    monkeypatch.setattr(P.larkcli, "call", call)


def test_dm_source_offline_multi_target(tmp_path, monkeypatch):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    calls = []
    _dm_fixture(monkeypatch, calls)
    cfg = {"self_open_id": "ou_me", "scope": {"include_chats": []}}
    rep = P.poll(cfg, d, "b1", DMT, init=100, end=1000)
    m = {x["message_id"]: x for x in rep["messages"]}
    assert set(m) == {"om_da1", "om_da2", "om_dc1"} and rep["counts"] == {
        "ou_a": 2,
        "ou_b": 0,
        "ou_c": 1,
    }  # 只取本人与目标之间的消息
    assert (
        m["om_da1"]["dm"] is True
        and m["om_da1"]["target"] == "ou_a"
        and m["om_da2"]["sender_open_id"] == "ou_me"
        and m["om_dc1"]["chat"] == "私聊·丙"
    )
    assert sorted(json.loads(a[-1])["container_id"] for a in calls if a[2] == "/open-apis/im/v1/messages") == [
        "oc_dm_a",
        "oc_dm_c",
    ]
    assert (
        sum(a[2].endswith("/members") for a in calls) == 2 and sum(a[2].count("/") == 5 for a in calls) == 2
    )  # 每个私聊拉取前都现场核验          # 乙没开私聊：不拉
    C.commit(d, "b1")
    assert C.start_points(d, DMT[:1], ["oc_dm_a"], init=100)["oc_dm_a"]["targets"] == {"ou_a": 170}
    d.close()


def test_dm_without_permission_fails_loudly(tmp_path, monkeypatch):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    _dm_fixture(monkeypatch, [], fail=True)
    with pytest.raises(P.DmUnavailable, match="p2p_msg:get_as_user"):
        P.poll({"self_open_id": "ou_me", "scope": {"include_chats": []}}, d, "b1", DMT, init=100, end=1000)
    assert d.execute("select count(*) from watch_pending_cursors").fetchone()[0] == 0
    d.close()


def test_target_chat_subset_and_per_target_backfill(tmp_path, monkeypatch):
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    ts = [Target("ou_a", "甲", {"ou_a": "x"}, chats=("oc_2",)), Target("ou_b", "乙", {"ou_b": "x"})]
    monkeypatch.setattr(
        P.larkcli,
        "call",
        lambda c, *a, **k: [{"code": 0, "data": {"items": [raw("m1", "ou_a", 150), raw("m2", "ou_b", 160)]}}],
    )
    cfg = {"scope": {"include_chats": [{"chat_id": "oc_1"}, {"chat_id": "oc_2"}]}}
    rep = P.poll(cfg, d, "b1", ts, init=100, end=1000)
    assert sorted((m["chat_id"], m["message_id"]) for m in rep["messages"]) == [
        ("oc_1", "m2"),
        ("oc_2", "m1"),
        ("oc_2", "m2"),
    ]  # 甲只在 oc_2
    C.commit(d, "b1")
    assert C.start_points(d, ts, ["oc_1"], init=100)["oc_1"]["targets"]["ou_a"] == 100
    d.close()  # 甲在 oc_1 没有游标


def test_same_second_two_messages_across_two_rounds(tmp_path, monkeypatch):
    """点名测试：同一秒（ts=150）里的两条消息分两轮拉取，起点 start=last_ts 不加 1，靠 message_id 去重，两轮各拿一条且不漏不重。"""
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    m1 = raw("om_same_1", "ou_a", 150, "第一条")
    m2 = raw("om_same_2", "ou_a", 150, "第二条")
    rounds = [[m1], [m1, m2]]
    monkeypatch.setattr(P.larkcli, "call", lambda c, *a, **k: [{"code": 0, "data": {"items": rounds.pop(0)}}])
    cfg = {"self_open_id": "ou_me", "scope": {"include_chats": [{"chat_id": "oc_1", "name": "群一"}]}}
    r1 = P.poll(cfg, d, "b1", TS[:1], init=100, end=200)
    C.commit(d, "b1")
    assert [m["message_id"] for m in r1["messages"]] == ["om_same_1"]
    assert C.start_points(d, TS[:1], ["oc_1"], init=100)["oc_1"]["start"] == 150
    r2 = P.poll(cfg, d, "b2", TS[:1], init=100, end=200)
    C.commit(d, "b2")
    assert [m["message_id"] for m in r2["messages"]] == ["om_same_2"]
    assert C.start_points(d, TS[:1], ["oc_1"], init=100)["oc_1"]["start"] == 150
    d.close()


def test_recalled_app_sender_and_thread_replies_truncation(tmp_path, monkeypatch):
    """拉取规范测试：撤回消息（deleted=True）、丢弃 sender_type=app、thread_replies 单话题 >50 条或累计 >500 条截断。"""
    sp = {"start": 100, "targets": {"ou_a": 100}}
    m_ok = raw("m_ok", "ou_a", 150, "正常")
    m_del = raw("m_del", "ou_a", 151, "已撤回", deleted=True)
    m_app = {
        **raw("m_app", "ou_a", 152, "机器人消息"),
        "sender": {"id": "ou_a", "sender_type": "app", "tenant_key": "t"},
    }
    assert [m["message_id"] for _, m in P.route([m_ok, m_del, m_app], TS[:1], sp)] == ["m_ok"]
    # 单条话题回复超过 50 条截断，且过滤掉话题内已撤回和 app 发的回复
    replies = [
        {"message_id": f"r_{i}", "text": f"reply {i}", "sender": {"id": "ou_a", "sender_type": "user"}}
        for i in range(65)
    ]
    replies.append({"message_id": "r_del", "text": "del", "deleted": True})
    replies.append({"message_id": "r_app", "text": "app", "sender": {"id": "ou_a", "sender_type": "app"}})
    one = P.trim_threads([{"message_id": "m1", "thread_replies": replies}])
    assert len(one[0]["thread_replies"]) == 50 and one[0]["thread_truncated"] is True
    # 累计话题回复超过 500 条截断（12 条消息 × 50 = 600 → 前 10 条各 50，第 11、12 条为 0）
    many = [
        {"message_id": f"t_{k}", "thread_replies": [{"message_id": f"r_{k}_{i}", "text": "x"} for i in range(50)]}
        for k in range(12)
    ]
    P.trim_threads(many)
    assert sum(len(x["thread_replies"]) for x in many) == 500
    assert (
        len(many[9]["thread_replies"]) == 50
        and len(many[10]["thread_replies"]) == 0
        and many[10]["thread_truncated"] is True
    )
