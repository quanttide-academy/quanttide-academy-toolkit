"""watch 多目标卡片：角色行只展示；行动按本人；对方 DDL 不进 deadline；合并批次按目标分节、序号全批连续。虚构数据。"""

from feishu_workflows.intent import roles
from feishu_workflows.intent import section as watch_view
from feishu_workflows.intent.fetch import sections
from feishu_workflows.intent.item import description, render_card
from tests.helpers import *

CFG = {
    "labels": {"priority_names": PN},
    "user": {"display_name": "小明"},
    "self_tenant_key": "t",
    "self_open_id": "ou_me",
    "watch": [{"name": "小明", "accounts": {"ou_me": "内部"}}, {"name": "甲", "accounts": {"ou_a": "内部"}}],
}


def item(target, no=1):
    return {
        "no": no,
        "title": "交表",
        "task_type": "team",
        "summary": "s",
        "date": None,
        "ddl": "2026-10-30",
        "remind": None,
        "priority": None,
        "labels": [],
        "refs": [],
        "subtasks": [],
        "note": None,
        "assignees": [{"name": "甲", "open_id": "ou_a", "basis": "quote", "evidence": "q", "message_id": "m1"}],
        "reviewers": [{"name": "小明", "open_id": "ou_me", "basis": "quote", "evidence": "q", "message_id": "m1"}],
        "consultees": [],
        "ddl_by_person": [{"person": "甲", "date": "2026-10-25", "basis": "周六前"}],
        "links": [
            {
                "url": "u",
                "message_id": "m1",
                "direct": True,
                "time": "10-18 09:00",
                "quote": "q",
                "speaker": "甲",
                "target": target,
            }
        ],
    }


def test_role_line_display_only_actions_from_self():
    it = item("ou_a")
    c = render_card(it, CFG)
    assert c.splitlines()[0] == "监听对象：甲（角色：执行员，仅展示）" and c.splitlines()[1].startswith("【#1】")
    assert roles.derive_actions(it, CFG) == ["评审"]  # 行动按本人 open_id
    assert watch_view.role_line(item("ou_me"), CFG) is None and watch_view.role_line(item(None), CFG) is None


def test_watched_ddl_only_in_description():
    it = item("ou_a")
    assert roles.self_ddl(it, CFG) is None and "甲 2026-10-25" in description(
        it, CFG
    )  # 对方 DDL 不进 deadline，也不退回条目截止
    assert roles.self_ddl(item("ou_me"), CFG) == "2026-10-30"  # 本人目标：原规则不变


def test_combined_batch_sections_and_numbering():
    """合并批次：按目标分节（本人在前），#N 全批连续不重排编号；单一目标时不加分节。"""
    its = [{**item("ou_a", 1)}, {**item("ou_me", 2)}, {**item("ou_a", 3)}]
    assert sections([(it, f"card{it['no']}") for it in its], CFG) == [
        "—— 本人 ——",
        "card2",
        "—— 甲 ——",
        "card1",
        "card3",
    ]
    assert sections([(it, f"card{it['no']}") for it in its[:1]], CFG) == ["card1"]
