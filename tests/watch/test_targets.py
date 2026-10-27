import sqlite3

import pytest

from quanttide_academy_toolkit.core import migrations
from quanttide_academy_toolkit.watch import targets as T

CFG = {
    "watch": [
        {"name": "甲", "accounts": {"ou_a1": "内部", "ou_a2": "外部"}},
        {"name": "乙", "accounts": {"ou_b1": "内部"}},
    ]
}


def test_load_and_route():
    ts = T.load(CFG)
    assert (
        [t.key for t in ts] == ["ou_a1", "ou_b1"]
        and ts[0].name == "甲"
        and ts[0].accounts == {"ou_a1": "内部", "ou_a2": "外部"}
    )
    assert T.owner(ts) == {"ou_a1": "ou_a1", "ou_a2": "ou_a1", "ou_b1": "ou_b1"}


def test_validation():
    with pytest.raises(T.BadTargets, match="重复"):
        T.load({"watch": [{"name": "甲", "accounts": {"ou_x": "a"}}, {"name": "乙", "accounts": {"ou_x": "b"}}]})
    with pytest.raises(T.BadTargets, match="ou_"):
        T.load({"watch": [{"name": "甲", "accounts": {"bad": "a"}}]})
    with pytest.raises(T.BadTargets, match="账号"):
        T.load({"watch": [{"name": "甲", "accounts": {}}]})
    with pytest.raises(T.BadTargets, match="name"):
        T.load({"watch": [{"accounts": {"ou_x": "a"}}]})
    assert T.load({}) == []


def test_dm_switch_global_and_per_target_wins():
    w = [
        {"name": "甲", "accounts": {"ou_a": "内部"}, "dm_chat_id": "oc_dm_a"},
        {"name": "乙", "accounts": {"ou_b": "内部"}, "dm": False},
        {"name": "丙", "accounts": {"ou_c": "x"}, "dm": True, "dm_chat_id": "oc_dm_c"},
    ]
    assert [t.dm for t in T.load({"watch": w})] == [False, False, True]  # 默认关；单目标开
    assert [t.dm for t in T.load({"watch": w, "watch_options": {"dm": True}})] == [
        True,
        False,
        True,
    ]  # 全局开，单目标 false 优先
    assert T.load({"watch": w})[2].dm_chat == "oc_dm_c"
    with pytest.raises(T.BadTargets, match="dm_chat_id"):
        T.load({"watch": [{"name": "甲", "accounts": {"ou_a": "x"}, "dm": True}]})
    with pytest.raises(T.BadTargets, match="dm_chat_id"):
        T.load({"watch": [{"name": "甲", "accounts": {"ou_a": "x"}, "dm": True, "dm_chat_id": "bad"}]})
    with pytest.raises(T.BadTargets, match="dm"):
        T.load({"watch": [{"name": "甲", "accounts": {"ou_a": "x"}, "dm": "yes"}]})


def test_backfill_days_default_and_bounds():
    assert T.backfill_days({}) == 7 and T.backfill_days({"watch_options": {"backfill_days": 30}}) == 30
    for bad in (0, 31, "7", True):
        with pytest.raises(T.BadTargets, match="backfill_days"):
            T.backfill_days({"watch_options": {"backfill_days": bad}})


def test_target_chats_must_be_subset_of_include_chats():
    sc = {"include_chats": [{"chat_id": "oc_1"}, {"chat_id": "oc_2"}]}
    ts = T.load(
        {
            "scope": sc,
            "watch": [
                {"name": "甲", "accounts": {"ou_a": "x"}, "chats": ["oc_2"]},
                {"name": "乙", "accounts": {"ou_b": "x"}},
            ],
        }
    )
    assert ts[0].chats == ("oc_2",) and ts[1].chats is None
    with pytest.raises(T.BadTargets, match="include_chats"):
        T.load({"scope": sc, "watch": [{"name": "甲", "accounts": {"ou_a": "x"}, "chats": ["oc_9"]}]})
    with pytest.raises(T.BadTargets, match="include_chats"):
        T.load({"watch": [{"name": "甲", "accounts": {"ou_a": "x"}, "chats": ["oc_1"]}]})


def test_self_key_resolution(tmp_path):
    assert T.self_key({**CFG, "self_open_id": "ou_b1"}) == "ou_b1"
    assert T.self_key({**CFG, "self_open_id": "ou_other"}) == "ou_a1"
    assert T.self_key({"self_open_id": "ou_me"}) == "ou_me"
    p = tmp_path / "s.db"
    migrations.migrate(p)
    d = sqlite3.connect(str(p))
    assert T.self_key(None, d) == "ou_demo_self"
    d.execute("insert into watch_cursors(target_key,chat_id,last_ts) values('ou_wc','oc_1',10)")
    d.commit()
    assert T.self_key(None, d) == "ou_wc"
    d.execute("insert into watch_targets(key,name,active) values('ou_wt','甲',1)")
    d.commit()
    assert T.self_key(None, d) == "ou_wt"
    d.close()
