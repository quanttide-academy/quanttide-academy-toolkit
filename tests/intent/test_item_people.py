from feishu_workflows.intent import roles
from feishu_workflows.intent.item_people import speaker_text
from feishu_workflows.intent.item_render import render_card
from feishu_workflows.intent.validate import validate
from feishu_workflows.watch.poll import record
from tests.helpers import *


def test_speaker_display_name_with_external_suffix_and_fallback():
    cfg = {"self_tenant_key": "t"}
    assert speaker_text({"speaker": "王五", "sender_external": True}, cfg) == "王五（外部成员）"
    assert speaker_text({"speaker": "王五", "sender_external": False}, cfg) == "王五"
    assert speaker_text({"speaker": "王五", "sender_external": False}, {}) == "王五（外部成员）"
    assert (
        speaker_text({"sender_external": True}, cfg) == "（未知发言人）"
        and speaker_text({"speaker": " "}, cfg) == "（未知发言人）"
    )
    it = {
        "no": 1,
        "title": "t",
        "summary": "s",
        "priority": "P2",
        "labels": [],
        "actions": ["执行"],
        "subtasks": [],
        "date": None,
        "date_basis": "x",
        "ddl": None,
        "ddl_basis": "x",
        "remind": None,
        "remind_basis": "x",
        "links": [{"url": "u", "message_id": "a", "direct": True, "time": "1", "quote": "q", "sender_external": False}],
    }
    assert "· 1 （未知发言人）：「q」" in render_card(it, {"labels": {"priority_names": PN}, "self_tenant_key": "t"})


def test_external_chat_and_speaker():
    cfg = {"labels": {"priority_names": PN}, "user": {"display_name": "小明"}, "self_tenant_key": "t_test"}
    it = {
        "no": 1,
        "title": "t",
        "summary": "s",
        "priority": "P2",
        "labels": [],
        "actions": ["问询"],
        "subtasks": [],
        "date": None,
        "date_basis": "x",
        "ddl": None,
        "ddl_basis": "x",
        "remind": None,
        "remind_basis": "x",
        "links": [
            {
                "url": "u",
                "message_id": "om_e",
                "direct": True,
                "time": "10-19 10:00",
                "quote": "q",
                "external_chat": True,
                "sender_external": True,
                "speaker": "负责人甲",
            }
        ],
    }
    c = render_card(it, cfg)
    assert (
        c.splitlines()[2] == "来自外部群"
        and "负责人甲（外部成员）：「q」" in c
        and "优先级：P2\n" in c
        and "标签：紧急次要" in c
    )
    t = copy.deepcopy(EX)
    x = t["items"][1]
    x["reviewers"] = []
    x["consultees"] = [
        {
            "name": "小明",
            "open_id": "ou_demo_self",
            "basis": "quote",
            "evidence": "活动报名表请@小李 负责收集",
            "message_id": "om_demo_2",
        }
    ]
    c2 = {"self_open_id": "ou_demo_self", "user": {"display_name": "小明", "roles": ["示例负责人"]}}
    msgs = no_self_mention(fixture_msgs())
    assert any("只能按角色推断" in e for e in validate(t, msgs, c2))
    msgs["om_demo_2"] = {**msgs["om_demo_2"], "text": msgs["om_demo_2"]["text"] + " 小明"}
    assert validate(t, msgs, c2) == []


def test_summary_and_evidence_share_speaker_text():
    cfg = {"labels": {"priority_names": PN}, "self_tenant_key": "t"}
    base = {
        "no": 1,
        "title": "t",
        "summary": "{speaker}请大家周五前交表。",
        "priority": "P2",
        "labels": [],
        "subtasks": [],
        "date": None,
        "date_basis": "x",
        "ddl": None,
        "ddl_basis": "x",
        "remind": None,
        "remind_basis": "x",
    }
    for link, want in (
        ({"speaker": "王五", "sender_external": True}, "王五（外部成员）"),
        ({"speaker": "王五", "sender_external": False}, "王五"),
        ({"sender_external": True}, "（未知发言人）"),
    ):
        c = render_card(
            {**base, "links": [{"url": "u", "message_id": "a", "direct": True, "time": "1", "quote": "q", **link}]}, cfg
        )
        assert c.splitlines()[1] == f"{want}请大家周五前交表。" and f"{want}：「q」" in c


def test_system_message_display_and_excluded_from_roles():
    for sys_link in (
        {"sender": None},
        {"sender": {}},
        {"sender": {"id": ""}},
        {"msg_type": "system"},
        {"system": True},
    ):
        assert speaker_text(sys_link, {}) == "（系统消息）"
    raw_sys = {
        "message_id": "om_sys",
        "create_time": "1760000000000",
        "sender": None,
        "msg_type": "system",
        "body": {"content": '{"text":"系统提示"}'},
    }
    rec = record({"self_open_id": "ou_me"}, {"chat_id": "oc_1", "name": "群一"}, None, raw_sys, [])
    assert rec["speaker"] == "（系统消息）" and rec["system"] is True and rec["sender_open_id"] is None
    it = {
        "no": 1,
        "title": "t",
        "summary": "{speaker}提示",
        "kind": "task",
        "task_type": "undetermined",
        "assignees": [
            {"name": "小明", "open_id": "ou_me", "basis": "quote", "evidence": "系统提示", "message_id": "om_sys"}
        ],
        "reviewers": [],
        "consultees": [],
        "priority": "P3",
        "labels": [],
        "subtasks": [],
        "links": [
            {
                "url": "u",
                "message_id": "om_sys",
                "direct": True,
                "time": "10-18 09:00",
                "quote": "系统提示",
                "system": True,
            }
        ],
    }
    cfg = {"self_open_id": "ou_me", "user": {"display_name": "小明"}}
    assert roles.effective(it, cfg)["assignees"] == [] and roles.own_roles(it, cfg) == []
    c = render_card(it, cfg)
    assert "（系统消息）提示" in c and "· 10-18 09:00 （系统消息）：「系统提示」" in c and "（外部成员）" not in c
