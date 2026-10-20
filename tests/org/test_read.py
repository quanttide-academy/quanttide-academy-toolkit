"""org 只读层：部门用应用身份、群用用户身份，全部 GET；读失败或部门为空即报错。"""

import pytest

from feishu_workflows.org import read as R


def test_identities_and_get_only(monkeypatch):
    calls = []

    def call(cfg, *a, **k):
        calls.append(a)
        assert a[:2] == ("api", "GET")
        if "departments" in a[2]:
            return [
                {"data": {"items": [{"open_department_id": "od_1", "name": "实训基地", "parent_department_id": "0"}]}}
            ]
        if "find_by_department" in a[2]:
            return [{"data": {"items": [{"open_id": "ou_1"}]}}]
        if a[2].endswith("/members"):
            return [{"data": {"items": [{"member_id": "ou_1", "tenant_key": "t"}]}}]
        return [{"data": {"name": "群", "owner_id": "ou_1"}}]

    monkeypatch.setattr(R.larkcli, "call", call)
    assert R.dept_tree({}) == [{"id": "od_1", "name": "实训基地", "parent": "0"}] and R.dept_members({}, "od_1") == {
        "ou_1"
    }
    assert R.chat_info({}, "oc_1")["owner"] == "ou_1" and R.chat_members({}, "oc_1") == {"ou_1": "t"}
    who = [a[a.index("--as") + 1] for a in calls]
    assert who == ["bot", "bot", "user", "user"]


def test_dept_errors(monkeypatch):
    def boom(cfg, *a, **k):
        raise R.larkcli.LarkError("x")

    monkeypatch.setattr(R.larkcli, "call", boom)
    with pytest.raises(R.DeptReadError):
        R.dept_tree({})
    with pytest.raises(R.DeptReadError):
        R.dept_members({}, "od")
    with pytest.raises(R.ChatReadError):
        R.chat_members({}, "oc")
    with pytest.raises(R.ChatReadError):
        R.chat_info({}, "oc")
    with pytest.raises(R.ChatReadError):
        R.approval_message({}, "om_1")
    with pytest.raises(R.ChatReadError):
        R.my_chats({})
    monkeypatch.setattr(R.larkcli, "call", lambda c, *a, **k: [{"data": {"items": []}}])
    with pytest.raises(R.DeptReadError, match="为空"):
        R.dept_tree({})
    with pytest.raises(R.ChatReadError, match="不存在"):
        R.approval_message({}, "om_1")
    monkeypatch.setattr(
        R.larkcli,
        "call",
        lambda c, *a, **k: (
            [{"data": {"chats": [{"chat_id": "oc_1", "name": "群1"}]}}]
            if "+chat-list" in a
            else [
                {
                    "data": {
                        "items": [
                            {
                                "message_id": "om_1",
                                "chat_id": "oc_ap",
                                "sender": {"id": "ou_me", "sender_type": "user"},
                                "create_time": "1792411200000",
                                "msg_type": "text",
                                "body": {"content": "not-json"},
                            }
                        ]
                    }
                }
            ]
        ),
    )
    assert R.my_chats({}) == [{"chat_id": "oc_1", "name": "群1"}]
    assert R.approval_message({}, "om_1")["text"] is None
