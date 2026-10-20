import contextlib

from quanttide_academy.core import db
from quanttide_academy.intent import collect
from quanttide_academy.watch import poll
from tests.helpers import *


def test_collect_mentions_self(monkeypatch, tmp_path):
    cfg = {
        "paths": {"data_dir": str(tmp_path)},
        "self_open_id": "ou_me",
        "watch": [{"name": "负责人甲", "accounts": {"ou_boss": "内部"}}],
        "initial_since": "2026-10-16",
        "scope": {"include_chats": [{"chat_id": "oc_1"}]},
    }
    msg = {
        "message_id": "om_1",
        "create_time": "1760000000000",
        "sender": {"id": "ou_boss"},
        "message_position": "5",
        "body": {"content": json.dumps({"text": "@_user_1 @_user_2 你来定"})},
        "mentions": [{"key": "@_user_1", "id": "ou_me"}, {"key": "@_user_2", "id": "ou_other"}],
    }

    def fake(cfg, *a):
        if "+chat-list" in a:
            return [{"data": {"chats": [{"chat_id": "oc_1", "name": "g"}]}}]
        if any("members" in x for x in a):
            return [{"data": {"items": [{"member_id": "ou_boss"}]}}]
        return [{"data": {"items": [msg]}}]

    monkeypatch.setattr(collect.larkcli, "call", fake)
    msg["sender"]["tenant_key"] = "t_boss"
    with contextlib.closing(db.connect(cfg)) as d:
        rep = collect.run(cfg, d, "b")
        m = rep["messages"][0]
        assert (
            m["sender_tenant_key"] == "t_boss"
            and d.execute("select sender_tenant_key from messages where message_id='om_1'").fetchone()[0] == "t_boss"
        )
        assert m["mentions"] == ["ou_me", "ou_other"] and m["mentions_self"] and m["text"].startswith("〔我〕 @_user_2")


def test_scope_whitelist(monkeypatch, tmp_path):
    base = {
        "paths": {"data_dir": str(tmp_path)},
        "self_open_id": "ou_me",
        "watch": [{"name": "负责人甲", "accounts": {"ou_boss": "内部"}}],
        "initial_since": "2026-10-16",
    }

    def fake(cfg, *a):
        if "+chat-list" in a:
            return [
                {"data": {"chats": [{"chat_id": "oc_w", "name": "白名单群"}, {"chat_id": "oc_d", "name": "部门群"}]}}
            ]
        if any("members" in x for x in a):
            return [{"data": {"items": [{"member_id": "ou_boss"}]}}]
        return [{"data": {"items": []}}]

    monkeypatch.setattr(collect.larkcli, "call", fake)
    cfg = {**base, "scope": {"include_chats": [{"chat_id": "oc_w", "name": "白名单群", "external": True}]}}
    with contextlib.closing(db.connect(cfg)) as d:
        rep = collect.run(cfg, d, "b")
    assert rep["new_chats"] == ["白名单群"] and rep["suggested_chats"] == [{"chat_id": "oc_d", "name": "部门群"}]
    cfg2 = {**base, "paths": {"data_dir": str(tmp_path / "2")}, "scope": {"include_chats": []}}
    with contextlib.closing(db.connect(cfg2)) as d2:
        rep = collect.run(cfg2, d2, "b")
    assert rep["new_chats"] == [] and len(rep["suggested_chats"]) == 2


def test_refetch_pushed_keeps_pushed(monkeypatch, tmp_path):
    cfg = {
        "paths": {"data_dir": str(tmp_path)},
        "self_open_id": "ou_me",
        "watch": [{"name": "张总", "accounts": {"ou_boss": "内部"}}],
        "initial_since": "2026-10-16",
        "scope": {"include_chats": [{"chat_id": "oc_1"}]},
    }
    msg = {
        "message_id": "om_1",
        "create_time": "1760000000000",
        "sender": {"id": "ou_boss"},
        "message_position": "5",
        "body": {"content": json.dumps({"text": "你来定"})},
    }

    def fake(c, *a):
        if "+chat-list" in a:
            return [{"data": {"chats": [{"chat_id": "oc_1", "name": "g"}]}}]
        if any("members" in x for x in a):
            return [{"data": {"items": []}}]
        return [{"data": {"items": [msg]}}]

    monkeypatch.setattr(collect.larkcli, "call", fake)
    with contextlib.closing(db.connect(cfg)) as d:
        assert len(collect.run(cfg, d, "b1")["messages"]) == 1
        d.execute("update messages set pushed=1")
        d.commit()
        msg["sender"]["tenant_key"] = "t_new"
        rep = collect.run(cfg, d, "b2")
        assert rep["messages"] == []
        assert d.execute("select pushed,batch,sender_tenant_key from messages where message_id='om_1'").fetchone() == (
            1,
            "b1",
            "t_new",
        )


def test_collect_fetches_through_watch_single_path(monkeypatch, tmp_path):
    cfg = {
        "paths": {"data_dir": str(tmp_path)},
        "self_open_id": "ou_me",
        "watch": [{"name": "负责人甲", "accounts": {"ou_boss": "内部"}}],
        "initial_since": "2026-10-16",
        "scope": {"include_chats": [{"chat_id": "oc_1"}]},
    }
    msg = {
        "message_id": "om_1",
        "create_time": "1760000000000",
        "sender": {"id": "ou_boss", "tenant_key": "t"},
        "message_position": "5",
        "body": {"content": json.dumps({"text": "x"})},
    }
    seen = []
    monkeypatch.setattr(
        poll,
        "fetch",
        lambda c, cid, s, e: seen.append(cid) or [msg, {**msg, "message_id": "om_2", "sender": {"id": "ou_x"}}],
    )
    monkeypatch.setattr(
        collect.larkcli, "call", lambda c, *a: [{"data": {"chats": [{"chat_id": "oc_1", "name": "g"}]}}]
    )
    with contextlib.closing(db.connect(cfg)) as d:
        rep = collect.run(cfg, d, "b")
    assert (
        seen == ["oc_1"]
        and [m["message_id"] for m in rep["messages"]] == ["om_1"]
        and "target" not in rep["messages"][0]
        and rep["messages"][0]["link"].startswith("https://")
    )
    assert "/open-apis/im/v1/messages" not in (ROOT / "src" / "quanttide_academy" / "intent" / "collect.py").read_text(
        encoding="utf-8"
    )
