"""私聊来源核验：开关关着不发任何请求；不是 p2p、成员不对、没权限都报错停止。全部为虚构 ID。"""

import pytest

from quanttide_academy.watch import dm
from quanttide_academy.watch.targets import Target

T = Target("ou_a", "甲", {"ou_a": "内部", "ou_a2": "外部"}, dm=True, dm_chat="oc_dm_a")
CFG = {"self_open_id": "ou_me"}


def fake(monkeypatch, mode="p2p", members=("ou_me", "ou_a"), calls=None):
    def call(cfg, *a, **k):
        (calls if calls is not None else []).append(a)
        assert a[:2] == ("api", "GET")
        if a[2].endswith("/members"):
            return [{"code": 0, "data": {"items": [{"member_id": o} for o in members]}}]
        if a[2].startswith("/open-apis/im/v1/chats/"):
            return [{"code": 0, "data": {"chat_mode": mode}}]
        return [{"code": 0, "data": {"items": []}}]

    monkeypatch.setattr(dm.larkcli, "call", call)


def test_switch_off_makes_no_request(monkeypatch):
    calls = []
    fake(monkeypatch, calls=calls)
    with pytest.raises(dm.DmUnavailable, match="未开启"):
        dm.fetch(CFG, Target("ou_a", "甲", {"ou_a": "x"}), 0, 1)
    assert calls == []


@pytest.mark.parametrize(
    "mode,members,msg",
    [
        ("group", ("ou_me", "ou_a"), "不是私聊"),
        ("p2p", ("ou_me", "ou_x"), "成员"),
        ("p2p", ("ou_me", "ou_a", "ou_b"), "成员"),
        ("p2p", ("ou_a", "ou_a2"), "成员"),
    ],
)
def test_verify_rejects(monkeypatch, mode, members, msg):
    calls = []
    fake(monkeypatch, mode, members, calls)
    with pytest.raises(dm.DmUnavailable, match=msg):
        dm.fetch(CFG, T, 0, 1)
    assert not any(a[2] == "/open-apis/im/v1/messages" for a in calls)  # 核验不过：不拉消息


def test_verify_ok_with_second_account_and_no_self_fails(monkeypatch):
    fake(monkeypatch, members=("ou_me", "ou_a2"))
    assert dm.fetch(CFG, T, 0, 1) == ([], None)
    with pytest.raises(dm.DmUnavailable, match="self_open_id"):
        dm.fetch({}, T, 0, 1)


def test_dm_filters_recalled_and_app_sender(monkeypatch):
    items = [
        {"message_id": "d1", "create_time": "150000", "sender": {"id": "ou_a", "sender_type": "user"}},
        {"message_id": "d2", "create_time": "160000", "sender": {"id": "ou_a", "sender_type": "user"}, "deleted": True},
        {"message_id": "d3", "create_time": "170000", "sender": {"id": "ou_a", "sender_type": "app"}},
    ]

    def call(cfg, *a, **k):
        if a[2].endswith("/members"):
            return [{"code": 0, "data": {"items": [{"member_id": "ou_me"}, {"member_id": "ou_a"}]}}]
        if a[2].startswith("/open-apis/im/v1/chats/"):
            return [{"code": 0, "data": {"chat_mode": "p2p"}}]
        return [{"code": 0, "data": {"items": items}}]

    monkeypatch.setattr(dm.larkcli, "call", call)
    got, mx = dm.fetch(CFG, T, 100, 200)
    assert [m["message_id"] for m in got] == ["d1"] and mx == 170
